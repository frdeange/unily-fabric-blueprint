import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "product_analytics"
sys.path.insert(0, str(SOURCE))
import build_product_analytics
from gold_contract import FEATURE_CATALOG, FORBIDDEN_COLUMNS, GOLD_KEYS, GOLD_TABLES, gold_schema

TENANT_SCOPED = {"fact_usage_event", "dim_user", "dim_tenant"}


class GoldContractTests(unittest.TestCase):
    def test_star_schema_tables_and_keys(self):
        self.assertEqual(set(GOLD_TABLES), {"fact_usage_event", "dim_user", "dim_feature", "dim_tenant", "dim_date"})
        self.assertEqual(set(GOLD_KEYS), set(GOLD_TABLES))
        for table, columns in GOLD_TABLES.items():
            names = [name for name, _ in columns]
            self.assertEqual(len(names), len(set(names)), table)
            self.assertTrue(set(GOLD_KEYS[table]) <= set(names), table)
            self.assertTrue(set(GOLD_KEYS[table]) <= set(names[:len(GOLD_KEYS[table])]), table)

    def test_tenant_scoped_tables_support_row_level_security(self):
        for table in TENANT_SCOPED:
            self.assertEqual(GOLD_TABLES[table][0], ("tenant_id", "string"))
            self.assertIn("tenant_id", GOLD_KEYS[table])

    def test_no_direct_identifiers_or_raw_text(self):
        self.assertTrue({"source_user_id", "display_name", "email", "free_text"} <= FORBIDDEN_COLUMNS)
        for table, columns in GOLD_TABLES.items():
            self.assertFalse(FORBIDDEN_COLUMNS & {name for name, _ in columns}, table)
        fact = dict(GOLD_TABLES["fact_usage_event"])
        self.assertEqual(fact["feedback_text"], "string")
        self.assertEqual(fact["has_feedback_text"], "boolean")

    def test_feature_catalog_covers_the_fixture(self):
        self.assertEqual(set(build_product_analytics.FEATURES), set(FEATURE_CATALOG))
        self.assertEqual(len({feature for feature, _, _ in FEATURE_CATALOG}), len(FEATURE_CATALOG))

    def test_schema_string_matches_contract(self):
        self.assertEqual(gold_schema("dim_tenant"), "tenant_id string")
        self.assertTrue(gold_schema("fact_usage_event").startswith("tenant_id string, event_id string"))

    def test_documented_contract_matches_code(self):
        text = (ROOT / "docs" / "gold-contract.md").read_text(encoding="utf-8")
        documented = {}
        for section in re.split(r"^### ", text, flags=re.M)[1:]:
            table = re.match(r"`(\w+)`", section).group(1)
            documented[table] = tuple(re.findall(r"^\| `(\w+)` \| (\w+) \|", section, flags=re.M))
        self.assertEqual(documented, GOLD_TABLES)

    def test_gold_phase_is_incremental_and_never_touches_vault(self):
        gold = (SOURCE / "gold_phase.py").read_text(encoding="utf-8")
        for forbidden in ("vault_workspace_id", "identity_id", "abfss://", 'mode("overwrite")', ".mode(\"append\")"):
            self.assertNotIn(forbidden, gold)
        for required in ('option("readChangeFeed", "true")', ".merge(", 'mode("errorifexists")',
                         "notebookutils.notebook.exit", "Unprotected text in Silver"):
            self.assertIn(required, gold)
        # The watermark advances only after the row-count verification.
        self.assertLess(gold.index("Gold facts do not match"), gold.index("notebookutils.fs.put(STATE"))

    def test_silver_enables_change_data_feed_before_publication(self):
        silver = (SOURCE / "silver_phase.py").read_text(encoding="utf-8")
        self.assertIn("delta.enableChangeDataFeed = true", silver)
        self.assertLess(silver.index("delta.enableChangeDataFeed = true"), silver.index('mode("append")'))
        self.assertIn('!= "SET TBLPROPERTIES"', silver)


if __name__ == "__main__":
    unittest.main()
