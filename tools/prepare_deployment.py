"""Prepare isolated, explicitly scoped deployment stages without touching Fabric."""

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
from gold_contract import GOLD_TABLES
from runtime_config import ID_FIELDS, LIBRARY_NAME, SETTING_FIELDS, validate_config

MODEL_NAME = "ProductAnalytics_Safe"
# layer -> item name -> (Fabric type, folder under fabric/<layer>/).
ITEMS = {
    "vault": {"Identity": ("Lakehouse", "shared/lakehouses")},
    "data": {
        "Bronze": ("Lakehouse", "shared/lakehouses"),
        "Silver": ("Lakehouse", "shared/lakehouses"),
        "Gold": ("Lakehouse", "shared/lakehouses"),
        LIBRARY_NAME: ("VariableLibrary", "product-analytics/variable-libraries"),
        "ProductAnalytics_Build": ("Notebook", "product-analytics/notebooks"),
        "ProductAnalytics_BronzeToSilver": ("Notebook", "product-analytics/notebooks"),
        "ProductAnalytics_SilverToGold": ("Notebook", "product-analytics/notebooks"),
        "ProductAnalytics_SilverPipeline": ("DataPipeline", "product-analytics/pipelines"),
        "ProductAnalytics_GoldPipeline": ("DataPipeline", "product-analytics/pipelines"),
        "ProductAnalytics_Demo": ("DataPipeline", "product-analytics/pipelines"),
    },
    "analytics": {MODEL_NAME: ("SemanticModel", "product-analytics/semantic-models")},
}
# Lakehouses first: the configuration and the semantic model reference their IDs. Pipelines share
# the data stage with the notebooks they reference, so fabric-cicd can resolve their logical IDs.
STAGES = (("vault", ("Lakehouse",)), ("data", ("Lakehouse",)),
          ("data", ("VariableLibrary", "Notebook", "DataPipeline")), ("analytics", ("SemanticModel",)))
ALLOWED_FILES = {
    "Lakehouse": {".platform", "lakehouse.metadata.json"},
    "Notebook": {".platform", "notebook-content.ipynb"},
    "VariableLibrary": {".platform", "variables.json", "settings.json"},
    "DataPipeline": {".platform", "pipeline-content.json"},
    "SemanticModel": {".platform", "definition.pbism", "definition/database.tmdl", "definition/model.tmdl",
                      "definition/expressions.tmdl", "definition/relationships.tmdl"}
    | {f"definition/tables/{table}.tmdl" for table in GOLD_TABLES},
}
# Semantic model roles are listed per item; one role per tenant plus the unfiltered internal role.
MODEL_ROLES = {"TenantA": "tenant_a", "TenantB": "tenant_b", "TenantC": "tenant_c", "UnilyAll": None}
DEFAULT_WORKSPACE = "00000000-0000-0000-0000-000000000000"
# The model reads Gold in the Data workspace; these placeholders are replaced at staging.
DATA_WORKSPACE_PLACEHOLDER = "00000000-0000-4000-8000-000000000019"
GOLD_PLACEHOLDER = "00000000-0000-4000-8000-000000000011"
ONELAKE = "https://onelake.dfs.fabric.microsoft.com"
# Gold contract types as Direct Lake column types.
TMDL_TYPES = {"string": "string", "date": "dateTime", "timestamp": "dateTime", "long": "int64", "int": "int64",
              "boolean": "boolean"}
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
LIBRARY_FOLDER = (ROOT / "fabric" / "data" / "product-analytics" / "variable-libraries"
                  / f"{LIBRARY_NAME}.VariableLibrary")
SUPPORTED_ENVIRONMENTS = {"dev"}


def item_folder(root, layer, name):
    kind, folder = ITEMS[layer][name]
    return root / "fabric" / layer / folder / f"{name}.{kind}"


def allowed_files(kind):
    if kind == "SemanticModel":
        return ALLOWED_FILES[kind] | {f"definition/roles/{role}.tmdl" for role in MODEL_ROLES}
    return ALLOWED_FILES[kind]


def model_summary(parts):
    """Authored shape of a TMDL model (TMDL file path -> text), ignoring metadata Fabric may add."""
    tables, roles, relationships, sources = {}, {}, set(), set()
    for path, text in parts.items():
        if not path.endswith(".tmdl"):
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines):
            stripped, depth = line.strip(), len(line) - len(line.lstrip("\t"))
            following = lambda key: next((l.strip()[len(key) + 2:] for l in lines[index + 1:index + 10]
                                          if l.strip().startswith(key + ":")), None)
            if depth == 0 and stripped.startswith("table "):
                table = tables.setdefault(stripped[6:], {"columns": {}, "measures": {}, "partitions": set()})
            elif depth == 1 and stripped.startswith("column "):
                table["columns"][stripped[7:]] = (following("dataType"), following("sourceColumn"))
            elif depth == 1 and stripped.startswith("measure "):
                name, expression = stripped[8:].split(" = ", 1)
                table["measures"][name.strip("'")] = " ".join(expression.split())
            elif depth == 3 and stripped.startswith("entityName:"):
                table["partitions"].add((stripped[12:], following("schemaName"), following("expressionSource"),
                                         next(l.strip()[6:] for l in lines[index - 3:index] if "mode:" in l)))
            elif depth == 0 and stripped.startswith("role "):
                role = roles.setdefault(stripped[5:], {})
            elif depth == 1 and stripped.startswith("tablePermission "):
                name, expression = stripped[16:].split(" = ", 1)
                role[name] = " ".join(expression.split())
            elif depth == 0 and stripped.startswith("relationship "):
                relationships.add((following("fromColumn"), following("toColumn")))
            elif "AzureStorage.DataLake(" in stripped:
                sources.add(stripped.split('"')[1])
    for table in tables.values():
        table["partitions"] = sorted(table["partitions"])
    return {"tables": tables, "roles": roles, "relationships": sorted(relationships), "sources": sorted(sources)}


def read_parts(folder):
    return {p.relative_to(folder).as_posix(): p.read_text(encoding="utf-8") for p in folder.rglob("*") if p.is_file()}


def tenants(settings):
    return {source["tenant_id"] for source in json.loads(settings["sources_json"])}


def check_model(summary, settings=None):
    """The safe model mirrors the Gold contract and isolates every configured tenant."""
    expected = {table: {column: (TMDL_TYPES[kind], column) for column, kind in columns}
                for table, columns in GOLD_TABLES.items()}
    if {name: table["columns"] for name, table in summary["tables"].items()} != expected:
        raise ValueError("Semantic model columns differ from the Gold contract")
    if any(table["partitions"] != [(name, "product", "'DirectLake - Gold'", "directLake")]
           for name, table in summary["tables"].items()):
        raise ValueError("Semantic model tables must be Direct Lake partitions of Gold")
    filtered = {table for table, columns in GOLD_TABLES.items() if "tenant_id" in dict(columns)}
    for role, tenant in MODEL_ROLES.items():
        expected_filters = {} if tenant is None else {t: f'[tenant_id] = "{tenant}"' for t in filtered}
        if summary["roles"].get(role) != expected_filters:
            raise ValueError(f"Unexpected row-level security filter in role: {role}")
    if set(summary["roles"]) != set(MODEL_ROLES):
        raise ValueError("Unexpected semantic model roles")
    covered = {tenant for tenant in MODEL_ROLES.values() if tenant}
    if settings is not None and tenants(settings) - covered:
        raise ValueError("A configured tenant has no row-level security role")


def variables_definition(values):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/variables/1.0.0/schema.json",
        "variables": [
            {"name": name, "type": "Boolean" if isinstance(value, bool) else "String", "value": value}
            for name, value in sorted(values.items())
        ],
    }


def load_settings(root, environment):
    """Committed, non-identifying settings; IDs are resolved by name at deployment."""
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError("Only the approved dev deployment target is supported")
    settings = json.loads((root / "config" / "environments" / environment / "product-analytics.json").read_text())
    if set(settings) != SETTING_FIELDS:
        raise ValueError("Environment settings do not match the configuration contract")
    if settings["allow_synthetic_overwrite"]:
        raise ValueError("Deployment must leave synthetic overwrite disabled")
    return settings


def runtime_values(settings, ids):
    if set(ids) != set(ID_FIELDS):
        raise ValueError("Resolved IDs do not match the configuration contract")
    values = {**settings, **ids}
    validate_config(values)
    return values


def logical_ids(root, layer):
    return {json.loads((item_folder(root, layer, name) / ".platform").read_text())["config"]["logicalId"]: name
            for name in ITEMS[layer]}


def check_scope(root):
    for layer, items in ITEMS.items():
        source = root / "fabric" / layer
        discovered = {p.parent for p in source.rglob(".platform")} if source.exists() else set()
        if discovered != {item_folder(root, layer, name) for name in items}:
            raise ValueError(f"Unexpected {layer} deployment item scope")
        for name, (kind, _) in items.items():
            item = item_folder(root, layer, name)
            platform = json.loads((item / ".platform").read_text())
            if platform["metadata"]["type"] != kind or platform["metadata"]["displayName"] != name:
                raise ValueError("Item metadata differs from the approved deployment scope")
            if {p.relative_to(item).as_posix() for p in item.rglob("*") if p.is_file()} != allowed_files(kind):
                raise ValueError("Unexpected files within a deployment item")
            if kind == "Lakehouse" and "defaultSchema" not in json.loads((item / "lakehouse.metadata.json").read_text()):
                raise ValueError(f"Lakehouse must be schema-enabled: {name}")
            if kind == "Notebook":
                notebook = json.loads((item / "notebook-content.ipynb").read_text())
                if any(c.get("outputs") or c.get("execution_count") is not None
                       or c.get("attachments") for c in notebook["cells"]):
                    raise ValueError("Notebook output or attachments cannot be deployed")
            if kind == "DataPipeline":
                # Only same-layer item references and the publication workspace placeholder.
                content = (item / "pipeline-content.json").read_text()
                if set(GUID.findall(content)) - set(logical_ids(root, layer)) - {DEFAULT_WORKSPACE}:
                    raise ValueError(f"Pipeline references an item outside its layer: {name}")
            if kind == "SemanticModel":
                parts = read_parts(item)
                definition = "".join(text for path, text in parts.items() if path != ".platform")
                if set(GUID.findall(definition)) != {DATA_WORKSPACE_PLACEHOLDER, GOLD_PLACEHOLDER}:
                    raise ValueError(f"Semantic model must reference Gold through placeholders only: {name}")
                summary = model_summary(parts)
                if summary["sources"] != [f"{ONELAKE}/{DATA_WORKSPACE_PLACEHOLDER}/{GOLD_PLACEHOLDER}"]:
                    raise ValueError(f"Semantic model must read Gold through Direct Lake on OneLake: {name}")
                check_model(summary)


def resolve_model(folder, values):
    """Point the staged model at the resolved Data workspace and Gold lakehouse."""
    for path in folder.rglob("*.tmdl"):
        text = path.read_text(encoding="utf-8")
        text = text.replace(DATA_WORKSPACE_PLACEHOLDER, values["data_workspace_id"])
        path.write_text(text.replace(GOLD_PLACEHOLDER, values["gold_id"]), encoding="utf-8", newline="\n")


def write_library(library, values):
    (library / "variables.json").write_text(json.dumps(variables_definition(values), indent=2), encoding="utf-8")
    # An explicit dev value set avoids fabric-cicd's default-value-set fallback.
    sets = library / "valueSets"
    sets.mkdir()
    (sets / "dev.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/valueSet/1.0.0/schema.json",
        "name": "dev",
        "variableOverrides": [],
    }, indent=2), encoding="utf-8")
    (library / "settings.json").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/settings/1.0.0/schema.json",
        "valueSetsOrder": ["dev"],
    }, indent=2), encoding="utf-8")


def stage_items(layer, kinds):
    return {name: kind for name, (kind, _) in ITEMS[layer].items() if kind in kinds}


def prepare(root, target, layer, kinds, environment, values=None):
    if environment not in SUPPORTED_ENVIRONMENTS:
        raise ValueError("Only the approved dev deployment target is supported")
    if target.exists():
        raise ValueError("Deployment staging directory must not already exist")
    if target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Private deployment staging must be outside the repository")
    selected = stage_items(layer, kinds)
    if not selected:
        raise ValueError("Empty deployment stage")
    needs_values = "VariableLibrary" in selected.values()
    needs_ids = "SemanticModel" in selected.values()
    if needs_values or needs_ids:
        if values is None:
            raise ValueError("Resolved configuration values are required for this stage")
        if validate_config(values)["allow_synthetic_overwrite"]:
            raise ValueError("Deployment must leave synthetic overwrite disabled")
    check_scope(root)
    if needs_ids:
        for name, kind in selected.items():
            if kind == "SemanticModel":
                check_model(model_summary(read_parts(item_folder(root, layer, name))), load_settings(root, environment))
    target.mkdir()
    for name, kind in selected.items():
        shutil.copytree(item_folder(root, layer, name), target / f"{name}.{kind}")
        if kind == "SemanticModel":
            resolve_model(target / f"{name}.{kind}", values)
    if needs_values:
        write_library(target / f"{LIBRARY_NAME}.VariableLibrary", values)
    return selected


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-template", action="store_true")
    args = parser.parse_args()
    example = json.loads((ROOT / "config" / "product-analytics.example.json").read_text())
    expected = variables_definition(example)
    path = LIBRARY_FOLDER / "variables.json"
    if args.check_template:
        check_scope(ROOT)
        load_settings(ROOT, "dev")
        if json.loads(path.read_text()) != expected:
            raise ValueError("Variable Library template differs from the configuration contract")
        print("Deployment scope, dev settings and Variable Library template verified.")
    else:
        path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        print("Example Variable Library template generated.")
