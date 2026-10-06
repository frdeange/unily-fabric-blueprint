"""Verify federated access to the environment workspaces without deploying or running items."""

import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parent))
from environment import workspace_names

API = "https://api.fabric.microsoft.com/v1"


def verify_connection(environment):
    names = workspace_names(environment)
    token = subprocess.check_output(
        ["az", "account", "get-access-token", "--resource", "https://api.fabric.microsoft.com",
         "--query", "accessToken", "--output", "tsv"],
        text=True,
    ).strip()
    if not token:
        raise RuntimeError("Azure CLI returned an empty Fabric access token")
    visible, url = [], f"{API}/workspaces"
    while url:
        if not url.startswith(API + "/"):
            raise RuntimeError("Refusing an unexpected API origin")
        request = Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
        try:
            with urlopen(request, timeout=60) as response:
                page = json.load(response)
        except HTTPError as error:
            raise RuntimeError(
                f"Fabric workspace listing failed (HTTP {error.code}); "
                "check the tenant service-principal settings"
            ) from None
        visible.extend(workspace["displayName"] for workspace in page["value"])
        url = page.get("continuationUri")
    missing = sorted(name for name in names.values() if visible.count(name) != 1)
    if missing:
        raise RuntimeError("Workspaces missing, ambiguous or not shared with the deployment identity: "
                           + ", ".join(missing))
    print(f"Federated Fabric connection verified for {', '.join(names.values())}. "
          "No items were deployed or executed.")


if __name__ == "__main__":
    verify_connection(os.environ.get("FABRIC_ENVIRONMENT", "dev"))
