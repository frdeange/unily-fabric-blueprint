"""Build a synthetic source notebook. It writes raw Bronze inputs only."""

import inspect
import json
import random
from collections import Counter
from datetime import datetime, timedelta


TENANTS = [
    ("tenant_a", "Example Company A", "ES", 12),
    ("tenant_b", "Example Company B", "UK", 18),
    ("tenant_c", "Example Company C", "DE", 24),
]
FEATURES = [
    ("news", "News", "Communications"),
    ("search", "Search", "Discovery"),
    ("knowledge", "Knowledge", "Collaboration"),
    ("community", "Community", "Collaboration"),
]
FIXTURE_VERSION = "abc-english-v2"
RAW_TEXT_CASES = {
    "en": [
        "Contact Alex Morgan at user001@{domain}.example.invalid.",
        "Contact phone: +1 202-555-0147.",
        "Send to user001@{domain}.example.invalid; copy user001@{domain}.example.invalid.",
        "Search does not return the help article.",
        "Please update my employee record. I live at 42 Example Road, London SW1A 1AA. My UK passport number is 123456789 and my National Insurance number is QQ123456C.",
        "Please update my details. My address is Musterstrasse 17, 10115 Berlin. My German national identity number is L01X00T47 and my passport number is C01X00T47.",
        "Please update my record. My address is 18 rue Exemple, 75001 Paris. My French social security number is 1 85 05 75 123 456 78 and my passport number is 12AB34567.",
        "I moved to 24 Voorbeeldstraat, 1012 AB Amsterdam. My Dutch BSN is 123456782. Please use my passport number NX1234567 when updating the travel request.",
        "Please update my profile. My address is Calle Ejemplo 25, 28013 Madrid. My Spanish national identity number is 12345678Z and my passport number is AAA123456. The ticket reference is INC-48271.",
        "",
        None,
    ],
}


def add_raw_text(events):
    language_by_tenant = {tenant[0]: "en" for tenant in TENANTS}
    counts = {tenant: 0 for tenant in language_by_tenant}
    result = []
    for event in events:
        tenant = event[1]
        language = language_by_tenant[tenant]
        text, text_language = None, None
        if event[4].startswith("2026-09"):
            index = counts[tenant]
            if index < len(RAW_TEXT_CASES[language]):
                template = RAW_TEXT_CASES[language][index]
                text = template.format(domain=tenant.replace("_", "-")) if template is not None else None
                text_language = language
            counts[tenant] += 1
        result.append((*event, text, text_language))
    return result


def generate_data():
    rng = random.Random(20261002)
    users, events = [], []
    for tenant_index, (tenant_id, _, _, user_count) in enumerate(TENANTS):
        for user_index in range(1, user_count + 1):
            source_id = f"user{user_index:03d}"
            # Preserve the original event fixture's RNG sequence without generating identity keys.
            rng.getrandbits(128)
            name = "Alex Morgan" if user_index == 1 else f"Test User {user_index:03d}"
            email = f"{source_id}@{tenant_id.replace('_', '-')}.example.invalid"
            users.append((tenant_id, source_id, name, email))
            for month in (8, 9):
                for day in range(1, 29):
                    for repetition in range(1 + (user_index + day + tenant_index) % 3):
                        feature = FEATURES[(user_index + day + repetition) % len(FEATURES)][0]
                        timestamp = datetime(2026, month, day, 9) + timedelta(minutes=user_index + repetition)
                        events.append((
                            f"event{len(events) + 1:06d}", tenant_id, source_id, feature,
                            timestamp.isoformat(), "view", 10 + rng.randrange(291),
                        ))
    return users, add_raw_text(events)


def expected_results(users, events):
    profiles = {
        "UnilyGlobalAnalyst": {"tenants": ["tenant_a", "tenant_b", "tenant_c"], "identity": False},
        "UnilyGlobalOperator": {"tenants": ["tenant_a", "tenant_b", "tenant_c"], "identity": True},
        "UnilyAnalystAB": {"tenants": ["tenant_a", "tenant_b"], "identity": False},
        "UnilyOperatorAB": {"tenants": ["tenant_a", "tenant_b"], "identity": True},
        "ClientAAnalyst": {"tenants": ["tenant_a"], "identity": False},
        "ClientAOperator": {"tenants": ["tenant_a"], "identity": True},
        "ClientBAnalyst": {"tenants": ["tenant_b"], "identity": False},
    }
    for profile in profiles.values():
        allowed = set(profile["tenants"])
        visible = [e for e in events if e[1] in allowed and e[4].startswith("2026-09")]
        profile["september_events"] = len(visible)
        profile["september_active_users"] = len({(e[1], e[2]) for e in visible})
        profile["visible_tenant_names"] = [t[1] for t in TENANTS if t[0] in allowed]
    return {
        "synthetic_only": True,
        "fixture_version": FIXTURE_VERSION,
        "purpose": "Reference expectations, not proof of populated downstream tables",
        "period": "2026-09",
        "raw_users": len(users),
        "raw_events": len(events),
        "profiles": profiles,
        "september_events_by_tenant": dict(Counter(e[1] for e in events if e[4].startswith("2026-09"))),
        "authorization_validated": False,
    }


def split_source_rows(rows, tenant_index):
    partitions = {t[0]: [] for t in TENANTS}
    for row in rows:
        tenant = row[tenant_index]
        if tenant not in partitions:
            raise ValueError(f"Unknown tenant: {tenant}")
        partitions[tenant].append(row)
    return partitions


SPARK_SOURCE = '''
if not CONFIG["allow_synthetic_overwrite"]:
    raise RuntimeError("Synthetic RAW overwrite is disabled in runtime configuration")
if {source["tenant_id"] for source in CONFIG["sources"]} != {tenant[0] for tenant in TENANTS}:
    raise RuntimeError("The synthetic generator supports only the versioned A/B/C fixture")

from pyspark.sql import functions as F

users, event_rows = generate_data()

def location(table):
    return f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{BRONZE_ID}/Tables/{table}"

user_schema = "tenant_id string, source_user_id string, display_name string, email string"
event_schema = "event_id string, tenant_id string, source_user_id string, feature_id string, occurred_at string, event_type string, duration_seconds long, free_text string, text_language string"
user_sources = split_source_rows(users, 0)
event_sources = split_source_rows(event_rows, 1)
bronze_evidence = {}
for tenant_id, _, _, _ in TENANTS:
    source = next(source for source in CONFIG["sources"] if source["tenant_id"] == tenant_id)
    raw_users = spark.createDataFrame(user_sources[tenant_id], user_schema)
    raw_events = spark.createDataFrame(event_sources[tenant_id], event_schema)
    bronze_evidence[tenant_id] = {}
    for name, df in (("users", raw_users), ("events", raw_events)):
        landing = f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{BRONZE_ID}/Files/landing/{tenant_id}/product/{name}"
        df.write.mode("overwrite").json(landing)
        landed = spark.read.schema(df.schema).json(landing)
        assert landed.filter(F.col("tenant_id") != tenant_id).count() == 0
        path = location(source["users_table"] if name == "users" else source["events_table"])
        # Additive fixture schema evolution only; do not replace existing schemas.
        landed.write.format("delta").mode("overwrite").option("mergeSchema", "true").save(path)
        persisted = spark.read.format("delta").load(path)
        assert persisted.exceptAll(df).limit(1).count() == 0
        assert df.exceptAll(persisted).limit(1).count() == 0
        bronze_evidence[tenant_id][name] = persisted.count()
    bronze_evidence[tenant_id]["text_cases"] = [
        row.asDict() for row in spark.read.format("delta").load(
            location(source["events_table"])
        ).filter(F.col("text_language").isNotNull()).select(
            "event_id", "free_text", "text_language"
        ).orderBy("event_id").collect()
    ]

evidence = {
    "purpose": "Synthetic raw inputs only; no downstream processing",
    "synthetic_only": True,
    "fixture_version": FIXTURE_VERSION,
    "raw_events": len(event_rows),
    "raw_users": len(users),
    "bronze_separate_sources": bronze_evidence,
}
spark.createDataFrame([(json.dumps(evidence, sort_keys=True),)], "value string").coalesce(1).write.mode("overwrite").text(
    f"abfss://{WORKSPACE_ID}@onelake.dfs.fabric.microsoft.com/{BRONZE_ID}/Files/validation/{FIXTURE_VERSION}"
)
print(json.dumps(evidence, indent=2))
'''


def notebook_source():
    return (
        "import json\nimport random\nfrom datetime import datetime, timedelta\n"
        'WORKSPACE_ID = CONFIG["workspace_id"]\nBRONZE_ID = CONFIG["bronze_id"]\n'
        f"TENANTS = {TENANTS!r}\nFEATURES = {FEATURES!r}\n"
        f"FIXTURE_VERSION = {FIXTURE_VERSION!r}\nRAW_TEXT_CASES = {RAW_TEXT_CASES!r}\n\n"
        + inspect.getsource(add_raw_text) + "\n" + inspect.getsource(generate_data) + "\n"
        + inspect.getsource(split_source_rows) + SPARK_SOURCE
    )


if __name__ == "__main__":
    raise SystemExit("Generate notebooks with python tools\\build_notebooks.py from the repository root.")
