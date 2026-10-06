"""Read-only Spark/runtime preflight, embedded before processing phases."""

def validate_runtime(config, spark_session):
    import pandas
    import synapse.ml.aifunc
    from delta.tables import DeltaTable

    data, vault = config["data_workspace_id"], config["vault_workspace_id"]
    users = {"tenant_id", "source_user_id", "display_name", "email"}
    events = {"event_id", "tenant_id", "source_user_id", "feature_id", "occurred_at",
              "event_type", "duration_seconds", "free_text", "text_language"}
    inputs = []
    for source in config["sources"]:
        inputs.extend([
            (data, config["bronze_id"], source["users_table"], users, True),
            (data, config["bronze_id"], source["events_table"], events, True),
        ])
    # Outputs may be absent before the first run; processing creates them once.
    inputs.extend([
        (vault, config["identity_id"], "user_identity_map", users | {"user_key"}, False),
        (data, config["silver_id"], "usage_events", {
            "event_id", "tenant_id", "user_key", "feature_id", "occurred_at",
            "event_date", "event_type", "duration_seconds", "free_text", "text_language",
            "pii_status", "pii_entity_count", "pii_policy_version", "pii_model",
            "processing_run_id",
        }, False),
    ])
    observations = []
    for workspace, lakehouse, table, expected, required in inputs:
        path = onelake_table(workspace, lakehouse, table)
        if not DeltaTable.isDeltaTable(spark_session, path):
            if required:
                raise RuntimeError(f"Required input table is missing: {table}")
            observations.append({"table": table, "status": "absent_until_first_run"})
            continue
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
