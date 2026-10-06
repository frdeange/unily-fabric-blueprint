import unittest
from pathlib import Path

from tools.issue_workflow import (
    DATA_CHANGE_IMPACT,
    check_branch,
    check_issue,
    classify,
    closing_issues,
)

ROOT = Path(__file__).resolve().parents[1]


def form(issue_type="Maintenance", area="CI/CD", impact="No Fabric or data impact"):
    return (
        f"### Issue type\n\n{issue_type}\n\n### Area\n\n{area}\n\n"
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


class TemplateTests(unittest.TestCase):
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
