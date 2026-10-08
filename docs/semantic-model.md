# Product Analytics semantic model

`ProductAnalytics_Safe` is the business semantic model for product analytics.
It lives in `Unily-Analytics-<Env>`, reads the Gold star schema in
`Unily-Data-<Env>` ([contract](gold-contract.md)), isolates tenants with
row-level security (RLS) and hides technical columns from tenants with
object-level security (OLS). Names follow [architecture](architecture.md#3-naming-convention).

Definition: `fabric/analytics/product-analytics/semantic-models/ProductAnalytics_Safe.SemanticModel/` (TMDL).

## Access pattern

The pattern was validated with seven synthetic users in #28:

1. **Storage mode: Direct Lake on OneLake.** The model reads the Gold Delta
   tables of the `product` schema directly. There is no import copy and no
   scheduled refresh of data; a refresh only reframes the model to the latest
   Gold version.
2. **Fixed identity.** The model reads Gold with the Analytics workspace
   identity (`Unily-Analytics-<Env>`) through the cloud connection
   `conn-unily-analytics-<env>-gold-onelake` (Azure Data Lake Storage,
   workspace identity, single sign-on disabled). Consumers need no access to
   Gold, its OneLake files or its SQL analytics endpoint.
3. **Semantic model RLS.** Roles filter `tenant_id` on `dim_tenant`,
   `dim_user` and `fact_usage_event`. A consumer outside every role is denied.
4. **Semantic model OLS.** The same tenant roles hide technical audit
   columns (see [Object-level security](#object-level-security)).

The workspace identity has the Viewer role on `Unily-Data-<Env>` and is the
only member of the Gold OneLake security role `AnalyticsReader` (`Tables`, read).

Rejected for now: OneLake security RLS enforced with each consumer's own
identity (single sign-on). It would grant consumers access to Gold and move
tenant isolation into the Data workspace. It remains a possible evolution
when the same rules must also protect other engines.

## Model contents

| Table | Gold source | Notes |
| --- | --- | --- |
| `fact_usage_event` | `product.fact_usage_event` | Measures: `Events`, `Active users`, `Total duration (s)`, `Average duration (s)`, `Events with feedback`, `Tenants` |
| `dim_user` | `product.dim_user` | Pseudonymous; no identity columns exist in Gold |
| `dim_feature` | `product.dim_feature` | |
| `dim_tenant` | `product.dim_tenant` | |
| `dim_date` | `product.dim_date` | |

- Every Gold contract column is included, including the protected
  `feedback_text`. Columns never summarize implicitly
  (`discourageImplicitMeasures`).
- Relationships (many to one): `fact_usage_event` to `dim_tenant`
  (`tenant_id`), `dim_user` (`user_key`, globally unique), `dim_feature`
  (`feature_id`) and `dim_date` (`event_date` to `date`).

| Role | Filter | Hidden columns (OLS) | Members (`<Env>` groups) |
| --- | --- | --- | --- |
| `TenantA` | `[tenant_id] = "tenant_a"` | `fact_usage_event[pii_status]`, `[silver_version]` | `Unily-Analytics-<Env>-TenantA` |
| `TenantB` | `[tenant_id] = "tenant_b"` | same | `Unily-Analytics-<Env>-TenantB` |
| `TenantC` | `[tenant_id] = "tenant_c"` | same | `Unily-Analytics-<Env>-TenantC` |
| `UnilyAll` | none | none | `Unily-Analytics-<Env>-AllTenants` |

A tenant role exists for every tenant in the environment settings; deployment
rejects a configured tenant without a role, a role with a different filter or
a role whose hidden objects differ from the table above.

## Object-level security

Tenant roles set `metadataPermission: none` on two technical audit columns of
`fact_usage_event`: `pii_status` (pseudonymisation outcome) and
`silver_version` (lineage). They describe the platform, not the tenant's
product usage. `feedback_text` stays visible to tenants: it is already
protected in Silver and filtered by RLS. `UnilyAll` sees every object.

```tmdl
tablePermission fact_usage_event = [tenant_id] = "tenant_a"

	columnPermission pii_status
		metadataPermission: none
```

Behaviour:

- A hidden column behaves as if it did not exist. A query that references it
  fails with an error saying the column cannot be found; it is also absent
  from the schema and the field list. No measure references the hidden
  columns, so every measure keeps working for tenants.
- OLS applies to consumers with item access (Read/Build) and to workspace
  Viewers. Workspace Admins, Members and Contributors bypass RLS and OLS.
- **RLS and OLS must live in the same roles.** A user who belongs to one role
  with RLS and another role with OLS gets an error on every query. Here OLS is
  added to the tenant roles that already filter rows, and `UnilyAll` has
  neither, so a user in a tenant group and `AllTenants` sees the union
  without error. Do not create OLS-only roles.
- OLS cannot hide a table that breaks a relationship chain, and a measure that
  references a hidden object becomes unavailable to the role. Hide new objects
  only after checking both.
- Copilot in Power BI and Fabric, and Data Agents that use the model as a
  source, query as the signed-in user and respect RLS and OLS. Q&A, Quick
  insights, Smart narrative and Excel data types do not support models with
  OLS.
- Marking a column hidden (`isHidden`) only hides it in report field lists; it
  is not security. OLS is the enforcement.

## Deployment

**Deploy dev environment** publishes the model in a fourth stage, after the
Data items. The repository stores two example placeholders in
`definition/expressions.tmdl`: `...0019` (Data workspace) and `...0011`
(the Gold lakehouse). Staging replaces them with the resolved IDs, so the
source becomes `https://onelake.dfs.fabric.microsoft.com/<Data>/<Gold>`.
After publication, readback compares tables, columns, measures, partitions,
relationships, roles (filters and hidden objects) and the source with the
staged copy.

Fabric does not keep role members in a definition, and updating a definition
drops its connection binding (observed in dev after #30). So after readback
every deployment, as the deployment service principal and per model:

1. **Takes over** the model, because only the owner can bind it
   (Power BI REST `POST groups/{workspace}/datasets/{model}/Default.TakeOver`).
2. **Rebinds Gold.** It resolves `conn-unily-analytics-<env>-gold-onelake` by
   name (it must be a single `ShareableCloud` connection), checks that the
   model's only data source reference has the same `connectionDetails` (type
   and path), binds it (Fabric REST
   `POST workspaces/{workspace}/semanticModels/{model}/bindConnection`) and
   relists `GET workspaces/{workspace}/items/{model}/connections` to confirm.
3. **Refreshes** once (Direct Lake framing, Power BI enhanced refresh
   `POST groups/{workspace}/datasets/{model}/refreshes`) and polls the
   refresh until `Completed`.

Any mismatch, missing binding or failed refresh fails the deployment. The
deployment service principal needs the `User` role on the connection, which
provisioning grants. Role members and sharing are never set by the deployment.

## Steps after the first deployment

Done once per environment by a workspace admin, signed in with `az login`.
Each step changes Fabric and needs explicit approval. Resolve workspace,
model, connection and group IDs by name at run time; never store them. Record
each run in the private deployment log.

| Step | Method |
| --- | --- |
| 1. **Create the connection** `conn-unily-analytics-<env>-gold-onelake` (OneLake, Analytics workspace identity, `ShareableCloud`), then rerun provisioning with `--apply` so the deployment service principal gets `User` on it | Portal, then `python tools/provision_environment.py` |
| 2. **Deploy.** The deployment takes over, binds and refreshes the model (see above) | **Deploy dev environment** workflow |
| 3. **Assign role members.** Add each group to its role as listed in the role table | **Portal only**: model, *Security*. There is no supported API for role membership |
| 4. **Share the model** with the four consumer groups as `ReadExplore` (Read and Build, no reshare, no workspace access) | Power BI REST: `POST groups/{workspace}/datasets/{model}/users` |
| 5. **Validate** the matrix below | DAX `executeQueries` signed in as each test user; T-SQL against the Gold SQL analytics endpoint must be denied |

Manual calls to the Fabric API carry the header
`x-ms-fabric-skill: semantic-model-authoring`. The Fabric API uses the audience
`https://api.fabric.microsoft.com`; the Power BI API uses
`https://analysis.windows.net/powerbi/api`.

A later redeployment updates the definition in place and repeats the
take-over, binding and refresh. Confirm that the role members survive; repeat
step 3 if they do not.

## Validation matrix

| Principal | Expected result |
| --- | --- |
| Member of `Unily-Analytics-<Env>-TenantA` | Only `tenant_a` rows (dev: 1,344 events, 12 users) |
| Member of `Unily-Analytics-<Env>-TenantB` | Only `tenant_b` rows (dev: 2,016 events, 18 users) |
| Member of `Unily-Analytics-<Env>-TenantC` | Only `tenant_c` rows (dev: 2,688 events, 24 users) |
| Tenant group member, query on `fact_usage_event[pii_status]` or `[silver_version]` | Error: column cannot be found |
| Member of `Unily-Analytics-<Env>-AllTenants` | All tenants; hidden columns queryable |
| Model access without a role | Denied (`RLSNotAuthorizedForModel`) |
| No model access | Denied (`PowerBIEntityNotFound`) |
| Any consumer, Gold SQL analytics endpoint or OneLake | Denied |

The dev counts come from the synthetic scenario and change if the generator
changes. A first query by a new user can briefly return `PowerBIEntityNotFound`;
retry before treating it as a failure.

In dev, one synthetic test user receives a direct share without a role to
cover the *model access without a role* case. This test-only share is the
single exception to the group-only rule.
