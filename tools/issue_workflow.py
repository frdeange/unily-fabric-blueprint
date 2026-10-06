"""Classify issue-form issues and validate pull-request issue links.

Issue and pull-request text is treated only as data: it is parsed with regular
expressions and never evaluated, executed or interpolated into a shell.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request

API = "https://api.github.com"

TYPES = {
    "Feature": "✨ feature",
    "Bug": "🐛 bug",
    "Maintenance": "🧹 maintenance",
    "Documentation": "📚 documentation",
}
AREAS = {
    "Product Analytics": "📊 product-analytics",
    "Support": "🛟 support",
    "CI/CD": "🚀 ci-cd",
    "Semantic Models": "🧠 semantic-models",
    "Security": "🔐 security",
    "Repository": None,
}
DATA_CHANGE_LABEL = "⚠️ data-change"
DATA_CHANGE_IMPACT = "Changes, deletes or regenerates Fabric data"
MANAGED_LABELS = {*TYPES.values(), *(label for label in AREAS.values() if label), DATA_CHANGE_LABEL}
BRANCH_PREFIXES = {"Feature": "feature", "Bug": "fix", "Maintenance": "maintenance", "Documentation": "docs"}

SECTION = re.compile(r"^###[ \t]+(.+?)[ \t]*\r?\n(.*?)(?=^###[ \t]|\Z)", re.M | re.S)
TITLE_PREFIX = re.compile(r"^\s*(?:\[[^\]\n]{1,40}\]\s*)+")
CLOSING = re.compile(r"(?<![\w/#])(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s*:?\s+#(\d+)\b", re.I)
HIDDEN = re.compile(r"<!--.*?-->|```.*?```|~~~.*?~~~", re.S)
BRANCH = re.compile(r"^(feature|fix|maintenance|docs)/(\d+)-[a-z0-9][a-z0-9-]*$")


def form_fields(body):
    """Return the `### Heading` sections rendered by GitHub issue forms."""
    return {name.strip(): value.strip() for name, value in SECTION.findall(body or "")}


def classify(title, body):
    """Return the normalized title and managed labels, or None for non-form issues."""
    fields = form_fields(body)
    issue_type = fields.get("Issue type")
    if issue_type is None:
        return None
    if issue_type not in TYPES:
        raise ValueError(f"Unsupported issue type: {issue_type}")
    area = fields.get("Area")
    if area not in AREAS:
        raise ValueError(f"Unsupported area: {area}")
    summary = TITLE_PREFIX.sub("", title or "").strip()
    for name in AREAS:
        if summary.lower().startswith(name.lower() + ":"):
            summary = summary[len(name) + 1:].strip()
            break
    if not summary:
        raise ValueError("Issue title needs a short summary")
    labels = {TYPES[issue_type]}
    if AREAS[area]:
        labels.add(AREAS[area])
    if fields.get("Fabric/data impact") == DATA_CHANGE_IMPACT:
        labels.add(DATA_CHANGE_LABEL)
    return f"[{issue_type}] {area}: {summary}", labels


def closing_issues(body):
    """Return the distinct same-repository issue numbers closed by a PR body."""
    visible = HIDDEN.sub("", body or "")
    return sorted({int(number) for number in CLOSING.findall(visible)})


def check_branch(branch, issue_number):
    """Return an advisory message when the branch does not follow the convention."""
    match = BRANCH.match(branch or "")
    if not match:
        return "Branch should be named <feature|fix|maintenance|docs>/<issue>-<short-slug>."
    if int(match.group(2)) != issue_number:
        return f"Branch number {match.group(2)} does not match linked issue #{issue_number}."
    return None


def check_issue(issue, number):
    if issue is None:
        raise ValueError(f"#{number} does not exist in this repository")
    if "pull_request" in issue:
        raise ValueError(f"#{number} is a pull request, not an issue")
    if issue.get("state") != "open":
        raise ValueError(f"Issue #{number} is not open")


def request(method, path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "issue-workflow",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        if error.code in (404, 410):
            return None
        raise


def load_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as handle:
        return json.load(handle)


def run_triage():
    event = load_event()
    repo = os.environ["GITHUB_REPOSITORY"]
    issue = event["issue"]
    if "pull_request" in issue:
        return 0
    try:
        result = classify(issue.get("title"), issue.get("body"))
    except ValueError as error:
        print(f"::warning::Issue #{issue['number']} was not classified: {error}")
        return 0
    if result is None:
        print("Issue was not created from a form; nothing to classify.")
        return 0
    title, wanted = result
    current = {label["name"] for label in issue.get("labels", [])}
    labels = sorted((current - MANAGED_LABELS) | wanted)
    if title == issue["title"] and set(labels) == current:
        print("Issue already classified.")
        return 0
    request("PATCH", f"/repos/{repo}/issues/{issue['number']}", {"title": title, "labels": labels})
    print(f"Classified issue #{issue['number']}: {title} {sorted(wanted)}")
    return 0


def run_link_check():
    event = load_event()
    repo = os.environ["GITHUB_REPOSITORY"]
    pr = event["pull_request"]
    numbers = closing_issues(pr.get("body"))
    if len(numbers) != 1:
        print("::error::The PR description must contain exactly one closing reference, e.g. 'Closes #123'.")
        return 1
    number = numbers[0]
    try:
        check_issue(request("GET", f"/repos/{repo}/issues/{number}"), number)
    except ValueError as error:
        print(f"::error::{error}")
        return 1
    advice = check_branch(pr["head"]["ref"], number)
    if advice:
        print(f"::warning::{advice}")
    print(f"Pull request is linked to open issue #{number}.")
    return 0


if __name__ == "__main__":
    commands = {"triage": run_triage, "check-pr": run_link_check}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit("usage: issue_workflow.py triage|check-pr")
    sys.exit(commands[sys.argv[1]]())
