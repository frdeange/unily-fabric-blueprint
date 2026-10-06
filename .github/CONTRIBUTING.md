# Contributing

All changes follow an issue-first workflow. Write issues, commits, pull requests
and code in English.

## Workflow

1. **Open an issue** using one of the forms: Feature, Bug, Maintenance or
   Documentation. Blank issues are disabled.
2. **Automatic triage** rewrites the title to `[Type] Area: summary` and applies
   managed emoji labels from the selected form values. For example:
   `[Maintenance] CI/CD: establish issue-first contribution workflow`.
3. **Create a branch** from up-to-date `main`, named
   `<prefix>/<issue-number>-<short-slug>`:

   | Issue type | Branch prefix | Example |
   | --- | --- | --- |
   | Feature | `feature/` | `feature/12-support-semantic-model` |
   | Bug | `fix/` | `fix/15-silver-marker-check` |
   | Maintenance | `maintenance/` | `maintenance/7-issue-first-workflow` |
   | Documentation | `docs/` | `docs/18-runtime-guide` |

4. **Open a pull request into `main`** with exactly one `Closes #<issue>`
   reference to an open issue in this repository. The `Linked issue` check fails
   when the reference is missing, invalid, closed, points to a pull request or
   when several issues are referenced. It reruns when the description changes.
   Branch names that do not follow the convention produce a warning.
5. **Merge** after required checks succeed. The issue closes automatically.
6. **Deploy separately.** Merging never publishes to Fabric. Publication runs
   only through the manual workflow and the approved `dev` Environment.
   Notebook execution and any data change need a separate explicit approval.

## Labels

| Label | Applied when |
| --- | --- |
| `✨ feature`, `🐛 bug`, `🧹 maintenance`, `📚 documentation` | Issue type |
| `📊 product-analytics`, `🛟 support`, `🚀 ci-cd`, `🧠 semantic-models`, `🔐 security` | Area (`Repository` adds no area label) |
| `⚠️ data-change` | Fabric/data impact changes, deletes or regenerates data |

Triage manages only these labels and preserves any other label. Editing the
form fields updates the title and labels. Triage changes made by the workflow
token do not trigger it again.

## Safety rules

- Never include secrets, tokens, real tenant/workspace/item IDs or personal
  data in issues, pull requests, commits or notebooks. Use the example GUIDs.
- Install and run the pre-commit hooks described in the README.
- Automation treats issue and pull-request text as data only; never add steps
  that interpolate it into shell commands or execute it.
