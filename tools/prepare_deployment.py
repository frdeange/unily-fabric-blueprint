"""Prepare isolated, explicitly scoped deployment stages without touching Fabric."""

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
from runtime_config import ID_FIELDS, LIBRARY_NAME, SETTING_FIELDS, validate_config

# layer -> item name -> (Fabric type, folder under fabric/<layer>/). Analytics has no items yet.
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
    "analytics": {},
}
# Lakehouses first: the configuration references their IDs. Pipelines share the last stage
# with the notebooks they reference, so fabric-cicd can resolve their logical IDs.
STAGES = (("vault", ("Lakehouse",)), ("data", ("Lakehouse",)),
          ("data", ("VariableLibrary", "Notebook", "DataPipeline")))
ALLOWED_FILES = {
    "Lakehouse": {".platform", "lakehouse.metadata.json"},
    "Notebook": {".platform", "notebook-content.ipynb"},
    "VariableLibrary": {".platform", "variables.json", "settings.json"},
    "DataPipeline": {".platform", "pipeline-content.json"},
}
DEFAULT_WORKSPACE = "00000000-0000-0000-0000-000000000000"
GUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
LIBRARY_FOLDER = (ROOT / "fabric" / "data" / "product-analytics" / "variable-libraries"
                  / f"{LIBRARY_NAME}.VariableLibrary")
SUPPORTED_ENVIRONMENTS = {"dev"}


def item_folder(root, layer, name):
    kind, folder = ITEMS[layer][name]
    return root / "fabric" / layer / folder / f"{name}.{kind}"


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
            if {p.relative_to(item).as_posix() for p in item.rglob("*") if p.is_file()} != ALLOWED_FILES[kind]:
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
    if needs_values:
        if values is None:
            raise ValueError("Configuration values are required for the Variable Library")
        if validate_config(values)["allow_synthetic_overwrite"]:
            raise ValueError("Deployment must leave synthetic overwrite disabled")
    check_scope(root)
    target.mkdir()
    for name, kind in selected.items():
        shutil.copytree(item_folder(root, layer, name), target / f"{name}.{kind}")
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
