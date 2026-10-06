"""Idempotently create the Data, Analytics and Vault workspaces of one environment.

Run locally by a Fabric administrator. Real IDs are arguments, never repository content.
Creates or corrects nothing beyond: missing workspaces, capacity assignment and the
deployment identity's Contributor role. It never deletes workspaces or role assignments.
"""

import argparse
import uuid

from environment import ENVIRONMENTS, workspace_names
from fabric_api import call, find_workspace, list_all

DEPLOYER_ROLE = "Contributor"


def plan_workspace(existing, capacity_id):
    if existing is None:
        return ["create"]
    return [] if existing.get("capacityId") == capacity_id else ["assign_capacity"]


def plan_role(assignments, principal_id):
    matches = [a for a in assignments if a["principal"]["id"] == principal_id]
    if not matches:
        return ["grant_deployer"]
    if matches[0]["role"] != DEPLOYER_ROLE:
        raise RuntimeError(f"Deployment identity has role {matches[0]['role']}; review manually")
    return []


def provision(credential, environment, capacity_id, deployer_id, apply):
    capacity_id, deployer_id = str(uuid.UUID(capacity_id)), str(uuid.UUID(deployer_id))
    workspaces = list_all(credential, "workspaces")
    report = {}
    for layer, name in workspace_names(environment).items():
        workspace = find_workspace(workspaces, name, required=False)
        actions = plan_workspace(workspace, capacity_id)
        if apply and "create" in actions:
            workspace = call(credential, "workspaces", {
                "displayName": name, "capacityId": capacity_id,
                "description": f"Unily {layer} layer, {environment} environment. Managed from the repository.",
            })
        elif apply and "assign_capacity" in actions:
            call(credential, f"workspaces/{workspace['id']}/assignToCapacity", {"capacityId": capacity_id})
        if workspace is None:
            actions.append("grant_deployer")
        else:
            assignments = list_all(credential, f"workspaces/{workspace['id']}/roleAssignments")
            role_actions = plan_role(assignments, deployer_id)
            if apply and role_actions:
                call(credential, f"workspaces/{workspace['id']}/roleAssignments", {
                    "principal": {"id": deployer_id, "type": "ServicePrincipal"}, "role": DEPLOYER_ROLE,
                })
            actions.extend(role_actions)
        report[name] = actions or ["unchanged"]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=ENVIRONMENTS, required=True)
    parser.add_argument("--capacity-id", required=True)
    parser.add_argument("--deployer-object-id", required=True,
                        help="Object ID of the deployment service principal (not the app ID)")
    parser.add_argument("--apply", action="store_true", help="Without this flag only the plan is shown")
    args = parser.parse_args()
    from azure.identity import AzureCliCredential
    report = provision(AzureCliCredential(), args.environment, args.capacity_id,
                       args.deployer_object_id, args.apply)
    for name, actions in report.items():
        print(f"{name}: {', '.join(actions)}")
    print("Applied." if args.apply else "Plan only; rerun with --apply to make changes.")


if __name__ == "__main__":
    main()
