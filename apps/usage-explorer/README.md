# Tenant Product Usage Explorer (Rayfin app)

A small Fabric app (Rayfin, preview) that reads the **synthetic** `ProductAnalytics_Safe` semantic model live and shows product usage per tenant: key figures, events and active users by tenant, a monthly trend and feature usage.

It exists to demonstrate an application delivery route on Fabric: issue, branch, pull request, automated checks, gated deployment and rollback. The data is synthetic and the lab it comes from is our own technical hypothesis, not confirmed customer architecture.

## Data

- Connector `productanalytics` (type `fabric-semanticmodel`, delegated auth): every query runs as the signed-in user, so the model's own security applies.
- Queries (DAX) live in `packages/frontend/src/queries/usage.ts` and use only measures and columns that exist in the model: `Events`, `Active users`, `Tenants`, `Average duration (s)`, `dim_tenant`, `dim_feature`, `dim_date`.
- No mock data is shipped. If the model is unreachable the panels show an error.

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

This workflow delivers only the app item. The semantic model, Gold tables and their security are delivered by the blueprint's Fabric deployment (`deploy-dev.yml`) and a `data-change` issue. The app does not create or change data items or permissions.

### Required environment setup (one-time, by a repository admin)

- `dev` environment secrets: `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` (already used by the Fabric deployment), `RAYFIN_WORKSPACE_ID`, `RAYFIN_SEMANTIC_MODEL_ID`.
- The federated identity needs permission to create and edit the app item in the target workspace.
- Fabric tenant settings: Fabric apps (preview) and Semantic Model Execute Queries REST API.
