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
from environment import gold_connection_name, workspace_name, workspace_names
from fabric_api import (POWERBI_API, POWERBI_SCOPE, find_workspace, operation_endpoint, refresh_model, send,
                        wait_operation)
from prepare_deployment import (DATA_WORKSPACE_PLACEHOLDER, DEFAULT_WORKSPACE, GOLD_PLACEHOLDER, ID_FIELDS, ITEMS,
                                MODEL_NAME, ONELAKE, check_model, check_scope, item_folder, load_settings,
                                model_summary, prepare, read_parts, runtime_values, variables_definition)


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
        self.connection = {"displayName": gold_connection_name("dev"), "id": str(uuid.uuid4()),
                           "connectivityType": "ShareableCloud", "connectionDetails": None}
        self.bindings, self.takeovers, self.refreshes = {}, [], []
        self.bind_persists, self.refresh_error = True, None

    def source(self, model):
        summary = model_summary({f: c.decode() for f, c in self.definitions[model].items()})
        return {"type": "AzureDataLakeStorage", "path": summary["sources"][0] + "/"}

    def list_all(self, credential, path):
        if path == "workspaces":
            return self.workspaces
        if path == "connections":
            if self.connection is None:
                return []
            model = next(i for items in self.items.values() for i in items if i["type"] == "SemanticModel")
            return [{**self.connection, "connectionDetails": self.connection["connectionDetails"]
                     or self.source(model["id"])}]
        if path.endswith("/connections"):
            model = path.split("/")[3]
            return [{"connectionDetails": self.source(model), "id": self.bindings.get(model)}]
        return list(self.items[path.split("/")[1]])

    def powerbi(self, credential, path, body=None):
        assert path.endswith("/Default.TakeOver") and body == {}
        self.takeovers.append(path.split("/")[3])
        return 200, {}, {}

    def refresh_model(self, credential, workspace, model):
        assert self.bindings.get(model) == self.connection["id"]
        if self.refresh_error:
            raise RuntimeError(self.refresh_error)
        self.refreshes.append((workspace, model))

    def call(self, credential, path, body=None, method=None):
        parts = path.split("/")
        item = parts[3]
        if path.endswith("/bindConnection"):
            binding = body["connectionBinding"]
            assert item in self.takeovers and binding["connectivityType"] == "ShareableCloud"
            assert binding["connectionDetails"] == self.source(item)
            if self.bind_persists:
                self.bindings[item] = binding["id"]
            return {}
        if path.endswith("getDefinition") or "getDefinition?" in path:
            return {"definition": {"parts": [{"path": file, "payload": base64.b64encode(content).decode()}
                                             for file, content in self.definitions[item].items()]}}
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
            target = find_item(self.items[workspace], name, kind)["id"]
            if kind == "SemanticModel":
                # Updating a model definition drops its connection binding.
                self.bindings.pop(target, None)
                self.definitions[target] = {f: c.encode() for f, c in read_parts(folder).items() if f != ".platform"}
                continue
            file = {"Notebook": "notebook-content.ipynb", "VariableLibrary": "variables.json",
                    "DataPipeline": "pipeline-content.json"}.get(kind)
            if file:
                content = (folder / file).read_text()
                if kind == "DataPipeline":
                    for old, new in logical.items():
                        content = content.replace(old, new)
                    content = content.replace(DEFAULT_WORKSPACE, workspace)
                self.definitions[target] = {file: content.encode()}

    def run(self):
        with patch("deploy_environment.list_all", self.list_all), patch("deploy_environment.call", self.call), \
                patch("deploy_environment.powerbi", self.powerbi), \
                patch("deploy_environment.refresh_model", self.refresh_model):
            return deploy(Mock(), "dev", self.publish)

    def model(self):
        return find_item(self.items[self.workspace("analytics")], MODEL_NAME, "SemanticModel")["id"]

    def workspace(self, layer):
        return find_workspace(self.workspaces, workspace_name(layer, "dev"))["id"]


class NamingTests(unittest.TestCase):
    def test_workspace_names_follow_convention(self):
        self.assertEqual(workspace_names("dev"), {
            "data": "Unily-Data-Dev", "analytics": "Unily-Analytics-Dev", "vault": "Unily-Vault-Dev"})
        self.assertEqual(gold_connection_name("test"), "conn-unily-analytics-test-gold-onelake")
        with self.assertRaises(ValueError):
            gold_connection_name("qa")
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
    @patch("fabric_api.powerbi")
    def test_model_refresh_polls_the_canonical_refresh(self, read, sleep):
        workspace, model, refresh = (str(uuid.uuid4()) for _ in range(3))
        base = f"groups/{workspace}/datasets/{model}/refreshes"
        accepted = (202, {"Location": f"https://regional.example.invalid/v1.0/myorg/{base}/{refresh}"}, {})
        read.side_effect = [accepted, (200, {}, {"status": "Unknown"}), (200, {}, {"status": "Completed"})]
        refresh_model(Mock(), workspace, model)
        self.assertEqual(read.call_args_list[0].args[1:], (base, {"type": "full", "retryCount": 0}))
        self.assertEqual(read.call_args.args[1], f"{base}/{refresh}")
        read.side_effect = [accepted, (200, {}, {"status": "Failed"})]
        with self.assertRaisesRegex(RuntimeError, "status Failed"):
            refresh_model(Mock(), workspace, model)
        read.side_effect = [(200, {}, {})]
        with self.assertRaisesRegex(RuntimeError, "not accepted"):
            refresh_model(Mock(), workspace, model)
        read.side_effect = [(202, {"Location": "https://example.invalid/arbitrary"}, {})]
        with self.assertRaises(ValueError):
            refresh_model(Mock(), workspace, model)

    def test_power_bi_calls_stay_on_the_canonical_api(self):
        for url in ("https://api.powerbi.com.example.invalid/v1.0/myorg/x", "https://api.fabric.microsoft.com/v1/x"):
            with self.assertRaisesRegex(ValueError, "unexpected API origin"):
                send(Mock(), url, POWERBI_API, POWERBI_SCOPE)

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
            (vault, ("Lakehouse",)), (data, ("Lakehouse",)), (data, ("VariableLibrary", "Notebook", "DataPipeline")),
            (analytics, ("SemanticModel",))])
        self.assertEqual({i["displayName"] for i in fabric.items[vault] if i["type"] == "Lakehouse"}, {"Identity"})
        self.assertEqual([(i["displayName"], i["type"]) for i in fabric.items[analytics]],
                         [(MODEL_NAME, "SemanticModel")])
        model = fabric.definitions[fabric.items[analytics][0]["id"]]
        gold_id = find_item(fabric.items[data], "Gold", "Lakehouse")["id"]
        self.assertEqual(model_summary({f: c.decode() for f, c in model.items()})["sources"],
                         [f"{ONELAKE}/{data}/{gold_id}"])
        library = find_item(fabric.items[data], "ProductAnalytics_Config", "VariableLibrary")
        deployed = {v["name"]: v["value"] for v in json.loads(fabric.definitions[library["id"]]["variables.json"])["variables"]}
        self.assertEqual(deployed["data_workspace_id"], data)
        self.assertEqual(deployed["vault_workspace_id"], vault)
        self.assertEqual(deployed["identity_id"], find_item(fabric.items[vault], "Identity", "Lakehouse")["id"])
        self.assertEqual(deployed["bronze_id"], find_item(fabric.items[data], "Bronze", "Lakehouse")["id"])
        self.assertFalse(deployed["allow_synthetic_overwrite"])
        demo = json.loads(fabric.definitions[find_item(fabric.items[data], "ProductAnalytics_Demo", "DataPipeline")["id"]]["pipeline-content.json"])
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
                    file = "pipeline-content.json"
                    fabric.definitions[item["id"]][file] = fabric.definitions[item["id"]][file].replace(
                        b'"Validate"', b'"Skipped"')
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

    def test_every_deployment_rebinds_and_reframes_the_model(self):
        fabric = FakeFabric()
        for run in (1, 2):
            fabric.run()
            model, analytics = fabric.model(), fabric.workspace("analytics")
            self.assertEqual(fabric.bindings, {model: fabric.connection["id"]})
            self.assertEqual(fabric.takeovers, [model] * run)
            self.assertEqual(fabric.refreshes, [(analytics, model)] * run)

    def test_binding_failures_stop_before_refresh(self):
        cases = {
            "not found or ambiguous": lambda fabric: setattr(fabric, "connection", None),
            "does not match": lambda fabric: fabric.connection.update(
                connectionDetails={"type": "AzureDataLakeStorage", "path": "https://example.invalid/"}),
            "did not persist": lambda fabric: setattr(fabric, "bind_persists", False),
        }
        for message, change in cases.items():
            with self.subTest(message=message):
                fabric = FakeFabric()
                change(fabric)
                with self.assertRaisesRegex(RuntimeError, message):
                    fabric.run()
                self.assertEqual(fabric.refreshes, [])

    def test_failed_refresh_fails_the_deployment(self):
        fabric = FakeFabric()
        fabric.refresh_error = "Semantic model refresh ended with status Failed"
        with self.assertRaisesRegex(RuntimeError, "status Failed"):
            fabric.run()

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


class SemanticModelTests(unittest.TestCase):
    def copy_model(self, directory):
        root = Path(directory)
        shutil.copytree(ROOT / "fabric", root / "fabric")
        return root, item_folder(root, "analytics", MODEL_NAME) / "definition"

    def test_model_mirrors_gold_contract_and_isolates_every_tenant(self):
        settings = load_settings(ROOT, "dev")
        summary = model_summary(read_parts(item_folder(ROOT, "analytics", MODEL_NAME)))
        check_model(summary, settings)
        self.assertEqual(summary["roles"]["UnilyAll"], {})
        self.assertEqual(summary["roles"]["TenantA"]["fact_usage_event"], '[tenant_id] = "tenant_a"')
        self.assertEqual(summary["hidden"]["TenantA"], {"fact_usage_event": ["pii_status", "silver_version"]})
        self.assertNotIn("UnilyAll", summary["hidden"])
        self.assertIn(("fact_usage_event.user_key", "dim_user.user_key"), summary["relationships"])
        extra = json.loads(settings["sources_json"]) + [
            {"tenant_id": "tenant_d", "users_table": "users_tenant_d", "events_table": "events_tenant_d"}]
        with self.assertRaisesRegex(ValueError, "no row-level security role"):
            check_model(summary, {**settings, "sources_json": json.dumps(extra)})

    def test_staged_model_reads_the_resolved_gold(self):
        current = values()
        with tempfile.TemporaryDirectory() as directory:
            stage = Path(directory) / "analytics"
            prepare(ROOT, stage, "analytics", ("SemanticModel",), "dev", current)
            parts = read_parts(stage / f"{MODEL_NAME}.SemanticModel")
            text = "".join(parts.values())
            self.assertNotIn(DATA_WORKSPACE_PLACEHOLDER, text)
            self.assertNotIn(GOLD_PLACEHOLDER, text)
            self.assertEqual(model_summary(parts)["sources"],
                             [f"{ONELAKE}/{current['data_workspace_id']}/{current['gold_id']}"])
            with self.assertRaises(ValueError):
                prepare(ROOT, Path(directory) / "missing", "analytics", ("SemanticModel",), "dev")

    def test_weakened_role_filter_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, definition = self.copy_model(directory)
            role = definition / "roles" / "TenantA.tmdl"
            role.write_text(role.read_text().replace('"tenant_a"', '"tenant_b"'), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "role: TenantA"):
                check_scope(root)

    def test_missing_or_extra_object_level_security_is_rejected(self):
        changes = {
            "TenantB.tmdl": lambda text: text.replace("columnPermission silver_version", "columnPermission event_id"),
            "TenantC.tmdl": lambda text: text.split("\t\tcolumnPermission")[0],
            "UnilyAll.tmdl": lambda text: text + "\n\ttablePermission dim_user\n\t\tmetadataPermission: none\n",
        }
        for file, change in changes.items():
            with self.subTest(file=file), tempfile.TemporaryDirectory() as directory:
                root, definition = self.copy_model(directory)
                role = definition / "roles" / file
                role.write_text(change(role.read_text()), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, "object-level security in role: " + file[:-5]):
                    check_scope(root)

    def test_column_outside_gold_contract_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, definition = self.copy_model(directory)
            table = definition / "tables" / "dim_user.tmdl"
            table.write_text(table.read_text().replace("sourceColumn: event_count", "sourceColumn: email"),
                             encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Gold contract"):
                check_scope(root)

    def test_model_referencing_another_item_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root, definition = self.copy_model(directory)
            source = definition / "expressions.tmdl"
            source.write_text(source.read_text().replace(GOLD_PLACEHOLDER, "00000000-0000-4000-8000-000000000010"),
                              encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "placeholders only"):
                check_scope(root)

    def test_changed_model_readback_is_rejected(self):
        fabric = FakeFabric()
        original = fabric.publish

        def tampered(workspace, directory, kinds):
            original(workspace, directory, kinds)
            for item in fabric.items[workspace]:
                if item["type"] == "SemanticModel":
                    file = "definition/roles/TenantB.tmdl"
                    text = fabric.definitions[item["id"]][file].decode()
                    fabric.definitions[item["id"]][file] = text.split("\t\tcolumnPermission")[0].encode()
        fabric.publish = tampered
        with self.assertRaisesRegex(RuntimeError, "Semantic model readback mismatch"):
            fabric.run()


if __name__ == "__main__":
    unittest.main()
