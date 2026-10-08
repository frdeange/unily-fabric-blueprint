"""Idempotently create the Data, Analytics and Vault workspaces of one environment.

Run locally by a Fabric administrator. Real IDs are arguments, never repository content.
Creates or corrects nothing beyond: missing workspaces, capacity assignment, the
deployment identity's Contributor role and its User role on the Gold connection (needed
to rebind the semantic models after each deployment). The connection itself is created
manually. It never deletes workspaces, connections or role assignments.
"""

import argparse
import uuid

from environment import ENVIRONMENTS, gold_connection_name, workspace_names
from fabric_api import call, find_workspace, list_all

DEPLOYER_ROLE = "Contributor"
CONNECTION_ROLE = "User"


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
    name = gold_connection_name(environment)
    report[name] = grant_connection(credential, name, deployer_id, apply)
    return report


def grant_connection(credential, name, deployer_id, apply):
    """Any existing role (User, UserWithReshare, Owner) is enough and is never changed."""
    connections = [c for c in list_all(credential, "connections") if c.get("displayName") == name]
    if len(connections) > 1:
        raise ValueError(f"Ambiguous connection name: {name}")
    if not connections:
        return ["missing: create it manually, then rerun"]
    path = f"connections/{connections[0]['id']}/roleAssignments"
    if any(a["principal"]["id"] == deployer_id for a in list_all(credential, path)):
        return ["unchanged"]
    if apply:
        call(credential, path, {"principal": {"id": deployer_id, "type": "ServicePrincipal"},
                                "role": CONNECTION_ROLE})
    return ["grant_deployer_user"]


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
