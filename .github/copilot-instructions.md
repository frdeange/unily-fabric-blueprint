# Instructions for AI coding agents

Follow `.github/CONTRIBUTING.md`. Key rules:

- Work only from an existing open issue. Read its form sections: Objective or
  Current/Expected behavior, Scope, Acceptance criteria, Out of scope and
  Fabric/data impact. Implement the scope and satisfy every acceptance
  criterion. Do not change anything listed as out of scope.
- Create a `<feature|fix|maintenance|docs>/<issue>-<slug>` branch from `main`. Open the pull request
  into `main` with exactly one `Closes #<issue>` reference and complete the PR
  template.
- Use English everywhere. Use only the example GUIDs
  `00000000-0000-4000-8000-000000000001` to `...0012`. Never commit secrets,
  real identifiers, personal data or notebook outputs.
- Edit Python sources in `src/`, then regenerate notebooks with
  `python tools/build_notebooks.py`. Do not edit generated code cells directly.
- Before opening the PR, run:
  `python tools/check_repository.py`,
  `python tools/build_notebooks.py --check`,
  `python tools/prepare_deployment.py --check-template` and
  `python -m unittest discover -s tests -v`.
- Never publish to Fabric, execute notebooks, or delete or regenerate data as
  part of a pull request. Deployment and execution are separate approved steps.
  If the issue has `⚠️ data-change`, stop and request explicit approval
  before any execution.
- Add new Fabric items as `fabric/<layer>/<domain>/<type>/<Name>.<FabricType>/` and
  explicitly extend the deployment allowlist and its tests.
- Name workspaces, items, groups, identities and secrets exactly as defined in
  `docs/architecture.md`. Never invent a name or token; if one is missing,
  stop and propose a change to that document first. Respect workspace
  boundaries: Analytics reads Gold only, and only Bronze-to-Silver writes Vault.
