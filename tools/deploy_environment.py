"""Publish the approved items of one environment by naming convention.

Never executes notebooks or pipelines. The only job is the Direct Lake framing refresh of
the semantic models, after their Gold connection is rebound.
"""

import argparse
import base64
import json
import os
import tempfile
import uuid
from pathlib import Path

from environment import gold_connection_name, workspace_names
from fabric_api import call, find_workspace, list_all, powerbi, refresh_model
from prepare_deployment import (DEFAULT_WORKSPACE, ID_FIELDS, ITEMS, LIBRARY_NAME, ROOT, STAGES, load_settings,
                                logical_ids, model_summary, prepare, read_parts, runtime_values)

# Fabric creates one SQL analytics endpoint per lakehouse, with the same display name.
COMPANIONS = {"Lakehouse": "SQLEndpoint"}


def mask(value):
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print("::add-mask::" + str(value))


def find_item(items, name, kind, required=False):
    matches = [item for item in items if item["displayName"] == name and item["type"] == kind]
    others = [item for item in items if item["displayName"] == name
              and item["type"] not in (kind, COMPANIONS.get(kind))]
    if len(matches) > 1 or others:
        raise ValueError(f"Ambiguous or incompatible target item: {name}")
    if required and not matches:
        raise RuntimeError(f"Published item not found: {name}")
    return matches[0] if matches else None


def decode_parts(definition):
    return {part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
            for part in definition["definition"]["parts"]}


def verify_inventory(layer, before, after):
    """Existing IDs are preserved; only approved items (and their endpoints) may appear."""
    allowed = set()
    for name, (kind, _) in ITEMS[layer].items():
        item = find_item(after, name, kind, required=True)
        old = find_item(before, name, kind)
        if old and old["id"] != item["id"]:
            raise RuntimeError(f"Existing item identity changed: {name}")
        allowed.add(item["id"])
        companion = COMPANIONS.get(kind)
        allowed.update(i["id"] for i in after if i["displayName"] == name and i["type"] == companion)
    before_ids, after_ids = {i["id"] for i in before}, {i["id"] for i in after}
    if before_ids - after_ids or after_ids - before_ids - allowed:
        raise RuntimeError(f"Unexpected item creation or deletion detected in {layer}")


def verify_lakehouses(credential, workspace, layer, items):
    for name, (kind, _) in ITEMS[layer].items():
        if kind == "Lakehouse":
            item = find_item(items, name, kind, required=True)
            details = call(credential, f"workspaces/{workspace}/lakehouses/{item['id']}")
            if "defaultSchema" not in details.get("properties", {}):
                raise RuntimeError(f"Lakehouse is not schema-enabled: {name}")


def pipeline_shape(content):
    """Fields we author; Fabric may add metadata to the stored definition."""
    properties = content["properties"]
    activities = []
    for activity in properties["activities"]:
        settings = activity["typeProperties"]
        activities.append((
            activity["name"], activity["type"],
            [(d["activity"], d["dependencyConditions"]) for d in activity.get("dependsOn", [])],
            settings.get("notebookId"), settings.get("workspaceId"), settings.get("parameters"),
            settings.get("pipeline", {}).get("referenceName"), settings.get("waitOnCompletion"),
        ))
    return activities, properties.get("libraryVariables")


def resolve_pipeline(text, workspace, items):
    """Apply the substitutions fabric-cicd performs at publication."""
    for logical, name in logical_ids(ROOT, "data").items():
        kind = ITEMS["data"][name][0]
        text = text.replace(logical, find_item(items, name, kind, required=True)["id"])
    return text.replace(DEFAULT_WORKSPACE, workspace)


def verify_definitions(credential, workspace, items, target, values):
    for name, (kind, _) in ITEMS["data"].items():
        if kind not in ("Notebook", "VariableLibrary", "DataPipeline"):
            continue
        item = find_item(items, name, kind, required=True)
        endpoint = {"Notebook": "notebooks", "VariableLibrary": "variableLibraries",
                    "DataPipeline": "dataPipelines"}[kind]
        suffix = "?format=ipynb" if kind == "Notebook" else ""
        parts = decode_parts(call(
            credential, f"workspaces/{workspace}/{endpoint}/{item['id']}/getDefinition{suffix}", {}
        ))
        if kind == "Notebook":
            expected = json.loads((target / f"{name}.{kind}" / "notebook-content.ipynb").read_text())
            actual = json.loads(parts["notebook-content.ipynb"])
            expected_cells = [(c["cell_type"], "".join(c["source"])) for c in expected["cells"]]
            actual_cells = [(c["cell_type"], "".join(c["source"])) for c in actual["cells"]]
            if actual_cells != expected_cells:
                raise RuntimeError(f"Notebook cell readback mismatch: {name}")
            if any(c.get("outputs") or c.get("execution_count") is not None for c in actual["cells"]):
                raise RuntimeError(f"Unexpected executed notebook output: {name}")
        elif kind == "DataPipeline":
            staged = (target / f"{name}.{kind}" / "pipeline-content.json").read_text()
            expected = json.loads(resolve_pipeline(staged, workspace, items))
            if pipeline_shape(json.loads(parts["pipeline-content.json"])) != pipeline_shape(expected):
                raise RuntimeError(f"Pipeline definition readback mismatch: {name}")
        else:
            actual = {v["name"]: v["value"] for v in json.loads(parts["variables.json"])["variables"]}
            if actual != values:
                raise RuntimeError("Variable Library values differ from approved config")
            details = call(credential, f"workspaces/{workspace}/variableLibraries/{item['id']}")
            if details["properties"]["activeValueSetName"] != "dev":
                raise RuntimeError("Variable Library dev value set is not active")


def verify_model(credential, workspace, items, target):
    """The deployed TMDL keeps the authored tables, measures, relationships, roles and Gold source."""
    for name, (kind, _) in ITEMS["analytics"].items():
        item = find_item(items, name, kind, required=True)
        parts = decode_parts(call(
            credential, f"workspaces/{workspace}/semanticModels/{item['id']}/getDefinition?format=TMDL", {}))
        expected = model_summary(read_parts(target / f"{name}.{kind}"))
        if model_summary(parts) != expected:
            raise RuntimeError(f"Semantic model readback mismatch: {name}")


def details(source):
    return {key: source.get("connectionDetails", {}).get(key) for key in ("type", "path")}


def bind_and_reframe(credential, workspace, items, environment):
    """Updating a definition drops its connection binding: take over, rebind Gold and reframe."""
    name = gold_connection_name(environment)
    matches = [c for c in list_all(credential, "connections") if c.get("displayName") == name]
    if len(matches) != 1 or matches[0].get("connectivityType") != "ShareableCloud":
        raise RuntimeError(f"Shareable cloud connection not found or ambiguous: {name}")
    connection = matches[0]
    mask(connection["id"])
    for model, (kind, _) in ITEMS["analytics"].items():
        if kind != "SemanticModel":
            continue
        item = find_item(items, model, kind, required=True)
        # Only the model owner can bind it; the deployer takes it over idempotently.
        powerbi(credential, f"groups/{workspace}/datasets/{item['id']}/Default.TakeOver", {})
        path = f"workspaces/{workspace}/items/{item['id']}/connections"
        references = list_all(credential, path)
        if len(references) != 1 or details(references[0]) != details(connection):
            raise RuntimeError(f"Data source of {model} does not match {name}")
        call(credential, f"workspaces/{workspace}/semanticModels/{item['id']}/bindConnection", {
            "connectionBinding": {"id": connection["id"], "connectivityType": "ShareableCloud",
                                  "connectionDetails": references[0]["connectionDetails"]}})
        if [reference.get("id") for reference in list_all(credential, path)] != [connection["id"]]:
            raise RuntimeError(f"Connection binding did not persist: {model}")
        refresh_model(credential, workspace, item["id"])


def resolve_ids(workspaces, data_items, vault_items):
    lakehouse = lambda items, name: find_item(items, name, "Lakehouse", required=True)["id"]
    ids = {
        "data_workspace_id": workspaces["data"], "vault_workspace_id": workspaces["vault"],
        "bronze_id": lakehouse(data_items, "Bronze"), "silver_id": lakehouse(data_items, "Silver"),
        "gold_id": lakehouse(data_items, "Gold"),
        "identity_id": lakehouse(vault_items, "Identity"),
    }
    assert set(ids) == set(ID_FIELDS)
    return ids


def deploy(credential, environment, publish):
    settings = load_settings(ROOT, environment)
    # Validate the settings with placeholder IDs before any Fabric call.
    runtime_values(settings, {name: str(uuid.uuid4()) for name in ID_FIELDS})
    names = workspace_names(environment)
    visible = list_all(credential, "workspaces")
    workspaces = {layer: find_workspace(visible, name)["id"] for layer, name in names.items()}
    for workspace in workspaces.values():
        mask(workspace)
    inventory = lambda layer: list_all(credential, f"workspaces/{workspaces[layer]}/items")
    before = {layer: inventory(layer) for layer in names}
    for layer, items in ITEMS.items():
        for name, (kind, _) in items.items():
            find_item(before[layer], name, kind)
    with tempfile.TemporaryDirectory(prefix="fabric-deploy-") as directory:
        temp = Path(directory)
        values = None
        stages = {}
        for index, (layer, kinds) in enumerate(STAGES):
            if "VariableLibrary" in kinds:
                ids = resolve_ids(workspaces, inventory("data"), inventory("vault"))
                for value in ids.values():
                    mask(value)
                values = runtime_values(settings, ids)
            stage = temp / f"stage-{index}"
            prepare(ROOT, stage, layer, kinds, environment, values)
            stages[(layer, kinds)] = stage
            publish(workspaces[layer], stage, list(kinds))
        after = {layer: inventory(layer) for layer in names}
        for layer in names:
            verify_inventory(layer, before[layer], after[layer])
            verify_lakehouses(credential, workspaces[layer], layer, after[layer])
        verify_definitions(credential, workspaces["data"], after["data"],
                           stages[("data", ("VariableLibrary", "Notebook", "DataPipeline"))], values)
        verify_model(credential, workspaces["analytics"], after["analytics"],
                     stages[("analytics", ("SemanticModel",))])
    bind_and_reframe(credential, workspaces["analytics"], after["analytics"], environment)
    return {layer: sorted(items) for layer, items in ITEMS.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", default="dev")
    environment = parser.parse_args().environment
    os.environ["FABRIC_CICD_FILE_LOGGING_ENABLED"] = "false"
    from azure.identity import AzureCliCredential
    from fabric_cicd import FabricWorkspace, append_feature_flag, publish_all_items
    append_feature_flag("disable_workspace_folder_publish")
    credential = AzureCliCredential()

    def publish(workspace, directory, kinds):
        publish_all_items(FabricWorkspace(
            workspace_id=workspace, environment=environment, repository_directory=str(directory),
            item_type_in_scope=kinds, token_credential=credential,
        ))

    report = deploy(credential, environment, publish)
    for layer, items in report.items():
        print(f"{workspace_names(environment)[layer]}: {', '.join(items) or 'no items yet'}")
    print("Published and verified by readback. Semantic models rebound to Gold and refreshed; "
          "no notebooks or pipelines executed.")


if __name__ == "__main__":
    main()
