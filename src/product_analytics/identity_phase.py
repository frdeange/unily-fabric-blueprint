
import hashlib
import json
import uuid
from datetime import datetime, timezone
from functools import reduce

import notebookutils
from delta.tables import DeltaTable
from pyspark.sql import functions as F

WORKSPACE = CONFIG["workspace_id"]
BRONZE = CONFIG["bronze_id"]
IDENTITY = CONFIG["identity_id"]
SOURCES = {source["tenant_id"]: source["users_table"] for source in CONFIG["sources"]}
BASE = f"abfss://{WORKSPACE}@onelake.dfs.fabric.microsoft.com"
MAP_PATH = f"{BASE}/{IDENTITY}/Tables/map_user_identity"
KEYS = ["tenant_id", "source_user_id"]
VALUE_COLUMNS = ["display_name", "email"]
MAP_COLUMNS = KEYS + ["user_key"] + VALUE_COLUMNS

def require_empty(df, reason):
    if df.limit(1).count():
        raise RuntimeError(reason)

def validate(df, columns, label):
    for column in columns:
        require_empty(
            df.filter(F.col(column).isNull() | (F.trim(F.col(column)) == "")),
            f"{label}: missing required field {column}",
        )
    require_empty(df.groupBy(*KEYS).count().filter("count > 1"), f"{label}: duplicate source keys")

frames = []
source_versions = {}
for tenant, table in SOURCES.items():
    path = f"{BASE}/{BRONZE}/Tables/{table}"
    version = DeltaTable.forPath(spark, path).history(1).first()["version"]
    source_versions[table] = int(version)
    raw = spark.read.format("delta").option("versionAsOf", version).load(path)
    if set(raw.columns) != set(KEYS + VALUE_COLUMNS):
        raise RuntimeError(f"Unexpected input schema: {table}")
    validate(raw, KEYS + VALUE_COLUMNS, table)
    require_empty(raw.filter(F.col("tenant_id") != tenant), "Tenant/source mismatch")
    frames.append(raw)
incoming = reduce(lambda a, b: a.unionByName(b), frames)
validate(incoming, KEYS + VALUE_COLUMNS, "incoming")

existing = spark.read.format("delta").load(MAP_PATH).select(*MAP_COLUMNS).cache()
validate(existing, MAP_COLUMNS, "mapping")
require_empty(existing.groupBy("user_key").count().filter("count > 1"), "Duplicate identity token")
require_empty(existing.filter(~F.col("tenant_id").isin(list(SOURCES))), "Unexpected mapping tenant")
before = {tuple(r[k] for k in KEYS): r["user_key"] for r in existing.select(*KEYS, "user_key").limit(10001).collect()}
if len(before) > 10000 or incoming.limit(10001).count() > 10000:
    raise RuntimeError("This single-writer A/B/C PoC is bounded to 10000 identities")

new_rows = incoming.join(existing.select(*KEYS), KEYS, "left_anti").collect()
new_records = [
    (r["tenant_id"], r["source_user_id"], str(uuid.uuid4()), r["display_name"], r["email"])
    for r in new_rows
]
new_df = spark.createDataFrame(new_records, existing.schema)
known = incoming.alias("u").join(existing.select(*KEYS, "user_key").alias("m"), KEYS).select(*MAP_COLUMNS)
staged = known.unionByName(new_df).cache()
assert staged.count() == incoming.count(), "Identity join lost or multiplied users"
require_empty(staged.groupBy("user_key").count().filter("count > 1"), "Token collision")
changed = known.alias("n").join(existing.alias("o"), KEYS).filter(
    ~F.col("n.display_name").eqNullSafe(F.col("o.display_name"))
    | ~F.col("n.email").eqNullSafe(F.col("o.email"))
).count()

# One manually launched writer only. No claim of safe concurrent onboarding.
if new_records or changed:
    DeltaTable.forPath(spark, MAP_PATH).alias("t").merge(
        staged.alias("s"),
        "t.tenant_id = s.tenant_id AND t.source_user_id = s.source_user_id",
    ).whenMatchedUpdate(
        condition="NOT (t.display_name <=> s.display_name) OR NOT (t.email <=> s.email)",
        set={"display_name": "s.display_name", "email": "s.email"},
    ).whenNotMatchedInsert(values={column: f"s.{column}" for column in MAP_COLUMNS}).execute()
existing.unpersist()
staged.unpersist()
after = spark.read.format("delta").load(MAP_PATH).select(*MAP_COLUMNS)
validate(after, MAP_COLUMNS, "persisted mapping")
require_empty(after.groupBy("user_key").count().filter("count > 1"), "Persisted token collision")
require_empty(incoming.select(*KEYS).join(after.select(*KEYS), KEYS, "left_anti"), "Missing persisted identity")
actual = {tuple(r[k] for k in KEYS): r["user_key"] for r in after.select(*KEYS, "user_key").collect()}
assert all(actual.get(k) == v for k, v in before.items()), "Existing identity token changed"
assert len(actual) == len(before) + len(new_records), "Unexpected mapping growth"
digest_rows = sorted((key[0], key[1], value) for key, value in actual.items())
evidence = {
    "run_id": str(uuid.uuid4()),
    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
    "source_versions": source_versions,
    "input_users": incoming.count(), "mapping_before": len(before),
    "new_identities": len(new_records), "updated_identity_attributes": changed,
    "mapping_after": len(actual), "existing_keys_preserved": True,
    "mapping_keys_sha256": hashlib.sha256(json.dumps(digest_rows).encode()).hexdigest(),
    "mapping_delta_version": int(DeltaTable.forPath(spark, MAP_PATH).history(1).first()["version"]),
    "writes": ["ProductIdentity.map_user_identity", "ProductIdentity.Files/validation/identity"],
    "silver_or_gold_written": False, "raw_generator_called": False,
    "concurrency": "Single manually launched writer; concurrent execution not supported in this PoC",
    "source_system_scope": "One Product user namespace per tenant in A/B/C; not cross-source resolution",
}
evidence_path = f"{BASE}/{IDENTITY}/Files/validation/identity"
notebookutils.fs.mkdirs(evidence_path)
notebookutils.fs.put(evidence_path + "/" + evidence["run_id"] + ".json", json.dumps(evidence, indent=2), False)
print(json.dumps(evidence, indent=2))
