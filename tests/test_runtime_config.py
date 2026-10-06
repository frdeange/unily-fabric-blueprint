import copy
import ast
from contextlib import contextmanager
import json
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
from runtime_config import FIELDS, ID_FIELDS, LIBRARY_NAME, load_runtime_config, onelake_table, validate_config
from tools.build_notebooks import code_sections, notebook_cells, pipelines
import build_product_analytics


def valid_config():
    values = json.loads((ROOT / "config" / "product-analytics.example.json").read_text())
    for name in ID_FIELDS:
        values[name] = str(uuid.uuid4())
    return values


class RuntimeConfigTests(unittest.TestCase):
    def test_example_config_is_not_executable(self):
        values = json.loads((ROOT / "config" / "product-analytics.example.json").read_text())
        with self.assertRaisesRegex(ValueError, "Example configuration only"):
            validate_config(values)

    def test_library_values_are_read_without_fallback(self):
        values = valid_config()
        utilities = Mock()
        library = utilities.variableLibrary.getLibrary.return_value
        library.getVariable.side_effect = values.__getitem__
        config = load_runtime_config(utilities)
        utilities.variableLibrary.getLibrary.assert_called_once_with(LIBRARY_NAME)
        self.assertEqual(library.getVariable.call_count, len(FIELDS))
        self.assertEqual(config["sources"][0]["users_table"], "users_tenant_a")
        library.getVariable.side_effect = RuntimeError("missing variable")
        with self.assertRaisesRegex(RuntimeError, "missing variable"):
            load_runtime_config(utilities)

    def test_pipeline_parameters_replace_library_reads(self):
        values = valid_config()
        values["allow_synthetic_overwrite"] = False
        utilities = Mock()
        config = load_runtime_config(utilities, values)
        utilities.variableLibrary.getLibrary.assert_not_called()
        self.assertEqual(config["bronze_id"], values["bronze_id"])
        partial = {**{name: None for name in FIELDS}, "bronze_id": values["bronze_id"]}
        with self.assertRaisesRegex(ValueError, "every configuration field"):
            load_runtime_config(utilities, partial)
        library = utilities.variableLibrary.getLibrary.return_value
        library.getVariable.side_effect = values.__getitem__
        load_runtime_config(utilities, {name: None for name in FIELDS})
        utilities.variableLibrary.getLibrary.assert_called_once_with(LIBRARY_NAME)

    def test_pipelines_pass_every_field_from_the_library(self):
        definitions = pipelines()
        self.assertEqual(set(definitions), {"ProductAnalytics_SilverPipeline", "ProductAnalytics_GoldPipeline",
                                            "ProductAnalytics_Demo"})
        for name, definition in definitions.items():
            library = definition["properties"]["libraryVariables"]
            self.assertEqual(set(library), FIELDS)
            self.assertTrue(all(v["libraryName"] == LIBRARY_NAME for v in library.values()))
            for activity in definition["properties"]["activities"]:
                if activity["type"] == "TridentNotebook":
                    self.assertTrue(set(FIELDS) <= set(activity["typeProperties"]["parameters"]))
                    self.assertTrue(activity["policy"]["secureInput"])
        validate, process = definitions["ProductAnalytics_SilverPipeline"]["properties"]["activities"]
        gold, = definitions["ProductAnalytics_GoldPipeline"]["properties"]["activities"]
        self.assertEqual(validate["typeProperties"]["parameters"]["validate_only"]["value"]["value"], "@bool('true')")
        self.assertEqual(process["typeProperties"]["parameters"]["validate_only"]["value"]["value"], "@bool('false')")
        self.assertEqual(process["dependsOn"], [{"activity": "Validate", "dependencyConditions": ["Succeeded"]}])
        self.assertNotIn("validate_only", gold["typeProperties"]["parameters"])
        self.assertEqual(gold["dependsOn"], [])
        build, silver, gold = definitions["ProductAnalytics_Demo"]["properties"]["activities"]
        self.assertNotIn("validate_only", build["typeProperties"]["parameters"])
        for invoke, after in ((silver, "Build"), (gold, "Silver")):
            self.assertEqual(invoke["type"], "ExecutePipeline")
            self.assertTrue(invoke["typeProperties"]["waitOnCompletion"])
            self.assertEqual(invoke["dependsOn"], [{"activity": after, "dependencyConditions": ["Succeeded"]}])
        # Only the reproduction pipeline chains stages.
        for name in ("ProductAnalytics_SilverPipeline", "ProductAnalytics_GoldPipeline"):
            types = {a["type"] for a in definitions[name]["properties"]["activities"]}
            self.assertEqual(types, {"TridentNotebook"})

    def test_fourth_source_is_supported_by_processing_registry(self):
        values = valid_config()
        sources = json.loads(values["sources_json"])
        sources.append({"tenant_id": "tenant_d", "users_table": "d_users", "events_table": "d_events"})
        values["sources_json"] = json.dumps(sources)
        config = validate_config(values)
        self.assertEqual(len(config["sources"]), 4)
        self.assertEqual(config["sources"][-1]["events_table"], "d_events")
        for module in ("identity_phase.py", "silver_phase.py"):
            source = (ROOT / "src" / "product_analytics" / module).read_text()
            self.assertIn('CONFIG["sources"]', source)
            self.assertNotIn('"tenant_a"', source)

    def test_invalid_config_is_rejected(self):
        baseline = valid_config()
        invalid = []
        missing = dict(baseline)
        del missing["data_workspace_id"]
        invalid.append(missing)
        for field, value in (
            ("data_workspace_id", ""), ("bronze_id", baseline["identity_id"]),
            ("gold_id", baseline["silver_id"]),
            ("vault_workspace_id", baseline["data_workspace_id"]),
            ("pii_model", ""), ("allow_synthetic_overwrite", "false"),
            ("sources_json", "[]"), ("sources_json", "null"),
            ("sources_json", "{}"), ("sources_json", "invalid"),
        ):
            invalid.append({**baseline, field: value})
        original = json.loads(baseline["sources_json"])
        for mutate in (
            lambda s: s.append(copy.deepcopy(s[0])),
            lambda s: s[0].update(users_table="../escape"),
            lambda s: s[0].update(events_table=s[0]["users_table"]),
            lambda s: s[0].update(tenant_id="unsafe/name"),
            lambda s: s[0].update(extra=True),
        ):
            sources = copy.deepcopy(original)
            mutate(sources)
            invalid.append({**baseline, "sources_json": json.dumps(sources)})
        for values in invalid:
            with self.subTest(values=values), self.assertRaises(ValueError):
                validate_config(values)

    def test_generator_allows_initial_load_and_guards_overwrite(self):
        mode = build_product_analytics.raw_load_mode
        config = validate_config(valid_config())
        self.assertEqual(mode(config, []), "initial_load")
        with self.assertRaisesRegex(RuntimeError, "overwrite is disabled"):
            mode(config, ["users_tenant_a"])
        self.assertEqual(mode({**config, "allow_synthetic_overwrite": True}, ["users_tenant_a"]), "overwrite")
        with self.assertRaisesRegex(RuntimeError, "only the versioned A/B/C"):
            mode({**config, "sources": [{"tenant_id": "tenant_d"}]}, [])
        spark_source = build_product_analytics.SPARK_SOURCE
        self.assertLess(spark_source.index("raw_load_mode("), spark_source.index(".write"))

    def test_identity_and_audit_live_in_vault_and_tables_in_product_schema(self):
        config = validate_config(valid_config())
        path = onelake_table(config["vault_workspace_id"], config["identity_id"], "user_identity_map")
        self.assertTrue(path.startswith(f"abfss://{config['vault_workspace_id']}@"))
        self.assertTrue(path.endswith("/Tables/product/user_identity_map"))
        source = ROOT / "src" / "product_analytics"
        identity = (source / "identity_phase.py").read_text()
        silver = (source / "silver_phase.py").read_text()
        self.assertIn('MAP_PATH = onelake_table(VAULT, CONFIG["identity_id"]', identity)
        self.assertIn('AUDIT = onelake_files(VAULT, CONFIG["identity_id"]', silver)
        self.assertIn('OUTPUT = onelake_table(DATA, CONFIG["silver_id"]', silver)
        for module in (identity, silver):
            self.assertNotIn("abfss://", module)
            self.assertIn('mode("errorifexists")', module)

    def test_cells_are_ordered_and_independently_syntactic(self):
        for name, sections in code_sections().items():
            cells = notebook_cells(name, sections)
            code = [cell for cell in cells if cell["cell_type"] == "code"]
            self.assertEqual(len(code), {"ProductAnalytics_Build": 4, "ProductAnalytics_BronzeToSilver": 7,
                                         "ProductAnalytics_SilverToGold": 4}[name])
            parameters = "".join(code[0]["source"])
            self.assertEqual(code[0]["metadata"]["tags"], ["parameters"])
            for field in FIELDS:
                self.assertIn(f"{field} = None", parameters)
            self.assertEqual("validate_only = False" in parameters, name.endswith("_BronzeToSilver"))
            self.assertIn("load_runtime_config(notebookutils, {name: globals().get(name)", "".join(code[1]["source"]))
            self.assertEqual(len({cell["id"] for cell in cells}), len(cells))
            for cell in code:
                compile("".join(cell["source"]), name, "exec")
                self.assertIsNone(cell["execution_count"])
                self.assertEqual(cell["outputs"], [])

    def test_validation_only_exits_before_processing(self):
        name = "ProductAnalytics_BronzeToSilver"
        sections = code_sections()[name]
        preflight = next(code for title, code in sections if title == "Read-only runtime validation")
        utilities = Mock()
        class NotebookExit(Exception):
            pass
        utilities.notebook.exit.side_effect = NotebookExit
        namespace = {"validate_only": True, "CONFIG": {}, "spark": object(),
                     "notebookutils": utilities, "json": json}
        # Replace only the validation function with a controlled read-only result.
        tree = ast.parse(preflight)
        tree.body = [node for node in tree.body if not isinstance(node, ast.FunctionDef)]
        namespace["validate_runtime"] = Mock(return_value={"data_writes": 0})
        with self.assertRaises(NotebookExit), patch("builtins.print"):
            exec(compile(tree, "<preflight>", "exec"), namespace)
        namespace["validate_runtime"].assert_called_once()
        source = "\n".join(code for _, code in sections)
        self.assertLess(source.index("Runtime validated; no processing or writes"),
                        source.index("new_records ="))

    def test_processing_and_publication_failures_are_audited_and_raised(self):
        source = (ROOT / "src" / "product_analytics" / "silver_phase.py").read_text()
        function = next(node for node in ast.parse(source).body
                        if isinstance(node, ast.FunctionDef) and node.name == "audit_failure")
        utilities = Mock()
        context = {"contextmanager": contextmanager, "notebookutils": utilities,
                   "evidence": {}, "AUDIT": "restricted-audit", "RUN": "test-run", "json": json}
        exec(compile(ast.Module(body=[function], type_ignores=[]), "<audit>", "exec"), context)
        for phase in ("processing", "publication"):
            with self.subTest(phase=phase), self.assertRaisesRegex(RuntimeError, phase):
                with context["audit_failure"]():
                    raise RuntimeError(phase)
            payload = json.loads(utilities.fs.put.call_args.args[1])
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["error"]["message"], phase)


if __name__ == "__main__":
    unittest.main()
