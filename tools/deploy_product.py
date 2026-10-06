"""Publish only the approved Product library and notebooks; never execute jobs."""

import base64
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from urllib.parse import urlparse

from prepare_product_deployment import ITEMS, ROOT, prepare

API = "https://api.fabric.microsoft.com/v1"


def operation_endpoint(headers):
    operation_id = headers.get("x-ms-operation-id")
    if not operation_id:
        location = urlparse(headers["Location"])
        segments = location.path.strip("/").split("/")
        if len(segments) != 3 or segments[:2] != ["v1", "operations"]:
            raise ValueError("Unexpected Fabric operation path")
        operation_id = segments[2]
    # Follow the operation ID through the canonical API, never a supplied host.
    return f"{API}/operations/{uuid.UUID(operation_id)}"


def read_api(credential, path, body=None):
    url = path if path.startswith("https://") else f"{API}/{path}"
    if not url.startswith(API + "/"):
        raise ValueError("Refusing an unexpected API origin")
    headers = {"Authorization": "Bearer " + credential.get_token(API.removesuffix("/v1") + "/.default").token}
    payload = None if body is None else json.dumps(body).encode()
    request = Request(url, data=payload, headers=headers, method="GET" if body is None else "POST")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=90) as response:
            if response.status == 202:
                location = operation_endpoint(response.headers)
                delay = int(response.headers.get("Retry-After", "5"))
                return wait_operation(credential, location, delay)
            return json.load(response)
    except HTTPError as error:
        raise RuntimeError(f"Fabric readback failed with HTTP {error.code}") from None


def wait_operation(credential, location, delay):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        time.sleep(min(max(delay, 1), 30))
        operation = read_api(credential, location)
        if operation["status"] == "Succeeded":
            return read_api(credential, location.rstrip("/") + "/result")
        if operation["status"] in ("Failed", "Cancelled"):
            raise RuntimeError("Fabric definition readback operation failed")
    raise TimeoutError("Fabric definition readback timed out")


def inventory(credential, workspace):
    result, path = [], f"workspaces/{workspace}/items"
    while path:
        page = read_api(credential, path)
        result.extend(page["value"])
        path = page.get("continuationUri")
    return result


def find_item(items, name, kind, required=False):
    matches = [item for item in items if item["displayName"] == name]
    if len(matches) > 1 or (matches and matches[0]["type"] != kind):
        raise ValueError(f"Ambiguous or incompatible target item: {name}")
    if required and not matches:
        raise RuntimeError(f"Published item not found: {name}")
    return matches[0] if matches else None


def decode_parts(definition):
    return {part["path"]: base64.b64decode(part["payload"]).decode("utf-8")
            for part in definition["definition"]["parts"]}


def verify_readback(credential, workspace, before, after, target, values):
    expected_ids = set()
    for name, (kind, _) in ITEMS.items():
        item = find_item(after, name, kind, required=True)
        old = find_item(before, name, kind)
        if old and old["id"] != item["id"]:
            raise RuntimeError(f"Existing item identity changed: {name}")
        expected_ids.add(item["id"])
        endpoint = "notebooks" if kind == "Notebook" else "variableLibraries"
        suffix = "?format=ipynb" if kind == "Notebook" else ""
        parts = decode_parts(read_api(
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
        else:
            actual = {v["name"]: v["value"] for v in json.loads(parts["variables.json"])["variables"]}
            if actual != values:
                raise RuntimeError("Variable Library values differ from approved config")
            details = read_api(credential, f"workspaces/{workspace}/variableLibraries/{item['id']}")
            if details["properties"]["activeValueSetName"] != "dev":
                raise RuntimeError("Variable Library dev value set is not active")
    before_ids = {item["id"] for item in before}
    after_ids = {item["id"] for item in after}
    if before_ids - after_ids or after_ids - before_ids - expected_ids:
        raise RuntimeError("Unexpected item creation or deletion detected")


def main():
    values = json.loads(os.environ["PRODUCT_RUNTIME_CONFIG_JSON"])
    workspace = os.environ["FABRIC_WORKSPACE_ID"].strip()
    # Each ID is masked independently, including identifiers inside package logs.
    if os.environ.get("GITHUB_ACTIONS") == "true":
        for name in ("workspace_id", "bronze_id", "silver_id", "identity_id"):
            print("::add-mask::" + str(values[name]))
    with tempfile.TemporaryDirectory(prefix="fabric-product-") as directory:
        temp = Path(directory)
        config = prepare(ROOT, temp / "items", values, "dev")
        if config["workspace_id"] != workspace:
            raise ValueError("Private configuration does not match approved workspace")
        os.environ["FABRIC_CICD_FILE_LOGGING_ENABLED"] = "false"
        from azure.identity import AzureCliCredential
        from fabric_cicd import FabricWorkspace, append_feature_flag, publish_all_items
        credential = AzureCliCredential()
        before = inventory(credential, workspace)
        for name, (kind, _) in ITEMS.items():
            find_item(before, name, kind)
        append_feature_flag("disable_workspace_folder_publish")
        target = FabricWorkspace(
            workspace_id=workspace, environment="dev",
            repository_directory=str(temp / "items"),
            item_type_in_scope=["VariableLibrary", "Notebook"],
            token_credential=credential,
        )
        publish_all_items(target)
        after = inventory(credential, workspace)
        verify_readback(credential, workspace, before, after, temp / "items", values)
    print("Published and verified Product configuration and two notebooks. No jobs executed.")


if __name__ == "__main__":
    main()
