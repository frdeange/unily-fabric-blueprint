import uuid
from datetime import datetime, timezone
import notebookutils
from delta.tables import DeltaTable
from pyspark.sql import Window, functions as F

# Gold reads Silver and writes Gold only; it never touches the Vault workspace.
DATA = CONFIG["data_workspace_id"]
SILVER = onelake_table(DATA, CONFIG["silver_id"], "usage_events")
GOLD = {name: onelake_table(DATA, CONFIG["gold_id"], name) for name in GOLD_TABLES}
STATE = onelake_files(DATA, CONFIG["gold_id"], GOLD_STATE)
RUN = str(uuid.uuid4())
TENANTS = [source["tenant_id"] for source in CONFIG["sources"]]
notebookutils.fs.mkdirs(STATE.rsplit("/", 1)[0])


def empty(df, message):
    if df.limit(1).count():
        raise RuntimeError(message)


def cdf_enabled(table):
    properties = table.detail().first()["properties"] or {}
    return str(properties.get("delta.enableChangeDataFeed", "false")).lower() == "true"


def conform(df, table, *extra):
    return df.select(*[F.col(name).cast(kind).alias(name) for name, kind in GOLD_TABLES[table]], *extra)


if not DeltaTable.isDeltaTable(spark, SILVER):
    raise RuntimeError("Silver is missing; run BronzeToSilver first")
silver = DeltaTable.forPath(spark, SILVER)
if not cdf_enabled(silver):
    raise RuntimeError("Silver Change Data Feed is disabled; run BronzeToSilver to enable it")
silver_id = silver.detail().first()["id"]
current = int(silver.history(1).first()["version"])
state = json.loads(notebookutils.fs.head(STATE, 1000000)) if notebookutils.fs.exists(STATE) else None
if state:
    if state["silver_table_id"] != silver_id:
        raise RuntimeError("Silver was recreated after the last Gold run; review required")
    if state["silver_version"] > current:
        raise RuntimeError("Gold watermark is ahead of Silver; review required")
    if state["silver_version"] == current:
        print(json.dumps({"status": "up_to_date", "silver_version": current, "gold_writes": 0}))
        notebookutils.notebook.exit("Gold is up to date; no reads or writes")

# First run publishes the current Silver snapshot; later runs read only the change feed.
if state is None:
    mode = "initial_snapshot"
    changes = (spark.read.format("delta").option("versionAsOf", current).load(SILVER)
               .withColumn("_change_type", F.lit("insert"))
               .withColumn("_commit_version", F.lit(current).cast("long")))
else:
    mode = "change_data_feed"
    changes = (spark.read.format("delta").option("readChangeFeed", "true")
               .option("startingVersion", state["silver_version"] + 1)
               .option("endingVersion", current).load(SILVER))
# Users touched by any change, including the old side of an update, need their stats refreshed.
affected = changes.select("tenant_id", "user_key").distinct().cache()
# The old side of an update removes its key; the new side, in the same commit, wins on the same key.
# This also handles updates that change tenant_id or event_id.
changes = changes.withColumn("_delete", F.col("_change_type").isin("delete", "update_preimage"))
latest = Window.partitionBy("tenant_id", "event_id").orderBy(F.col("_commit_version").desc(), "_delete")
changes = changes.withColumn("_rank", F.row_number().over(latest)).filter("_rank = 1").cache()
upserts = changes.filter(~F.col("_delete"))

for column in ["tenant_id", "event_id", "user_key", "feature_id", "event_date"]:
    empty(upserts.filter(F.col(column).isNull()), "Missing " + column)
empty(upserts.filter(~F.col("tenant_id").isin(TENANTS)), "Tenant outside the source registry")
catalog = spark.createDataFrame(FEATURE_CATALOG, gold_schema("dim_feature"))
empty(upserts.join(catalog, "feature_id", "left_anti"), "Unknown feature_id; update FEATURE_CATALOG")
has_text = F.col("free_text").isNotNull() & (F.trim(F.col("free_text")) != "")
# Only text that went through the PII protection step can be published.
empty(upserts.filter(has_text & ~F.col("pii_status").eqNullSafe("processed")), "Unprotected text in Silver")

for name in GOLD_TABLES:
    expected = spark.createDataFrame([], gold_schema(name)).schema
    if not DeltaTable.isDeltaTable(spark, GOLD[name]):
        spark.createDataFrame([], expected).write.format("delta").mode("errorifexists").save(GOLD[name])
    actual = spark.read.format("delta").load(GOLD[name]).schema
    if [(f.name, f.dataType) for f in actual] != [(f.name, f.dataType) for f in expected]:
        raise RuntimeError(f"Gold schema differs from the contract: {name}")
    if FORBIDDEN_COLUMNS & set(actual.fieldNames()):
        raise RuntimeError(f"Forbidden column in Gold: {name}")


def merge(table, source, upsert=True, delete=False):
    """Idempotent upsert on the contract keys; reruns never duplicate rows."""
    columns = [name for name, _ in GOLD_TABLES[table]]
    condition = " AND ".join(f"t.{key} = s.{key}" for key in GOLD_KEYS[table])
    values = {name: f"s.{name}" for name in columns}
    builder = DeltaTable.forPath(spark, GOLD[table]).alias("t").merge(source.alias("s"), condition)
    keep = "NOT s._delete" if delete else None
    if delete:
        builder = builder.whenMatchedDelete(condition="s._delete")
    if upsert:
        builder = builder.whenMatchedUpdate(condition=keep, set=values)
    builder.whenNotMatchedInsert(condition=keep, values=values).execute()


facts = changes.select(
    "tenant_id", "event_id", "user_key", "feature_id", "event_date", "occurred_at",
    "event_type", "duration_seconds",
    F.when(has_text, F.col("free_text")).alias("feedback_text"),
    has_text.alias("has_feedback_text"), "pii_status",
    F.col("_commit_version").alias("silver_version"), "_delete")
merge("fact_usage_event", conform(facts, "fact_usage_event", "_delete"), delete=True)

# Recompute only the affected users from the fact table; users without events are removed.
fact = spark.read.format("delta").load(GOLD["fact_usage_event"])
stats = fact.join(F.broadcast(affected), ["tenant_id", "user_key"]).groupBy("tenant_id", "user_key").agg(
    F.min("event_date").alias("first_seen_date"), F.max("event_date").alias("last_seen_date"),
    F.count("*").alias("event_count"))
users = affected.join(stats, ["tenant_id", "user_key"], "left").withColumn(
    "_delete", F.col("event_count").isNull())
merge("dim_user", conform(users, "dim_user", "_delete"), delete=True)

day = F.col("date")
dates = upserts.select(F.col("event_date").alias("date")).distinct().select(
    "date", F.year(day).alias("year"), F.quarter(day).alias("quarter"), F.month(day).alias("month"),
    F.date_format(day, "MMMM").alias("month_name"), F.dayofmonth(day).alias("day"),
    # ISO day of week: Monday = 1 ... Sunday = 7.
    ((F.dayofweek(day) + 5) % 7 + 1).alias("day_of_week"), F.date_format(day, "EEEE").alias("day_name"),
    F.weekofyear(day).alias("iso_week"), F.dayofweek(day).isin(1, 7).alias("is_weekend"))
merge("dim_date", conform(dates, "dim_date"), upsert=False)
merge("dim_tenant", spark.createDataFrame([(t,) for t in TENANTS], gold_schema("dim_tenant")), upsert=False)
merge("dim_feature", catalog)

counts = {name: spark.read.format("delta").load(GOLD[name]).count() for name in GOLD_TABLES}
silver_rows = spark.read.format("delta").option("versionAsOf", current).load(SILVER).count()
if counts["fact_usage_event"] != silver_rows:
    raise RuntimeError("Gold facts do not match the Silver snapshot; watermark not advanced")
evidence = {
    "status": "completed", "run_id": RUN, "mode": mode,
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "silver_table_id": silver_id, "silver_version": current,
    "previous_silver_version": state["silver_version"] if state else None,
    "changed_events": changes.count(), "deleted_events": changes.filter("_delete").count(),
    "affected_users": affected.count(), "gold_rows": counts,
}
# The watermark moves only after every merge succeeded; a failed run is simply repeated.
notebookutils.fs.put(STATE, json.dumps(evidence, indent=2), True)
print(json.dumps(evidence, indent=2))
