import unittest
from pathlib import Path

from tools.issue_workflow import (
    DATA_CHANGE_IMPACT,
    MANAGED_LABELS,
    WORKSPACE_LABELS,
    check_branch,
    check_issue,
    classify,
    closing_issues,
    managed_labels,
    path_labels,
    target_workspace_labels,
)

ROOT = Path(__file__).resolve().parents[1]


def form(issue_type="Maintenance", area="CI/CD", impact="No Fabric or data impact", workspaces=None):
    body = (
        f"### Issue type\n\n{issue_type}\n\n### Area\n\n{area}\n\n"
    )
    if workspaces is not None:
        boxes = "\n".join(f"- [{'X' if name in workspaces else ' '}] {name}"
                          for name in ("Data", "Analytics", "Vault"))
        body += f"### Target workspace\n\n{boxes}\n\n"
    return body + (
        f"### Objective\n\nText with ### inside a line and `rm -rf /`.\n\n"
        f"### Fabric/data impact\n\n{impact}\n\n### Impact notes\n\n_No response_\n"
    )


class ClassifyTests(unittest.TestCase):
    def test_title_and_labels(self):
        title, labels = classify("[Maintenance] establish workflow", form())
        self.assertEqual(title, "[Maintenance] CI/CD: establish workflow")
        self.assertEqual(labels, {"🧹 maintenance", "🚀 ci-cd"})

    def test_existing_prefix_is_replaced_idempotently(self):
        title, _ = classify("[Bug] [Old] Support: broken load", form("Bug", "Product Analytics"))
        self.assertEqual(title, "[Bug] Product Analytics: broken load")
        self.assertEqual(classify(title, form("Bug", "Product Analytics"))[0], title)

    def test_repository_area_has_no_area_label(self):
        _, labels = classify("[Documentation] fix typo", form("Documentation", "Repository"))
        self.assertEqual(labels, {"📚 documentation"})

    def test_data_change_label(self):
        _, labels = classify("[Feature] reset raw", form("Feature", "Product Analytics", DATA_CHANGE_IMPACT))
        self.assertIn("⚠️ data-change", labels)

    def test_non_form_issue_is_ignored(self):
        self.assertIsNone(classify("Anything", "free text"))

    def test_invalid_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "type"):
            classify("[X] y", form("Epic"))
        with self.assertRaisesRegex(ValueError, "area"):
            classify("[Bug] y", form("Bug", "Billing"))
        with self.assertRaisesRegex(ValueError, "summary"):
            classify("[Bug] ", form("Bug"))


class LinkTests(unittest.TestCase):
    def test_single_reference(self):
        self.assertEqual(closing_issues("## Linked issue\n\nCloses #7\n"), [7])
        self.assertEqual(closing_issues("fixes: #3 and Resolves #3"), [3])

    def test_missing_or_ignored_references(self):
        self.assertEqual(closing_issues("Closes #\n<!-- Closes #9 -->\n```\nFixes #4\n```"), [])
        self.assertEqual(closing_issues("Closes other/repo#5 and see #6"), [])
        self.assertEqual(closing_issues(None), [])

    def test_multiple_references(self):
        self.assertEqual(closing_issues("Closes #1\nCloses #2"), [1, 2])

    def test_issue_validation(self):
        check_issue({"state": "open"}, 1)
        for issue, message in ((None, "exist"), ({"state": "closed"}, "not open"),
                               ({"state": "open", "pull_request": {}}, "pull request")):
            with self.assertRaisesRegex(ValueError, message):
                check_issue(issue, 1)

    def test_branch_advice(self):
        self.assertIsNone(check_branch("maintenance/7-issue-first-workflow", 7))
        self.assertIn("does not match", check_branch("feature/8-x", 7))
        self.assertIn("should be named", check_branch("chore/x", 7))


class WorkspaceLabelTests(unittest.TestCase):
    def test_checked_boxes_become_labels(self):
        _, labels = classify("[Feature] x", form("Feature", "Product Analytics", workspaces={"Data", "Vault"}))
        self.assertEqual(labels, {"✨ feature", "📊 product-analytics", "🗄️ data", "🔒 vault"})
        self.assertEqual(target_workspace_labels("### Target workspace\n\n- [x] Analytics\n- [ ] Vault\n"),
                         {"📈 analytics"})

    def test_empty_or_missing_field(self):
        self.assertEqual(target_workspace_labels(form(workspaces=set())), set())
        self.assertIsNone(target_workspace_labels(form()))
        self.assertEqual(target_workspace_labels("### Target workspace\n\n_No response_\n"), set())

    def test_workspace_labels_managed_only_with_field(self):
        self.assertEqual(managed_labels(form()), MANAGED_LABELS)
        self.assertEqual(managed_labels(form(workspaces=set())), MANAGED_LABELS | WORKSPACE_LABELS)

    def test_path_labels(self):
        self.assertEqual(path_labels(["fabric/data/shared/lakehouses/Bronze.Lakehouse/.platform"]), {"🗄️ data"})
        self.assertEqual(path_labels(["fabric/analytics/x/y"]), {"📈 analytics"})
        self.assertEqual(path_labels(["src/product_analytics/identity_phase.py"]), {"🗄️ data", "🔒 vault"})
        self.assertEqual(path_labels(["src/product_analytics/silver_phase.py"]), {"🗄️ data", "🔒 vault"})
        self.assertEqual(path_labels(["src/product_analytics/runtime_config.py"]), {"🗄️ data"})
        self.assertEqual(path_labels(["fabric/vault/shared/a", "fabric/data/b"]), {"🔒 vault", "🗄️ data"})
        self.assertEqual(path_labels(["README.md", "tools/x.py", "fabric/datax/y", "src/product_analytics"]),
                         set())


class TemplateTests(unittest.TestCase):
    def test_workspace_field_in_forms(self):
        for name in ("1-feature.yml", "2-bug.yml", "3-maintenance.yml"):
            text = (ROOT / ".github" / "ISSUE_TEMPLATE" / name).read_text(encoding="utf-8")
            self.assertIn("label: Target workspace", text, name)
            for option in ("Data", "Analytics", "Vault"):
                self.assertIn(f'- label: "{option}"', text, name)

    def test_forms_match_classifier(self):
        from tools.issue_workflow import AREAS, TYPES

        forms = sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("[0-9]-*.yml"))
        self.assertEqual(len(forms), 4)
        found = set()
        for path in forms:
            text = path.read_text(encoding="utf-8")
            for value in (*AREAS, DATA_CHANGE_IMPACT, "label: Issue type", "label: Fabric/data impact"):
                self.assertIn(value, text, path.name)
            found.update(t for t in TYPES if f'title: "[{t}] "' in text)
            self.assertNotIn('- "None"', text)
        self.assertEqual(found, set(TYPES))


if __name__ == "__main__":
    unittest.main()
