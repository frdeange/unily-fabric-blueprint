# Product Analytics semantic model

`ProductAnalytics_Safe` is the business semantic model for product analytics.
It lives in `Unily-Analytics-<Env>`, reads the Gold star schema in
`Unily-Data-<Env>` ([contract](gold-contract.md)) and isolates tenants with
row-level security (RLS). Names follow [architecture](architecture.md#3-naming-convention).

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

| Role | Filter | Members (`<Env>` groups) |
| --- | --- | --- |
| `TenantA` | `[tenant_id] = "tenant_a"` | `Unily-Analytics-<Env>-TenantA` |
| `TenantB` | `[tenant_id] = "tenant_b"` | `Unily-Analytics-<Env>-TenantB` |
| `TenantC` | `[tenant_id] = "tenant_c"` | `Unily-Analytics-<Env>-TenantC` |
| `UnilyAll` | none | `Unily-Analytics-<Env>-AllTenants` |

A tenant role exists for every tenant in the environment settings; deployment
rejects a configured tenant without a role or a role with a different filter.

## Deployment

**Deploy dev environment** publishes the model in a fourth stage, after the
Data items. The repository stores two example placeholders in
`definition/expressions.tmdl`: `...0019` (Data workspace) and `...0011`
(the Gold lakehouse). Staging replaces them with the resolved IDs, so the
source becomes `https://onelake.dfs.fabric.microsoft.com/<Data>/<Gold>`.
After publication, readback compares tables, columns, measures, partitions,
relationships, roles and the source with the staged copy.

Fabric drops role members and connection bindings from a definition, so the
deployment never sets them and never refreshes the model.

## Steps after the first deployment

Done once per environment by a workspace admin, signed in with `az login`.
Each step changes Fabric and needs explicit approval. Resolve workspace,
model, connection and group IDs by name at run time; never store them. Record
each run in the private deployment log.

| Step | Method |
| --- | --- |
| 1. **Take over** the model, because only the owner can bind it (the deployment service principal owns the published model) | Power BI REST: `POST groups/{workspace}/datasets/{model}/Default.TakeOver` |
| 2. **Bind the connection.** List the model's data source references, then bind the OneLake reference to `conn-unily-analytics-<env>-gold-onelake` (connectivity `ShareableCloud`), echoing `connectionDetails` exactly. Relist to confirm | Fabric REST: `GET workspaces/{workspace}/items/{model}/connections`, then `POST workspaces/{workspace}/semanticModels/{model}/bindConnection` |
| 3. **Refresh** the model once and confirm that the refresh history reports `Completed` | Power BI REST: `POST`, then `GET groups/{workspace}/datasets/{model}/refreshes` |
| 4. **Assign role members.** Add each group to its role as listed in the role table | **Portal only**: model, *Security*. There is no supported API for role membership |
| 5. **Share the model** with the four consumer groups as `ReadExplore` (Read and Build, no reshare, no workspace access) | Power BI REST: `POST groups/{workspace}/datasets/{model}/users` |
| 6. **Validate** the matrix below | DAX `executeQueries` signed in as each test user; T-SQL against the Gold SQL analytics endpoint must be denied |

Calls to the Fabric API carry the header
`x-ms-fabric-skill: semantic-model-authoring`. The Fabric API uses the audience
`https://api.fabric.microsoft.com`; the Power BI API uses
`https://analysis.windows.net/powerbi/api`.

A later redeployment updates the definition in place. Confirm that the
binding and the role members survive; repeat steps 1 to 4 if they do not.

## Validation matrix

| Principal | Expected result |
| --- | --- |
| Member of `Unily-Analytics-<Env>-TenantA` | Only `tenant_a` rows (dev: 1,344 events, 12 users) |
| Member of `Unily-Analytics-<Env>-TenantB` | Only `tenant_b` rows (dev: 2,016 events, 18 users) |
| Member of `Unily-Analytics-<Env>-TenantC` | Only `tenant_c` rows (dev: 2,688 events, 24 users) |
| Member of `Unily-Analytics-<Env>-AllTenants` | All tenants |
| Model access without a role | Denied (`RLSNotAuthorizedForModel`) |
| No model access | Denied (`PowerBIEntityNotFound`) |
| Any consumer, Gold SQL analytics endpoint or OneLake | Denied |

The dev counts come from the synthetic scenario and change if the generator
changes. A first query by a new user can briefly return `PowerBIEntityNotFound`;
retry before treating it as a failure.

In dev, one synthetic test user receives a direct share without a role to
cover the *model access without a role* case. This test-only share is the
single exception to the group-only rule.
