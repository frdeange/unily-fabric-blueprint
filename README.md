# Unily Fabric Blueprint

Public reference implementation for synthetic multi-tenant product analytics.

## Current scope

| Notebook | Purpose |
| --- | --- |
| `ProductAnalytics_Build` | Generate separate synthetic A/B/C RAW sources. |
| `ProductAnalytics_BronzeToSilver` | Resolve tenant-scoped identities, protect free text with Fabric AI Functions, and publish Silver. |

This is the existing lab baseline, not a production deployment framework.
Workspace, lakehouse and logical item references are fictitious example IDs.
The code intentionally rejects execution with these example values.
Notebooks read validated runtime configuration and expose documented phases.
Gold publication, incremental ingestion, and production runtime identity are
not implemented.

## Repository layout

- `fabric/product-analytics/notebooks/`: the two operational Fabric definitions.
- `src/product_analytics/`: RAW generator, identity phase, event phase, and exact-span masking.
- `tests/`: standard-library tests using synthetic data; no Fabric access.
- `tools/`: reproducibility and repository-content checks.
- `config/product-analytics.example.json`: non-executable configuration contract.
- `.github/workflows/ci.yml`: read-only CI, without Fabric credentials.
- `.github/workflows/verify-fabric.yml`: manually approved OIDC connection check.

Items follow `fabric/<domain>/<type>/<Name>.<FabricType>/`. Keep each item's
definition and `.platform` together. Semantic models will use TMDL under
`semantic-models/`, and Variable Libraries will use `variable-libraries/`.
Support will follow the same domain layout when its sanitized definitions are
added. Do not add empty placeholder folders or duplicate code for dev/pre/prod.
Environment references belong in private configuration, not domain folders.
Shared code will go in `src/shared/` when there is an actual shared consumer.

## Runtime configuration

Both notebooks load the active values of a same-workspace Variable Library
named `ProductAnalytics_Config` using NotebookUtils. No fallback environment
or configuration is embedded in the generated code cells. Configure these
variables before running:

| Variable | Fabric type | Purpose |
| --- | --- | --- |
| `workspace_id` | String | Workspace containing all three lakehouses. |
| `bronze_id` | String | RAW lakehouse ID. |
| `silver_id` | String | Protected events lakehouse ID. |
| `identity_id` | String | Mapping and restricted audit lakehouse ID. |
| `sources_json` | String | JSON array of tenant/user-table/event-table entries. |
| `pii_policy_version` | String | Version label matching the reviewed PII policy. |
| `pii_model` | String | Fabric AI Functions deployment name. |
| `allow_synthetic_overwrite` | Boolean | Explicit opt-in for RAW fixture overwrite; normally false. |

The public example defines the contract, not a deployment-ready library item.
Real values must be supplied privately in Fabric. The library has not been
created or published by this PR. Add its sanitized item definition in a later
approved deployment change; never commit populated environment value sets.
Missing variables, invalid GUIDs, example IDs, duplicate lakehouse IDs, invalid
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

NotebookUtils currently does not support Variable Library reads by service
principals. Notebook execution remains delegated to the lab user; the GitHub
OIDC identity is for publication, not processing. This limitation must be resolved
before scheduling these notebooks with a service identity.

The current deployment allowlist still includes only the two Product notebooks.
Adding another item requires explicitly extending that allowlist and its tests.
There is no deployment discovery or semantic-model publication implemented yet.
Folder organization does not grant permissions or isolate data.

## Contribution workflow

Create a short-lived `feature/...`, `fix/...` or `chore/...` branch from `main`,
commit changes and open a pull request. Merge only after required CI succeeds.
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

Configure `AZURE_CLIENT_ID`, `AZURE_TENANT_ID` and `FABRIC_WORKSPACE_ID` as `dev`
Environment Secrets, never as committed files. The identity has Contributor
access to the Product lab workspace, not Azure subscription roles. Contributor
permits more than notebook publication, including workspace data access; the
workflow currently performs only a GET of the expected workspace.
The tenant already permits service principals to use Fabric public APIs.
No tenant setting is changed by this setup.

After merging this foundation, run **Verify Fabric connection** from `main`
and approve the pending `dev` environment gate. This verifies authentication and
workspace access without publishing, deleting or running items. Deployment is
still unimplemented and must wait for private Variable Library setup and Spark
dependency verification.

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
generator overwrites synthetic fixtures and must never run automatically as
part of a deployment.
