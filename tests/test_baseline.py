import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
sys.path.insert(0, str(ROOT / "tools"))

from build_product_analytics import TENANTS, generate_data, notebook_source
from build_notebooks import sources


class BaselineTests(unittest.TestCase):
    def test_raw_contract(self):
        users, events = generate_data()
        self.assertEqual((users, events), generate_data())
        self.assertEqual(len(users), 54)
        self.assertEqual(Counter(e[1] for e in events),
                         {"tenant_a": 1344, "tenant_b": 2016, "tenant_c": 2688})
        keys = {(u[0], u[1]) for u in users}
        self.assertTrue(all((e[1], e[2]) in keys for e in events))
        self.assertEqual({e[8] for e in events if e[8]}, {"en"})
        self.assertEqual(sum(bool(e[7]) for e in events), 27)
        self.assertEqual([t[1] for t in TENANTS],
                         ["Example Company A", "Example Company B", "Example Company C"])

    def test_generator_has_no_downstream_logic(self):
        source = notebook_source()
        for forbidden in ("user_key", "gold_", "user_identity_map", "vault_workspace_id"):
            self.assertNotIn(forbidden, source)

    def test_operational_notebook_is_self_contained(self):
        source = sources()["ProductAnalytics_BronzeToSilver"]
        compile(source, "<silver>", "exec")
        self.assertLess(source.index("new_records ="), source.index("documents = joined"))
        self.assertNotIn("notebookutils.notebook.run", source)
        self.assertIn('"model_calls": 0', source)
        self.assertIn("This first-load PoC refuses to overwrite", source)
        self.assertIn("Unresolved users; entire batch held", source)
        self.assertNotIn("table.delete()", source)

    def test_example_notebooks_refuse_execution(self):
        for name, source in sources().items():
            with self.subTest(notebook=name):
                self.assertIn("Example configuration only", source)


if __name__ == "__main__":
    unittest.main()
