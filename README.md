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
External configuration and readable notebook cells are the next changes.
Gold publication, incremental ingestion, and production runtime identity are
not implemented.

## Repository layout

- `fabric/`: only the two operational Fabric item definitions.
- `src/`: RAW generator, identity phase, event phase, and exact-span masking.
- `tests/`: standard-library tests using synthetic data; no Fabric access.
- `tools/`: reproducibility and repository-content checks.
- `.github/workflows/ci.yml`: read-only CI, without Fabric credentials.
- `.github/workflows/verify-fabric.yml`: manually approved OIDC connection check.

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
still unimplemented and must wait for private environment binding of notebook
references.

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
