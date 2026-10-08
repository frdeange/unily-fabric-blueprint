"""Minimal Fabric REST client: canonical hosts only, long-running operations, paging.

The Power BI API is used only for what Fabric does not expose yet: semantic model
take-over and refresh.
"""

import json
import time
import uuid
from urllib.error import HTTPError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

API = "https://api.fabric.microsoft.com/v1"
SCOPE = "https://api.fabric.microsoft.com/.default"
POWERBI_API = "https://api.powerbi.com/v1.0/myorg"
POWERBI_SCOPE = "https://analysis.windows.net/powerbi/api/.default"
REFRESH_DONE = "Completed"
REFRESH_FAILED = ("Failed", "Cancelled", "Disabled", "TimedOut")


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


def send(credential, url, base, scope, body=None, method=None):
    """Return status, headers and decoded JSON of one request to an allowed origin."""
    if not url.startswith(base + "/"):
        raise ValueError("Refusing an unexpected API origin")
    method = method or ("GET" if body is None else "POST")
    headers = {"Authorization": "Bearer " + credential.get_token(scope).token}
    payload = None if body is None else json.dumps(body).encode()
    request = Request(url, data=payload, headers=headers, method=method)
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=90) as response:
            content = response.read()
            return response.status, response.headers, json.loads(content) if content else {}
    except HTTPError as error:
        service = "Power BI" if base == POWERBI_API else "Fabric"
        raise RuntimeError(f"{service} {method} {urlparse(url).path.split('/')[-1]} "
                           f"failed with HTTP {error.code}") from None


def call(credential, path, body=None, method=None):
    url = path if path.startswith("https://") else f"{API}/{path}"
    status, headers, content = send(credential, url, API, SCOPE, body, method)
    if status == 202 and (headers.get("x-ms-operation-id") or headers.get("Location")):
        location = operation_endpoint(headers)
        return wait_operation(credential, location, int(headers.get("Retry-After", "5")))
    return content


def powerbi(credential, path, body=None):
    """Call the Power BI API; return status, headers and JSON."""
    return send(credential, f"{POWERBI_API}/{path}", POWERBI_API, POWERBI_SCOPE, body)


def refresh_model(credential, workspace, model, timeout=900):
    """Run one full (Direct Lake framing) refresh and wait until it completes."""
    base = f"groups/{uuid.UUID(workspace)}/datasets/{uuid.UUID(model)}/refreshes"
    status, headers, _ = powerbi(credential, base, {"type": "full", "retryCount": 0})
    if status != 202 or not headers.get("Location"):
        raise RuntimeError("Semantic model refresh was not accepted")
    # Follow the refresh ID through the canonical API, never a supplied host.
    refresh = uuid.UUID(urlparse(headers["Location"]).path.rstrip("/").rsplit("/", 1)[-1])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(min(max(int(headers.get("Retry-After", "10")), 1), 30))
        state = powerbi(credential, f"{base}/{refresh}")[2].get("status")
        if state == REFRESH_DONE:
            return
        if state in REFRESH_FAILED:
            raise RuntimeError(f"Semantic model refresh ended with status {state}")
    raise TimeoutError("Semantic model refresh timed out")


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
