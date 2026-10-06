"""Read-only Spark/runtime preflight, embedded before processing phases."""

def validate_runtime(config, spark_session):
    import pandas
    import synapse.ml.aifunc
    from delta.tables import DeltaTable

    base = f'abfss://{config["workspace_id"]}@onelake.dfs.fabric.microsoft.com'
    users = {"tenant_id", "source_user_id", "display_name", "email"}
    events = {"event_id", "tenant_id", "source_user_id", "feature_id", "occurred_at",
              "event_type", "duration_seconds", "free_text", "text_language"}
    inputs = []
    for source in config["sources"]:
        inputs.extend([
            (config["bronze_id"], source["users_table"], users),
            (config["bronze_id"], source["events_table"], events),
        ])
    inputs.extend([
        (config["identity_id"], "map_user_identity", users | {"user_key"}),
        (config["silver_id"], "product_events", {
            "event_id", "tenant_id", "user_key", "feature_id", "occurred_at",
            "event_date", "event_type", "duration_seconds", "free_text", "text_language",
            "pii_status", "pii_entity_count", "pii_policy_version", "pii_model",
            "processing_run_id",
        }),
    ])
    observations = []
    for lakehouse, table, expected in inputs:
        path = f"{base}/{lakehouse}/Tables/{table}"
        version = int(DeltaTable.forPath(spark_session, path).history(1).first()["version"])
        frame = spark_session.read.format("delta").option("versionAsOf", version).load(path)
        if set(frame.columns) != expected:
            raise RuntimeError(f"Runtime validation schema mismatch: {table}")
        rows = frame.count()
        after = int(DeltaTable.forPath(spark_session, path).history(1).first()["version"])
        if version != after:
            raise RuntimeError(f"Table changed during runtime validation: {table}")
        observations.append({"table": table, "delta_version": version, "rows": rows})
    return {
        "status": "runtime_validated", "tables": observations,
        "model_calls": 0, "data_writes": 0,
        "scope": "Library read, imports and Delta snapshot reads; no AI inference or audit writes",
    }
