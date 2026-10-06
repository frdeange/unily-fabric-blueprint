import base64
import copy
import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from prepare_product_deployment import ITEMS, prepare, variables_definition
from deploy_product import find_item, verify_readback


def config():
    values = json.loads((ROOT / "config" / "product-analytics.example.json").read_text())
    for name in ("workspace_id", "bronze_id", "silver_id", "identity_id"):
        values[name] = str(uuid.uuid4())
    return values


class ProductDeploymentTests(unittest.TestCase):
    def test_staging_is_exact_scope_and_does_not_modify_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "items"
            values = config()
            template = ROOT / "fabric" / "product-analytics" / "variable-libraries" / "ProductAnalytics_Config.VariableLibrary" / "variables.json"
            original = template.read_bytes()
            prepare(ROOT, target, values, "dev")
            self.assertEqual({p.name for p in target.iterdir()}, {f"{n}.{t}" for n, (t, _) in ITEMS.items()})
            self.assertEqual(template.read_bytes(), original)
            library = target / "ProductAnalytics_Config.VariableLibrary"
            self.assertEqual(json.loads((library / "variables.json").read_text()), variables_definition(values))
            self.assertEqual(json.loads((library / "settings.json").read_text())["valueSetsOrder"], ["dev"])
            self.assertEqual(json.loads((library / "valueSets" / "dev.json").read_text())["variableOverrides"], [])

    def test_unsafe_staging_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "items"
            for values, environment in (({**config(), "allow_synthetic_overwrite": True}, "dev"), (config(), "prod")):
                with self.assertRaises(ValueError):
                    prepare(ROOT, target, values, environment)
                self.assertFalse(target.exists())
            with self.assertRaises(ValueError):
                prepare(ROOT, ROOT / "private-stage", config(), "dev")

    def test_ambiguous_or_wrong_type_target_is_rejected(self):
        with self.assertRaises(ValueError):
            find_item([{"displayName": "target", "type": "Lakehouse"}], "target", "Notebook")
        with self.assertRaises(ValueError):
            find_item([{"displayName": "target", "type": "Notebook"}] * 2, "target", "Notebook")
        with self.assertRaises(RuntimeError):
            find_item([], "target", "Notebook", required=True)

    def test_readback_checks_definitions_ids_and_active_set(self):
        values = config()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "items"
            prepare(ROOT, target, values, "dev")
            before = [{"displayName": n, "type": t, "id": str(uuid.uuid4())} for n, (t, _) in ITEMS.items()]
            responses = []
            for name, (kind, _) in ITEMS.items():
                folder = target / f"{name}.{kind}"
                file = "notebook-content.ipynb" if kind == "Notebook" else "variables.json"
                responses.append({"definition": {"parts": [{"path": file, "payload": base64.b64encode((folder / file).read_bytes()).decode()}]}})
                if kind == "VariableLibrary":
                    responses.append({"properties": {"activeValueSetName": "dev"}})
            with patch("deploy_product.read_api", side_effect=copy.deepcopy(responses)):
                verify_readback(Mock(), values["workspace_id"], before, before, target, values)
            changed = copy.deepcopy(before)
            changed[0]["id"] = str(uuid.uuid4())
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                verify_readback(Mock(), values["workspace_id"], before, changed, target, values)
            responses[-1]["properties"]["activeValueSetName"] = "Default value set"
            with patch("deploy_product.read_api", side_effect=responses), self.assertRaisesRegex(RuntimeError, "not active"):
                verify_readback(Mock(), values["workspace_id"], before, before, target, values)


if __name__ == "__main__":
    unittest.main()
