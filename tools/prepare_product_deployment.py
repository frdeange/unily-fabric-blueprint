"""Prepare an isolated, explicitly scoped deployment without touching Fabric."""

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "product_analytics"))
from runtime_config import LIBRARY_NAME, validate_config

ITEMS = {
    "ProductAnalytics_Build": ("Notebook", "notebooks"),
    "ProductAnalytics_BronzeToSilver": ("Notebook", "notebooks"),
    LIBRARY_NAME: ("VariableLibrary", "variable-libraries"),
}
LIBRARY_FOLDER = (
    ROOT / "fabric" / "product-analytics" / "variable-libraries"
    / f"{LIBRARY_NAME}.VariableLibrary"
)


def variables_definition(values):
    return {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/variableLibrary/definition/variables/1.0.0/schema.json",
        "variables": [
            {"name": name, "type": "Boolean" if isinstance(value, bool) else "String", "value": value}
            for name, value in sorted(values.items())
        ],
    }


def prepare(root, target, values, environment):
    config = validate_config(values)
    if environment != "dev":
        raise ValueError("Only the approved dev deployment target is supported")
    if config["allow_synthetic_overwrite"]:
        raise ValueError("Deployment must leave synthetic overwrite disabled")
    if target.exists():
        raise ValueError("Deployment staging directory must not already exist")
    if target.resolve().is_relative_to(root.resolve()):
        raise ValueError("Private deployment staging must be outside the repository")
    source = root / "fabric" / "product-analytics"
    discovered = {path.parent.relative_to(source) for path in source.rglob(".platform")}
    expected = {Path(folder) / f"{name}.{kind}" for name, (kind, folder) in ITEMS.items()}
    if discovered != expected:
        raise ValueError("Unexpected Product deployment item scope")
    # Preflight every item before creating a private resolved copy.
    for name, (kind, folder) in ITEMS.items():
        item = source / folder / f"{name}.{kind}"
        platform = json.loads((item / ".platform").read_text())
        if platform["metadata"]["type"] != kind or platform["metadata"]["displayName"] != name:
            raise ValueError("Item metadata differs from the approved deployment scope")
        allowed = {".platform", "notebook-content.ipynb"} if kind == "Notebook" else {
            ".platform", "variables.json", "settings.json",
        }
        if {p.relative_to(item).as_posix() for p in item.rglob("*") if p.is_file()} != allowed:
            raise ValueError("Unexpected files within a deployment item")
        if kind == "Notebook":
            notebook = json.loads((item / "notebook-content.ipynb").read_text())
            if any(c.get("outputs") or c.get("execution_count") is not None
                   or c.get("attachments") for c in notebook["cells"]):
                raise ValueError("Notebook output or attachments cannot be deployed")
    target.mkdir()
    for name, (kind, folder) in ITEMS.items():
        shutil.copytree(source / folder / f"{name}.{kind}", target / f"{name}.{kind}")
    library = target / f"{LIBRARY_NAME}.VariableLibrary"
    (library / "variables.json").write_text(
        json.dumps(variables_definition(values), indent=2), encoding="utf-8"
    )
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
    return config


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-template", action="store_true")
    args = parser.parse_args()
    example = json.loads((ROOT / "config" / "product-analytics.example.json").read_text())
    expected = variables_definition(example)
    path = LIBRARY_FOLDER / "variables.json"
    if args.check_template:
        if json.loads(path.read_text()) != expected:
            raise ValueError("Variable Library template differs from the configuration contract")
        print("Variable Library template verified.")
    else:
        path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
        print("Example Variable Library template generated.")
