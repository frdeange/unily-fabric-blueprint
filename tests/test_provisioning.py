import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from provision_environment import plan_role, plan_workspace, provision

CAPACITY, DEPLOYER = str(uuid.uuid4()), str(uuid.uuid4())
CONNECTION = "conn-unily-analytics-dev-gold-onelake"
WORKSPACES = {"Unily-Data-Dev", "Unily-Analytics-Dev", "Unily-Vault-Dev"}


class FakeTenant:
    def __init__(self, workspaces=(), connections=()):
        self.workspaces = list(workspaces)
        self.connections = list(connections)
        self.roles = {w["id"]: [] for w in self.workspaces + self.connections}
        self.writes = []

    def list_all(self, credential, path):
        if path in ("workspaces", "connections"):
            return getattr(self, path)
        return self.roles[path.split("/")[1]]

    def call(self, credential, path, body=None, method=None):
        self.writes.append(path)
        if path == "workspaces":
            workspace = {**body, "id": str(uuid.uuid4())}
            self.workspaces.append(workspace)
            self.roles[workspace["id"]] = []
            return workspace
        if path.endswith("/roleAssignments"):
            self.roles[path.split("/")[1]].append(body)
        elif path.endswith("/assignToCapacity"):
            next(w for w in self.workspaces if w["id"] == path.split("/")[1])["capacityId"] = body["capacityId"]
        return {}

    def run(self, apply):
        with patch("provision_environment.list_all", self.list_all), patch("provision_environment.call", self.call):
            return provision(Mock(), "dev", CAPACITY, DEPLOYER, apply)


class PlanTests(unittest.TestCase):
    def test_workspace_plan(self):
        self.assertEqual(plan_workspace(None, CAPACITY), ["create"])
        self.assertEqual(plan_workspace({"capacityId": CAPACITY}, CAPACITY), [])
        self.assertEqual(plan_workspace({"capacityId": "other"}, CAPACITY), ["assign_capacity"])

    def test_role_plan_never_downgrades_or_upgrades_silently(self):
        self.assertEqual(plan_role([], DEPLOYER), ["grant_deployer"])
        self.assertEqual(plan_role([{"principal": {"id": DEPLOYER}, "role": "Contributor"}], DEPLOYER), [])
        with self.assertRaisesRegex(RuntimeError, "review manually"):
            plan_role([{"principal": {"id": DEPLOYER}, "role": "Admin"}], DEPLOYER)


class ProvisionTests(unittest.TestCase):
    def test_plan_mode_writes_nothing(self):
        tenant = FakeTenant(connections=[{"displayName": CONNECTION, "id": "c1"}])
        report = tenant.run(apply=False)
        self.assertEqual(set(report), WORKSPACES | {CONNECTION})
        self.assertTrue(all(report[name] == ["create", "grant_deployer"] for name in WORKSPACES))
        self.assertEqual(report[CONNECTION], ["grant_deployer_user"])
        self.assertEqual(tenant.writes, [])

    def test_apply_is_idempotent(self):
        tenant = FakeTenant(connections=[{"displayName": CONNECTION, "id": "c1"}])
        tenant.run(apply=True)
        self.assertEqual(len(tenant.workspaces), 3)
        for workspace in tenant.workspaces:
            self.assertEqual(workspace["capacityId"], CAPACITY)
            self.assertEqual(tenant.roles[workspace["id"]], [
                {"principal": {"id": DEPLOYER, "type": "ServicePrincipal"}, "role": "Contributor"}])
        self.assertEqual(tenant.roles["c1"], [{"principal": {"id": DEPLOYER, "type": "ServicePrincipal"},
                                               "role": "User"}])
        tenant.writes.clear()
        self.assertTrue(all(a == ["unchanged"] for a in tenant.run(apply=True).values()))
        self.assertEqual(tenant.writes, [])

    def test_connection_roles_are_never_changed_and_missing_connection_is_reported(self):
        tenant = FakeTenant(connections=[{"displayName": CONNECTION, "id": "c1"}])
        tenant.roles["c1"].append({"principal": {"id": DEPLOYER}, "role": "Owner"})
        self.assertEqual(tenant.run(apply=True)[CONNECTION], ["unchanged"])
        self.assertEqual(tenant.roles["c1"], [{"principal": {"id": DEPLOYER}, "role": "Owner"}])
        self.assertEqual(FakeTenant().run(apply=True)[CONNECTION], ["missing: create it manually, then rerun"])
        twice = FakeTenant(connections=[{"displayName": CONNECTION, "id": i} for i in ("c1", "c2")])
        with self.assertRaisesRegex(ValueError, "Ambiguous connection"):
            twice.run(apply=True)

    def test_existing_workspace_on_other_capacity_is_reassigned(self):
        tenant = FakeTenant([{"displayName": "Unily-Data-Dev", "id": "w1", "capacityId": "old"}])
        report = tenant.run(apply=True)
        self.assertEqual(report["Unily-Data-Dev"], ["assign_capacity", "grant_deployer"])
        self.assertEqual(tenant.workspaces[0]["capacityId"], CAPACITY)

    def test_invalid_ids_fail_before_any_call(self):
        tenant = FakeTenant()
        with patch("provision_environment.list_all") as listing:
            with self.assertRaises(ValueError):
                provision(Mock(), "dev", "not-a-guid", DEPLOYER, True)
            listing.assert_not_called()


if __name__ == "__main__":
    unittest.main()
