# Unily Fabric Blueprint

Public reference implementation for synthetic multi-tenant product analytics.

## Current scope

| Notebook | Purpose |
| --- | --- |
| `ProductAnalytics_Build` | Generate separate synthetic A/B/C RAW sources. |
| `ProductAnalytics_BronzeToSilver` | Resolve tenant-scoped identities, protect free text with Fabric AI Functions, and publish Silver. |

| Pipeline | Purpose |
| --- | --- |
| `ProductAnalytics_Process` | Production path: read-only validation, then Bronze-to-Silver. Schedule this one. |
| `ProductAnalytics_Demo` | Reproduction: synthetic RAW load (`Build`), then invokes `ProductAnalytics_Process`. Never schedule. |

This is the existing lab baseline, not a production deployment framework.
Workspace, lakehouse and logical item references are fictitious example IDs.
The code intentionally rejects execution with these example values.
Notebooks read validated runtime configuration and expose documented phases.
Gold publication, incremental ingestion, and production runtime identity are
not implemented.

## Repository layout

- `fabric/<layer>/`: Fabric item definitions; the layer (`data`, `analytics`,
  `vault`) selects the target workspace.
- `config/environments/<env>/`: non-identifier environment settings.
- `src/product_analytics/`: RAW generator, identity phase, event phase, and exact-span masking.
- `tests/`: standard-library tests using synthetic data; no Fabric access.
- `tools/`: reproducibility and repository-content checks.
- `config/product-analytics.example.json`: non-executable configuration contract.
- `.github/workflows/ci.yml`: read-only CI, without Fabric credentials.
- `.github/workflows/verify-fabric.yml`: manually approved OIDC connection check.
- `.github/workflows/issue-triage.yml` and `issue-link.yml`: issue classification
  and pull-request issue-link check.
- `.github/ISSUE_TEMPLATE/`: structured issue forms.
- `docs/architecture.md`: target workspaces (Data, Analytics, Vault per
  environment), access model and the mandatory naming convention.

Items follow `fabric/<domain>/<type>/<Name>.<FabricType>/`. Keep each item's
definition and `.platform` together. Semantic models will use TMDL under
`semantic-models/`, and Variable Libraries will use `variable-libraries/`.
Support will follow the same domain layout when its sanitized definitions are
added. Do not add empty placeholder folders or duplicate code for dev/pre/prod.
Environment references belong in private configuration, not domain folders.
Shared code will go in `src/shared/` when there is an actual shared consumer.

## Runtime configuration

Both notebooks use the active values of a Variable Library in the Data workspace
named `ProductAnalytics_Config`. Pipelines resolve the library values and inject
all of them as notebook parameters; an interactive run leaves the parameters as
`None` and reads the library through NotebookUtils. Partial parameters are rejected.
No fallback environment or configuration is embedded in the generated code cells.
Configure these variables before running:

| Variable | Fabric type | Purpose |
| --- | --- | --- |
| `data_workspace_id` | String | Data workspace (Bronze, Silver, Gold). |
| `vault_workspace_id` | String | Vault workspace (identity mapping and audit). |
| `bronze_id` | String | RAW lakehouse ID (Data). |
| `silver_id` | String | Protected events lakehouse ID (Data). |
| `identity_id` | String | Mapping and restricted audit lakehouse ID (Vault). |
| `sources_json` | String | JSON array of tenant/user-table/event-table entries. |
| `pii_policy_version` | String | Version label matching the reviewed PII policy. |
| `pii_model` | String | Fabric AI Functions deployment name. |
| `allow_synthetic_overwrite` | Boolean | Explicit opt-in for RAW fixture overwrite; normally false. |

The public example and matching Variable Library item define the contract.
Settings without identifiers come from `config/environments/<env>/`; workspace
and lakehouse IDs are resolved by name during deployment and written only to a
temporary deployment directory, never to the checkout.
Never commit populated environment value sets.
Missing variables, invalid GUIDs, example IDs, duplicate lakehouse IDs, a Vault
workspace equal to the Data workspace, invalid
source table names and duplicate tenant/table entries fail before data access.
Configuration values are not printed by the configuration cell.

`sources_json` supports one Product user namespace per tenant. Identity and
event phases consume the same registry, so table names can change or more tenants
can be onboarded without editing those phases. This does not provide arbitrary
connector ingestion, multiple source namespaces per tenant or incremental loads.
The synthetic generator deliberately remains limited to the A/B/C fixture.
Fixture companies, actions and test narratives remain versioned English test data,
not environment configuration. The prompt/schema and masking code also remain
reviewed code; changing a policy label alone does not change the detector.

Notebooks no longer attach a default lakehouse through environment-bound metadata.
All reads and writes use absolute paths built from validated configuration.
Logical `.platform` IDs remain stable. Spark session/environment dependencies
still need verification in Fabric before publication/execution is considered ready.

Cells are separated into configuration, identity, event validation, PII processing
and publication, with English Markdown and stable cell IDs. Run the entire
notebook in order; manually rerunning publication cells is not a supported retry.
The source registry is included in the batch fingerprint to avoid reusing a marker
for a different set of input tables. This intentionally changes the fingerprint
from the earlier lab baseline: an existing populated Silver table will be held
for manual migration review, not silently reprocessed or overwritten. No reset
or marker migration is automated in this change.

For a non-mutating Spark preflight, run `ProductAnalytics_BronzeToSilver` with
the Boolean notebook parameter `validate_only=true`. The parameter cell is
tagged for Fabric job injection. After loading configuration, the notebook
checks pandas/AI Functions/Delta imports, reads registered user/event tables,
mapping and Silver schemas, counts snapshot rows and checks stable table versions.
It then exits before identity processing, inference, publication or audit writes.
This verifies imports and storage access, not model availability or inference.
Do not omit the parameter for a preflight: its normal-processing default is false.
This mode does not run the RAW generator or change the legacy completion marker.

NotebookUtils currently does not support Variable Library reads by service
principals; parameter injection by the pipelines avoids that read. A notebook run
from a pipeline uses the identity of the pipeline's last modifier. Because the
deployment publishes the pipelines, that is the deployment service principal, and
a schedule runs as whoever created or last updated it. Whether AI Functions and
cross-workspace OneLake writes work under a service principal is validated in #18.

The deployment allowlist includes the Bronze, Silver and Gold lakehouses (Data),
the Identity lakehouse (Vault), the two Product notebooks, their configuration library
and the two Product pipelines.
Adding another item requires explicitly extending that allowlist and its tests.
Semantic-model publication is not implemented yet.
Folder organization does not grant permissions or isolate data.

## Contribution workflow

Every change starts with an issue created from a form. Triage normalizes its
title to `[Type] Area: summary` and applies emoji labels. Work on an
`<feature|fix|maintenance|docs>/<issue>-<slug>` branch from `main` and open a pull request
that contains exactly one `Closes #<issue>` reference. Merge only after required
CI and the `Linked issue` check succeed. See `.github/CONTRIBUTING.md`; AI agents
also follow `.github/copilot-instructions.md`.
`.github/CODEOWNERS` assigns ownership by domain and item type, including the
automation and CODEOWNERS file itself. All owners currently map to the solo
repository owner. Independent owner review is not enforced; enable it when
eligible collaborators are available. Owners must have repository write access.

Install the local hooks once in your development environment:

```powershell
python -m pip install -r requirements-dev.txt
python -m pre_commit install
python -m pre_commit run --all-files
```

The pinned `nbstripout` hook removes notebook outputs and execution counts.
Review any automatic changes and stage them again before committing. The hooks
also check repository content and generated notebook consistency. CI runs the
same hooks on all tracked files and rejects changes they would make, even when
local hooks were skipped. Never treat output stripping as secret scanning:
secrets in source cells remain unsafe, and notebook attachments are rejected.

## Local checks

Run with Python 3.11:

```powershell
python tools\check_repository.py
python tools\build_notebooks.py --check
python -m unittest discover -s tests -v
```

To regenerate code cells after editing sources:

```powershell
python tools\build_notebooks.py
```

Notebook metadata uses example logical item IDs. Do not edit generated
code cells independently from their source.

## Delivery boundaries

A push or successful CI run does not deploy or execute anything in Fabric.
`main` requires a pull request, successful `validate` CI against an up-to-date
branch and resolved conversations. These rules apply to administrators.
Independent PR approval is not required for this solo-owner lab.

The manual **Verify Fabric connection** workflow uses Microsoft Entra workload
identity federation, not a password or client secret. Its `dev` environment
allows only `main`, requires owner approval and disables administrator bypass.
The owner can approve their own run for this solo-owner lab; production should
use independent reviewers. The Entra trust is scoped to this repository's `dev`
environment. CI on pull requests cannot access those environment secrets.

Configure `AZURE_CLIENT_ID` and `AZURE_TENANT_ID` as `dev` Environment Secrets,
never as committed files. Workspaces are found by name (`Unily-<Layer>-Dev`),
so no workspace ID is stored. The identity has Contributor access to the three
dev workspaces, not Azure subscription roles. Contributor permits more than
publication, including workspace data access; the verification workflow only
lists workspaces and checks that each expected name appears exactly once.
The tenant already permits service principals to use Fabric public APIs.
No tenant setting is changed by this setup.

After merging this foundation, run **Verify Fabric connection** from `main`
and approve the pending `dev` environment gate. This verifies authentication and
workspace access without publishing, deleting or running items. Deployment is
is a separate manually approved workflow. Processing still requires delegated
runtime/Spark verification and a review of the existing Silver completion marker.

## Manual dev deployment

**Deploy dev environment** deploys only the allowlisted items from approved
`main` through the `dev` gate: first the Vault lakehouse, then the Data
lakehouses, then `ProductAnalytics_Config`, the two Product notebooks and the two
pipelines in one publication, so pipeline references to notebooks and to the other
pipeline resolve to the deployed item IDs. It uses
`fabric-cicd` 1.3.0 with Azure CLI OIDC credentials. It does not call orphan
cleanup, create workspace folders, deploy models/agents, execute notebooks or
refresh data. Lakehouses are created schema-enabled and empty; existing item IDs
are verified after update.
The deployment is not atomic; a failed publication may require a reviewed retry.

The Variable Library values combine the reviewed settings file with the IDs
resolved from the target workspaces. Lakehouse IDs must be distinct and
`allow_synthetic_overwrite` must be false. Temporary staging flattens the explicit item allowlist for
publication; it never broadly scans/publishes the whole repository.
An explicit `dev` value set is generated and activated by the package.

After publication, definition readback checks notebook cell content, absence
of outputs, configured library values, the active value set, and pipeline
activities, dependencies, parameters and resolved references. It also checks
that pre-existing item IDs survive, lakehouses are schema-enabled, and no
unexpected items appear/disappear (SQL analytics endpoints created by Fabric for
each lakehouse are expected).
This proves definition publication, not Spark execution, PII processing or
unchanged table versions. Those require separate delegated validation.
No completed marker is rewritten and no Silver/Identity data is reset.

Private resolved files are removed with the temporary directory. Package debug
file logging is disabled, and environment IDs are individually masked in Actions.
Do not enable debug logs, upload resolved staging or publish request/response
payloads as public workflow artifacts.

Do not commit credentials, user mappings, lab results, customer data, or notebook
outputs. Synthetic test strings are permitted. Real environment identifiers
must remain outside this public repository, in private deployment configuration
or Fabric Variable Libraries. CI rejects GUIDs other than the example allowlist,
including GUIDs in notebook metadata. This does not cover every identifier format.

This repository starts with a new sanitized history, not the original lab
repository history. Changes here do not modify the running Fabric laboratory.

CI checks and content guards reduce mistakes but are not a comprehensive secret
scanner or a guarantee of PII removal.

The current processing flow is a bounded single-writer, first-load PoC. A
successful unchanged batch skips inference and writes; changed inputs against
populated Silver are rejected. Deployment is separate from execution. The RAW
generator performs an initial load into empty Bronze tables and refuses to
overwrite existing tables unless `allow_synthetic_overwrite` is explicitly true.
It must never run automatically as part of a deployment.

## Reproducing the scenario

1. Provision the three workspaces and run **Deploy dev environment**.
2. In `Unily-Data-<Env>`, run the `ProductAnalytics_Demo` pipeline once. It loads
   the synthetic A/B/C RAW tables into empty Bronze tables, then runs
   `ProductAnalytics_Process` (validation, then Bronze-to-Silver).
3. Later runs use `ProductAnalytics_Process` only. An unchanged batch is a no-op.
   Rerunning `ProductAnalytics_Demo` against populated Bronze fails by design
   in `Build` unless `allow_synthetic_overwrite` is explicitly true.
