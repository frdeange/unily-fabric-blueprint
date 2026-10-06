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
- `.github/workflows/ci.yml`: CI only, without deployment credentials.

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
GitHub-to-Fabric authentication and CD will be configured separately, preferably
using Microsoft Entra workload identity federation rather than a stored client
secret. No repository or workflow currently has access to Fabric.

Do not commit credentials, user mappings, lab results, customer data, or notebook
outputs. Synthetic test strings are permitted. Real environment identifiers
must remain outside this public repository, in private deployment configuration
or Fabric Variable Libraries. CI rejects GUIDs other than the example allowlist,
including GUIDs in notebook metadata. This does not cover every identifier format.

This repository starts with a new sanitized history, not the original lab
repository history. Changes here do not modify the running Fabric laboratory.

CI checks and content guards reduce mistakes but are not a comprehensive secret
scanner or a guarantee of PII removal. Branch protection and required reviews
must be configured separately according to the GitHub plan.

The current processing flow is a bounded single-writer, first-load PoC. A
successful unchanged batch skips inference and writes; changed inputs against
populated Silver are rejected. Deployment is separate from execution. The RAW
generator overwrites synthetic fixtures and must never run automatically as
part of a deployment.
