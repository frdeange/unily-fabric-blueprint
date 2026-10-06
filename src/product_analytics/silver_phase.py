
import hashlib
import uuid
from datetime import datetime, timezone
from functools import reduce
from contextlib import contextmanager
import notebookutils
from delta.tables import DeltaTable
from pyspark.sql import functions as F

BASE = f'abfss://{CONFIG["workspace_id"]}@onelake.dfs.fabric.microsoft.com'
BRONZE = BASE + "/" + CONFIG["bronze_id"]
IDENTITY = BASE + "/" + CONFIG["identity_id"]
OUTPUT = BASE + "/" + CONFIG["silver_id"] + "/Tables/product_events"
AUDIT = IDENTITY + "/Files/validation/english_v2_silver"
POLICY = CONFIG["pii_policy_version"]
MODEL = CONFIG["pii_model"]
RUN = str(uuid.uuid4())
KEYS = ["tenant_id", "source_user_id"]
notebookutils.fs.mkdirs(AUDIT)

def empty(df, message):
    if df.limit(1).count():
        raise RuntimeError(message)

def delta_version(path):
    return int(DeltaTable.forPath(spark, path).history(1).first()["version"])

versions = {}
frames = []
raw_columns = {"event_id", "tenant_id", "source_user_id", "feature_id",
               "occurred_at", "event_type", "duration_seconds", "free_text", "text_language"}
for source in CONFIG["sources"]:
    tenant = source["tenant_id"]
    path = BRONZE + "/Tables/" + source["events_table"]
    versions[tenant] = delta_version(path)
    df = spark.read.format("delta").option("versionAsOf", versions[tenant]).load(path)
    if set(df.columns) != raw_columns:
        raise RuntimeError("Unexpected RAW event schema")
    empty(df.filter(F.col("tenant_id").isNull() | (F.col("tenant_id") != tenant)), "Tenant mismatch")
    frames.append(df)
raw = reduce(lambda a, b: a.unionByName(b), frames).cache()
if raw.limit(10001).count() > 10000:
    raise RuntimeError("This single-writer PoC is bounded to 10000 events")
for column in ["event_id", "source_user_id", "feature_id", "occurred_at", "event_type"]:
    empty(raw.filter(F.col(column).isNull() | (F.trim(F.col(column)) == "")), "Missing " + column)
empty(raw.groupBy("tenant_id", "event_id").count().filter("count > 1"), "Duplicate event")
empty(raw.filter(F.col("duration_seconds").isNull() | (F.col("duration_seconds") < 0)), "Invalid duration")
empty(raw.filter(F.col("free_text").isNotNull() & (F.col("free_text") != "") &
                 (F.col("text_language").isNull() | (F.col("text_language") != "en"))), "Expected English text")
map_path = IDENTITY + "/Tables/map_user_identity"
map_version = delta_version(map_path)
mapping = spark.read.format("delta").option("versionAsOf", map_version).load(map_path)
empty(mapping.groupBy(*KEYS).count().filter("count > 1"), "Duplicate mapping")
empty(mapping.groupBy("user_key").count().filter("count > 1"), "Duplicate pseudonymous key")
empty(mapping.filter(F.col("user_key").isNull() | (F.trim("user_key") == "")), "Empty pseudonymous key")
joined = raw.join(mapping.select(*KEYS, "user_key"), KEYS, "left").cache()
missing = joined.filter(F.col("user_key").isNull())
if missing.limit(1).count():
    missing.select("tenant_id", "event_id").withColumn("reason", F.lit("unresolved_user")).write.mode("error").json(
        AUDIT + "/rejected-" + RUN)
    raise RuntimeError("Unresolved users; entire batch held, Silver unchanged")
joined = joined.withColumn("occurred_at", F.to_timestamp("occurred_at"))
empty(joined.filter(F.col("occurred_at").isNull()), "Invalid timestamp")

fingerprint = hashlib.sha256(json.dumps({
    "source_versions": versions, "source_registry": CONFIG["sources"],
    "map_version": map_version, "policy": POLICY,
    "prompt": PROMPT, "model": MODEL,
}, sort_keys=True).encode()).hexdigest()
marker = AUDIT + "/completed-" + fingerprint + ".json"
if notebookutils.fs.exists(marker):
    previous = json.loads(notebookutils.fs.head(marker, 1000000))
    if previous["silver_delta_version"] != delta_version(OUTPUT):
        raise RuntimeError("Silver changed after the recorded batch; review required")
    print(json.dumps({"status": "already_processed", "model_calls": 0, "run_id": previous["run_id"]}))
    notebookutils.notebook.exit("Already processed; no new inference or writes")
if spark.read.format("delta").load(OUTPUT).limit(1).count():
    raise RuntimeError("This first-load PoC refuses to overwrite a populated Silver table")

documents = joined.filter(F.col("free_text").isNotNull() & (F.col("free_text") != "")).select(
    "tenant_id", "event_id", "free_text").orderBy("tenant_id", "event_id").collect()
if len(documents) > 50:
    raise RuntimeError("PoC inference bounded to 50 nonempty event texts")
evidence = {
    "run_id": RUN, "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "status": "started", "source_versions": versions, "mapping_version": map_version,
    "policy": POLICY, "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    "requested_model": MODEL, "input_rows": raw.count(), "submitted_texts": len(documents),
    "runtime_identity": "Notebook job submitter; built-in Fabric authentication",
    "security_note": "Logical separation within the same workspace; workspace administrators retain access",
}
@contextmanager
def audit_failure():
    try:
        yield
    except Exception as error:
        evidence["status"] = "failed"
        evidence["error"] = {"type": type(error).__name__, "message": str(error)}
        notebookutils.fs.put(AUDIT + "/failed-" + RUN + ".json", json.dumps(evidence, indent=2), False)
        raise


with audit_failure():
    import pandas as pd
    import synapse.ml.aifunc as aifunc
    frame = pd.DataFrame([{"text": d["free_text"]} for d in documents])
    if documents:
        responses = frame.ai.generate_response(
            prompt=PROMPT, response_format=RESPONSE_FORMAT,
            conf=aifunc.Conf(model_deployment_name=MODEL, concurrency=1, timeout=120))
        if len(responses) != len(documents) or not responses.index.equals(frame.index):
            raise RuntimeError("Response alignment mismatch")
        responses = responses.tolist()
    else:
        responses = []
    evidence["responses"] = [
        {"tenant_id": d["tenant_id"], "event_id": d["event_id"], "response": response}
        for d, response in zip(documents, responses)]
    records = []
    for d, response in zip(documents, responses):
        result = mask_response(d["free_text"], response)
        records.append((d["tenant_id"], d["event_id"], result["redacted"],
                        "processed", len(result["entities"])))
    transformed = spark.createDataFrame(records,
        "tenant_id string, event_id string, protected_text string, pii_status string, pii_entity_count long")
    staged = joined.join(transformed, ["tenant_id", "event_id"], "left")
    no_text = F.col("free_text").isNull() | (F.col("free_text") == "")
    empty(staged.filter(~no_text & F.col("protected_text").isNull()), "Missing processed text")
    staged = staged.select(
        "event_id", "tenant_id", "user_key", "feature_id", "occurred_at",
        F.to_date("occurred_at").alias("event_date"), "event_type", "duration_seconds",
        F.when(no_text, F.col("free_text")).otherwise(F.col("protected_text")).alias("free_text"),
        "text_language",
        F.when(no_text, F.lit("not_required")).otherwise(F.col("pii_status")).alias("pii_status"),
        F.coalesce(F.col("pii_entity_count"), F.lit(0)).alias("pii_entity_count"),
        F.lit(POLICY).alias("pii_policy_version"), F.lit(MODEL).alias("pii_model"),
        F.lit(RUN).alias("processing_run_id"),
    ).cache()
    assert staged.count() == raw.count()
    assert not {"source_user_id", "display_name", "email"} & set(staged.columns)

with audit_failure():
    detail_id = DeltaTable.forPath(spark, OUTPUT).detail().first()["id"]
    # Publish only after the entire batch passes structural validation.
    staged.write.format("delta").mode("append").option("mergeSchema", "true").save(OUTPUT)
    persisted = spark.read.format("delta").load(OUTPUT)
    assert persisted.count() == staged.count()
    assert not persisted.exceptAll(staged).limit(1).count()
    assert not staged.exceptAll(persisted).limit(1).count()
    assert DeltaTable.forPath(spark, OUTPUT).detail().first()["id"] == detail_id
    evidence["silver_delta_version"] = delta_version(OUTPUT)
    evidence["silver_rows"] = persisted.count()
    evidence["status"] = "completed"
    evidence["text_observations"] = [r.asDict() for r in persisted.filter(
        F.col("text_language").isNotNull()).select(
            "tenant_id", "event_id", "free_text", "pii_status", "pii_entity_count").orderBy(
                "tenant_id", "event_id").collect()]
    notebookutils.fs.put(marker, json.dumps(evidence, indent=2), False)
print(json.dumps(evidence, indent=2))
