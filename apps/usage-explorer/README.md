# Adoption Workbench (Rayfin app)

A Fabric app (Rayfin, preview) that connects **live investigation** to **persistent follow-through**. Read the synthetic `ProductAnalytics_Safe` semantic model, capture an evidence-based diagnosis, and manage private follow-up actions in the app's own database.

The demo workflow is our proposal, not a confirmed Unily process. The source data and lab architecture are synthetic technical hypotheses, not customer facts. There is no churn model, invented benchmark, automated recommendation, or mock-data fallback.

## Demonstration flow

1. **Investigate:** select an available tenant and month, examine distinct active users, event counts, duration, prior-calendar-month comparisons, and feature usage. Selecting a feature focuses the evidence inspector.
2. **Diagnose:** capture the observed figures and write your own interpretation. The private library retains a dated snapshot even if live source data later changes. Editing a diagnosis changes only its title and interpretation.
3. **Follow through:** create linked actions, set priority and a due date, and move them between Planned, In progress, and Done. Search by action or tenant, filter overdue/high-priority items, and revisit the original diagnosis.

The signed-in user is the responsible owner. Cross-user collaboration, external notifications, and deletion are deliberately not exposed. Every action is linked to an existing, accessible diagnosis.

## Data

- Connector `productanalytics` (type `fabric-semanticmodel`, delegated auth): every query runs as the signed-in user, so the model's own security applies.
- Bounded DAX queries live in `packages/frontend/src/queries/adoption.ts`; their exact source columns and result contracts are checked, including numeric and calendar values.
- `[Active users]` is queried at the required tenant/month or feature grain. Feature user counts are **not** summed. Event share is feature events / tenant events. Events per user is tenant events / tenant distinct users.
- A zero or missing prior-month denominator yields no percentage comparison, not an invented increase. Duration is not a satisfaction metric. Monthly event totals are not normalized by month length.
- Source limits are 1,000 tenant/month observations and 5,000 feature observations; sentinel rows detect over-limit results and fail explicitly instead of silently truncating.
- A model failure does not hide the user's saved records. An unavailable app data service does not replace saving with browser storage.

### App-owned records and authorization

`packages/data/src/Diagnosis.ts` and `FollowUp.ts` define the runtime entities; `packages/shared` carries browser-safe contracts. Both have explicit authenticated create/read policies matching `claims.sub` to `owner_id`. Update field allowlists prevent transferring ownership, changing a diagnosis's captured evidence, or relinking an existing action.

The typed client stamps ownership from the authenticated session. Backend policies, not client filters, enforce row access. Saved lists use cursor pagination with a visible failure above the supported 2,000-record-per-entity limit. Save feedback follows the server's returned row; a failed write keeps the form text.

Snapshots contain aggregate evidence only, never user-level events. Do not put personal data or confidential information in free-text fields. A saved diagnosis is a user-authored working record, not a tamper-proof audit record.

Source-model permission revocation does not automatically retract an already captured snapshot. App-owned records remain protected by their owner's app identity, not by a fresh semantic-model RLS evaluation. Review retention and revocation requirements before extending this demo to real customer data.

## Configuration and secrets

- `rayfin/rayfin.yml` is committed with placeholder identifiers (`...0001` workspace, `...0002` semantic model).
- `scripts/render-rayfin-config.mjs` replaces them from `RAYFIN_WORKSPACE_ID` and `RAYFIN_SEMANTIC_MODEL_ID` at deploy time. `--check` verifies the placeholders are intact.
- No credentials are stored in code. CI authenticates with Entra workload identity federation (no client secret).
- `rayfin/.env`, `rayfin/.deployments.json` and `rayfin.config.json` are generated per deployment and git-ignored.

## Local development

```sh
npm ci
npm run typecheck && npm run lint && npm test && npm run build
```

To run against the live model, sign in with `rayfin login`, render the config from your own environment variables, and use `npm run dev`. Do not commit the rendered `rayfin.yml`.

## CI/CD

| Stage | Workflow | Notes |
|---|---|---|
| Pull request | `.github/workflows/app-ci.yml` | Install, config check, typecheck, lint, tests, visual validation, build. No Fabric credentials. |
| Deploy | `.github/workflows/deploy-app-dev.yml` | Manual, only from `main`, bound to the protected `dev` environment (required reviewer). Re-runs the checks, renders config, previews with `rayfin up --dry-run`, deploys, then checks `rayfin up status`. |
| Rollback | same workflow | Run it again with `ref` set to a previous commit or tag. |

Merging a pull request never deploys.

### App delivery vs. data dependencies

This workflow delivers the app item **and the app-owned data schema**. Enabling Rayfin's MSSQL data service can provision app-managed storage and incurs capacity usage. The first Workbench deployment therefore requires explicit approval for that schema/service change. It does not repopulate Gold, modify the semantic model, or change shared data permissions.

The source model, Gold tables, and their security have their own blueprint deployment (`deploy-dev.yml`) and data-change approvals. App-owned diagnoses/actions are a separate operational data lifecycle, not new Gold tables or copies of source event data.

**Rollback is schema-aware:** a previous ref redeploys code/configuration, not a database backup. Preserve app records and use a schema-compatible release. Never use `--force`, drop tables, or disable the data service to simulate a rollback; review any migration first.

### Current delivery blocker

GitHub deployment fails at runtime settings synchronization with `403: Could not verify Build permission on semantic model` ([#55](https://github.com/frdeange/unily-fabric-blueprint/issues/55)).
The approved Workbench deployment reproduced this on the merged source.
Read-only Entra sign-in audit correlation confirmed that the run used the
expected automation principal and the matching GitHub protected-dev federated
credential. A fresh model-access read confirmed that same principal has
`ReadWriteExplore` (including Build); earlier workspace inspection showed
Contributor access. A mismatched deployment identity therefore does not explain
the observed failure. The workload's server-side Build validation path is still
unknown; do not change permissions or source-model security speculatively.

The workflow and local static checks are not evidence that automated deployment, live persistence, or owner isolation has passed. Before releasing the Workbench, resolve that blocker and test create, reload, edit, action progression, and access denial with a second user against the deployed data service. No live persistence result is claimed by this source change.

Before deployment, `scripts/deployment-identity.mjs` compares the Azure CLI token's
client/tenant claims with the configured identity and compares Fabric/Power BI
principal claims. It logs comparisons, never tokens or identifiers. This is
diagnostic claim inspection, not cryptographic token validation. It then makes a
read-only model-access request and reports only the matching app principal's
direct permission names. Missing direct entries cannot rule out inherited access.

The [Get Dataset Users In Group API](https://learn.microsoft.com/rest/api/power-bi/datasets/get-dataset-users-in-group)
requires **ReadWriteReshare**, which is not the same as Build (`Explore`).
A 403 on this diagnostic is explicitly inconclusive: do not grant Reshare simply
to make the diagnostic pass, and do not interpret it as proof of missing Build.
Neither this diagnostic nor a successful dry run proves the workload's separate
runtime-settings validation will accept the connector. Identity mismatch,
malformed responses and transport failures stop deployment with sanitized errors.

### Required environment setup (one-time, by a repository admin)

- `dev` environment secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` (already used by the Fabric deployment), `RAYFIN_WORKSPACE_ID`, `RAYFIN_SEMANTIC_MODEL_ID`.
- The federated identity needs permission to create and edit the app item in the target workspace.
- Fabric tenant settings: Fabric apps (preview) and Semantic Model Execute Queries REST API.
