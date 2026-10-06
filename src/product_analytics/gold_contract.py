"""Gold star-schema contract; pure Python so tests and docs can check it without Spark."""

# Every table carries tenant_id (except the shared calendar and feature catalog) for RLS.
GOLD_TABLES = {
    "fact_usage_event": (
        ("tenant_id", "string"), ("event_id", "string"), ("user_key", "string"),
        ("feature_id", "string"), ("event_date", "date"), ("occurred_at", "timestamp"),
        ("event_type", "string"), ("duration_seconds", "long"),
        ("feedback_text", "string"), ("has_feedback_text", "boolean"),
        ("pii_status", "string"), ("silver_version", "long"),
    ),
    "dim_user": (
        ("tenant_id", "string"), ("user_key", "string"),
        ("first_seen_date", "date"), ("last_seen_date", "date"), ("event_count", "long"),
    ),
    "dim_feature": (
        ("feature_id", "string"), ("feature_name", "string"), ("feature_category", "string"),
    ),
    "dim_tenant": (("tenant_id", "string"),),
    "dim_date": (
        ("date", "date"), ("year", "int"), ("quarter", "int"), ("month", "int"),
        ("month_name", "string"), ("day", "int"), ("day_of_week", "int"),
        ("day_name", "string"), ("iso_week", "int"), ("is_weekend", "boolean"),
    ),
}
GOLD_KEYS = {
    "fact_usage_event": ("tenant_id", "event_id"),
    "dim_user": ("tenant_id", "user_key"),
    "dim_feature": ("feature_id",),
    "dim_tenant": ("tenant_id",),
    "dim_date": ("date",),
}
# Versioned reference catalog; an unknown Silver feature_id stops the Gold run.
FEATURE_CATALOG = (
    ("news", "News", "Communications"),
    ("search", "Search", "Discovery"),
    ("knowledge", "Knowledge", "Collaboration"),
    ("community", "Community", "Collaboration"),
)
# Direct identifiers and raw text never reach Gold.
FORBIDDEN_COLUMNS = {"source_user_id", "display_name", "email", "free_text"}
GOLD_STATE = "state/silver-to-gold.json"


def gold_schema(table):
    return ", ".join(f"{name} {kind}" for name, kind in GOLD_TABLES[table])
