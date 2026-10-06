import base64
import json
import shutil
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from deploy_environment import deploy, find_item, verify_inventory
from environment import workspace_name, workspace_names
from fabric_api import find_workspace, operation_endpoint, wait_operation
from prepare_deployment import (DEFAULT_WORKSPACE, ID_FIELDS, ITEMS, check_scope, load_settings, prepare,
                                runtime_values, variables_definition)


def values():
    return runtime_values(load_settings(ROOT, "dev"), {name: str(uuid.uuid4()) for name in ID_FIELDS})


class FakeFabric:
    """In-memory Fabric: workspaces by name, items, definitions and lakehouse endpoints."""

    def __init__(self, schema_enabled=True):
        self.workspaces = [{"displayName": n, "id": str(uuid.uuid4())} for n in workspace_names("dev").values()]
        self.items = {w["id"]: [] for w in self.workspaces}
        self.definitions = {}
        self.schema_enabled = schema_enabled
        self.published = []

    def list_all(self, credential, path):
        if path == "workspaces":
            return self.workspaces
        return list(self.items[path.split("/")[1]])

    def call(self, credential, path, body=None, method=None):
        parts = path.split("/")
        item = parts[3]
        if path.endswith("getDefinition") or "getDefinition?" in path:
            file, content = self.definitions[item]
            return {"definition": {"parts": [{"path": file, "payload": base64.b64encode(content).decode()}]}}
        if parts[2] == "lakehouses":
            return {"properties": {"defaultSchema": "dbo"} if self.schema_enabled else {}}
        return {"properties": {"activeValueSetName": "dev"}}

    def publish(self, workspace, directory, kinds):
        self.published.append((workspace, tuple(kinds)))
        logical = {}
        for folder in directory.iterdir():
            name, kind = folder.name.rsplit(".", 1)
            assert kind in kinds
            existing = find_item(self.items[workspace], name, kind)
            if not existing:
                existing = {"displayName": name, "type": kind, "id": str(uuid.uuid4())}
                self.items[workspace].append(existing)
                if kind == "Lakehouse":
                    self.items[workspace].append({"displayName": name, "type": "SQLEndpoint", "id": str(uuid.uuid4())})
            logical[json.loads((folder / ".platform").read_text())["config"]["logicalId"]] = existing["id"]
        # Like fabric-cicd: resolve logical IDs within this publication and the workspace placeholder.
        for folder in directory.iterdir():
            name, kind = folder.name.rsplit(".", 1)
            file = {"Notebook": "notebook-content.ipynb", "VariableLibrary": "variables.json",
                    "DataPipeline": "pipeline-content.json"}.get(kind)
            if file:
                content = (folder / file).read_text()
                if kind == "DataPipeline":
                    for old, new in logical.items():
                        content = content.replace(old, new)
                    content = content.replace(DEFAULT_WORKSPACE, workspace)
                self.definitions[find_item(self.items[workspace], name, kind)["id"]] = (file, content.encode())

    def run(self):
        with patch("deploy_environment.list_all", self.list_all), patch("deploy_environment.call", self.call):
            return deploy(Mock(), "dev", self.publish)

    def workspace(self, layer):
        return find_workspace(self.workspaces, workspace_name(layer, "dev"))["id"]


class NamingTests(unittest.TestCase):
    def test_workspace_names_follow_convention(self):
        self.assertEqual(workspace_names("dev"), {
            "data": "Unily-Data-Dev", "analytics": "Unily-Analytics-Dev", "vault": "Unily-Vault-Dev"})
        with self.assertRaises(ValueError):
            workspace_name("gold", "dev")


class FabricApiTests(unittest.TestCase):
    def test_regional_operation_location_uses_canonical_host(self):
        operation = str(uuid.uuid4())
        regional = f"https://regional.example.invalid/v1/operations/{operation}"
        expected = f"https://api.fabric.microsoft.com/v1/operations/{operation}"
        self.assertEqual(operation_endpoint({"x-ms-operation-id": operation, "Location": regional}), expected)
        self.assertEqual(operation_endpoint({"Location": regional}), expected)
        with self.assertRaises(ValueError):
            operation_endpoint({"x-ms-operation-id": "invalid"})
        with self.assertRaises(ValueError):
            operation_endpoint({"Location": "https://example.invalid/arbitrary"})

    @patch("fabric_api.time.sleep")
    @patch("fabric_api.call")
    def test_operation_polling_and_result(self, read, sleep):
        endpoint = operation_endpoint({"x-ms-operation-id": str(uuid.uuid4())})
        read.side_effect = [{"status": "Running"}, {"status": "Succeeded"}, {"definition": {}}]
        self.assertEqual(wait_operation(Mock(), endpoint, 1), {"definition": {}})
        self.assertEqual(read.call_args.args[1], endpoint + "/result")
        read.side_effect = [{"status": "Succeeded"}, RuntimeError("HTTP 404")]
        self.assertEqual(wait_operation(Mock(), endpoint, 1), {})
        read.side_effect = [{"status": "Succeeded"}, RuntimeError("HTTP 403")]
        with self.assertRaisesRegex(RuntimeError, "403"):
            wait_operation(Mock(), endpoint, 1)
        read.side_effect = [{"status": "Failed"}]
        with self.assertRaisesRegex(RuntimeError, "operation failed"):
            wait_operation(Mock(), endpoint, 1)

    def test_workspace_lookup_is_exact(self):
        workspaces = [{"displayName": "Unily-Data-Dev", "id": "1"}]
        self.assertEqual(find_workspace(workspaces, "Unily-Data-Dev")["id"], "1")
        with self.assertRaises(RuntimeError):
            find_workspace(workspaces, "Unily-Vault-Dev")
        with self.assertRaises(ValueError):
            find_workspace(workspaces * 2, "Unily-Data-Dev")


class StagingTests(unittest.TestCase):
    def test_repository_scope_and_settings_are_valid(self):
        check_scope(ROOT)
        settings = load_settings(ROOT, "dev")
        self.assertFalse(settings["allow_synthetic_overwrite"])
        self.assertFalse(set(ID_FIELDS) & set(settings))
        with self.assertRaises(ValueError):
            load_settings(ROOT, "prod")

    def test_stages_are_exact_scope_and_do_not_modify_checkout(self):
        template = ROOT / "fabric" / "data" / "product-analytics" / "variable-libraries" / "ProductAnalytics_Config.VariableLibrary" / "variables.json"
        original = template.read_bytes()
        with tempfile.TemporaryDirectory() as directory:
            vault = Path(directory) / "vault"
            prepare(ROOT, vault, "vault", ("Lakehouse",), "dev")
            self.assertEqual({p.name for p in vault.iterdir()}, {"Identity.Lakehouse"})
            config = Path(directory) / "config"
            current = values()
            prepare(ROOT, config, "data", ("VariableLibrary", "Notebook", "DataPipeline"), "dev", current)
            self.assertEqual({p.name for p in config.iterdir()}, {
                "ProductAnalytics_Config.VariableLibrary", "ProductAnalytics_Build.Notebook",
                "ProductAnalytics_BronzeToSilver.Notebook", "ProductAnalytics_SilverToGold.Notebook",
                "ProductAnalytics_SilverPipeline.DataPipeline", "ProductAnalytics_GoldPipeline.DataPipeline",
                "ProductAnalytics_Demo.DataPipeline"})
            library = config / "ProductAnalytics_Config.VariableLibrary"
            self.assertEqual(json.loads((library / "variables.json").read_text()), variables_definition(current))
            self.assertEqual(json.loads((library / "settings.json").read_text())["valueSetsOrder"], ["dev"])
        self.assertEqual(template.read_bytes(), original)

    def test_unsafe_staging_fails_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "items"
            kinds = ("VariableLibrary", "Notebook", "DataPipeline")
            for args in (({**values(), "allow_synthetic_overwrite": True}, "dev"), (values(), "prod"), (None, "dev")):
                with self.assertRaises(ValueError):
                    prepare(ROOT, target, "data", kinds, args[1], args[0])
                self.assertFalse(target.exists())
            with self.assertRaises(ValueError):
                prepare(ROOT, ROOT / "private-stage", "vault", ("Lakehouse",), "dev")


class DeploymentTests(unittest.TestCase):
    def test_first_deployment_creates_items_in_the_right_workspaces(self):
        fabric = FakeFabric()
        fabric.run()
        data, vault, analytics = (fabric.workspace(layer) for layer in ("data", "vault", "analytics"))
        self.assertEqual(fabric.published, [
            (vault, ("Lakehouse",)), (data, ("Lakehouse",)), (data, ("VariableLibrary", "Notebook", "DataPipeline"))])
        self.assertEqual({i["displayName"] for i in fabric.items[vault] if i["type"] == "Lakehouse"}, {"Identity"})
        self.assertEqual(fabric.items[analytics], [])
        library = find_item(fabric.items[data], "ProductAnalytics_Config", "VariableLibrary")
        deployed = {v["name"]: v["value"] for v in json.loads(fabric.definitions[library["id"]][1])["variables"]}
        self.assertEqual(deployed["data_workspace_id"], data)
        self.assertEqual(deployed["vault_workspace_id"], vault)
        self.assertEqual(deployed["identity_id"], find_item(fabric.items[vault], "Identity", "Lakehouse")["id"])
        self.assertEqual(deployed["bronze_id"], find_item(fabric.items[data], "Bronze", "Lakehouse")["id"])
        self.assertFalse(deployed["allow_synthetic_overwrite"])
        demo = json.loads(fabric.definitions[find_item(fabric.items[data], "ProductAnalytics_Demo", "DataPipeline")["id"]][1])
        build, silver, gold = demo["properties"]["activities"]
        self.assertEqual(build["typeProperties"]["notebookId"],
                         find_item(fabric.items[data], "ProductAnalytics_Build", "Notebook")["id"])
        self.assertEqual(build["typeProperties"]["workspaceId"], data)
        self.assertEqual(silver["typeProperties"]["pipeline"]["referenceName"],
                         find_item(fabric.items[data], "ProductAnalytics_SilverPipeline", "DataPipeline")["id"])
        self.assertEqual(gold["typeProperties"]["pipeline"]["referenceName"],
                         find_item(fabric.items[data], "ProductAnalytics_GoldPipeline", "DataPipeline")["id"])

    def test_changed_pipeline_readback_is_rejected(self):
        fabric = FakeFabric()
        original = fabric.publish

        def tampered(workspace, directory, kinds):
            original(workspace, directory, kinds)
            for item in fabric.items[workspace]:
                if item["type"] == "DataPipeline" and item["displayName"] == "ProductAnalytics_SilverPipeline":
                    file, content = fabric.definitions[item["id"]]
                    fabric.definitions[item["id"]] = (file, content.replace(b'"Validate"', b'"Skipped"'))
        fabric.publish = tampered
        with self.assertRaisesRegex(RuntimeError, "Pipeline definition readback mismatch"):
            fabric.run()

    def test_pipeline_referencing_another_layer_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "fabric", root / "fabric")
            content = root / "fabric" / "data" / "product-analytics" / "pipelines" / "ProductAnalytics_SilverPipeline.DataPipeline" / "pipeline-content.json"
            identity = "00000000-0000-4000-8000-000000000012"
            content.write_text(content.read_text().replace("00000000-0000-4000-8000-000000000007", identity))
            with self.assertRaisesRegex(ValueError, "outside its layer"):
                check_scope(root)

    def test_redeployment_preserves_ids(self):
        fabric = FakeFabric()
        fabric.run()
        before = {w: list(items) for w, items in fabric.items.items()}
        fabric.run()
        self.assertEqual(fabric.items, before)

    def test_missing_workspace_fails_before_publishing(self):
        fabric = FakeFabric()
        fabric.workspaces = fabric.workspaces[:2]
        with self.assertRaises(RuntimeError):
            fabric.run()
        self.assertEqual(fabric.published, [])

    def test_lakehouse_without_schemas_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "not schema-enabled"):
            FakeFabric(schema_enabled=False).run()

    def test_unexpected_or_changed_items_are_rejected(self):
        layer, name = "vault", "Identity"
        before = [{"displayName": name, "type": "Lakehouse", "id": "a"}]
        verify_inventory(layer, before, before + [{"displayName": name, "type": "SQLEndpoint", "id": "b"}])
        with self.assertRaisesRegex(RuntimeError, "identity changed"):
            verify_inventory(layer, before, [{"displayName": name, "type": "Lakehouse", "id": "c"}])
        with self.assertRaisesRegex(RuntimeError, "Unexpected item"):
            verify_inventory(layer, before, before + [{"displayName": "Other", "type": "Notebook", "id": "d"}])
        with self.assertRaises(ValueError):
            find_item([{"displayName": name, "type": "Notebook", "id": "e"}], name, "Lakehouse")


if __name__ == "__main__":
    unittest.main()
