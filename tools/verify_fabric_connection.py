"""Verify federated workspace access without deploying or running items."""

import json
import os
import subprocess
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify_connection(workspace_id):
    workspace = str(uuid.UUID(workspace_id))
    if workspace.startswith("00000000-0000-4000-8000-"):
        raise ValueError("Example workspace IDs cannot be used for connection verification")
    token = subprocess.check_output(
        [
            "az",
            "account",
            "get-access-token",
            "--resource",
            "https://api.fabric.microsoft.com",
            "--query",
            "accessToken",
            "--output",
            "tsv",
        ],
        text=True,
    ).strip()
    if not token:
        raise RuntimeError("Azure CLI returned an empty Fabric access token")
    request = Request(
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace}",
        headers={"Authorization": f"Bearer {token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=60) as response:
            result = json.load(response)
    except HTTPError as error:
        raise RuntimeError(
            f"Fabric workspace access failed (HTTP {error.code}); "
            "check the workspace role and tenant service-principal settings"
        ) from None
    if result.get("id") != workspace:
        raise RuntimeError("Fabric returned an unexpected workspace")
    print("Federated Fabric connection verified. No items were deployed or executed.")


if __name__ == "__main__":
    verify_connection(os.environ["FABRIC_WORKSPACE_ID"])
