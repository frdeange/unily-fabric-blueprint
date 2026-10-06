"""Minimal Fabric REST client: canonical host only, long-running operations, paging."""

import json
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API = "https://api.fabric.microsoft.com/v1"
SCOPE = "https://api.fabric.microsoft.com/.default"


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


def call(credential, path, body=None, method=None):
    url = path if path.startswith("https://") else f"{API}/{path}"
    if not url.startswith(API + "/"):
        raise ValueError("Refusing an unexpected API origin")
    method = method or ("GET" if body is None else "POST")
    headers = {"Authorization": "Bearer " + credential.get_token(SCOPE).token}
    payload = None if body is None else json.dumps(body).encode()
    request = Request(url, data=payload, headers=headers, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=90) as response:
            if response.status == 202 and (
                response.headers.get("x-ms-operation-id") or response.headers.get("Location")
            ):
                location = operation_endpoint(response.headers)
                delay = int(response.headers.get("Retry-After", "5"))
                return wait_operation(credential, location, delay)
            content = response.read()
            return json.loads(content) if content else {}
    except HTTPError as error:
        raise RuntimeError(f"Fabric {method} {urlparse(url).path.split('/')[-1]} failed with HTTP {error.code}") from None


def wait_operation(credential, location, delay):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        time.sleep(min(max(delay, 1), 30))
        operation = call(credential, location)
        if operation["status"] == "Succeeded":
            try:
                return call(credential, location.rstrip("/") + "/result")
            except RuntimeError as error:
                # Operations without a result payload (for example capacity assignment) return 404.
                if "HTTP 404" not in str(error):
                    raise
                return {}
        if operation["status"] in ("Failed", "Cancelled"):
            raise RuntimeError("Fabric long-running operation failed")
    raise TimeoutError("Fabric long-running operation timed out")


def list_all(credential, path):
    result = []
    while path:
        page = call(credential, path)
        result.extend(page["value"])
        path = page.get("continuationUri")
    return result


def find_workspace(workspaces, name, required=True):
    matches = [workspace for workspace in workspaces if workspace["displayName"] == name]
    if len(matches) > 1:
        raise ValueError(f"Ambiguous workspace name: {name}")
    if required and not matches:
        raise RuntimeError(f"Workspace not found or not accessible: {name}")
    return matches[0] if matches else None
