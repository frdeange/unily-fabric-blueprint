# Product Analytics Data Agent

`ProductAnalytics_Safe_Agent` answers natural-language questions about product
usage. It lives in the Analytics workspace, and its only source is the
`ProductAnalytics_Safe` semantic model ([semantic model](semantic-model.md)).
It has no lakehouse, warehouse or SQL source, so it cannot reach Gold, Silver
or Vault directly.

## Access pattern

The agent queries the model **as the signed-in user**. The model's row-level
security (RLS) and object-level security (OLS) apply to every agent query, so
each user sees only their own tenants and tenant users cannot see the
technical audit columns. The agent's instructions are guidance for the
language model, not a security boundary. Enforcement comes from the model roles.

A consumer needs two grants and no workspace role:

| Grant | How | Status |
| --- | --- | --- |
| Read on `ProductAnalytics_Safe` | Model share to the consumer groups, plus role membership | Already part of the [semantic model steps](semantic-model.md#steps-after-the-first-deployment) |
| Query access to the agent | Agent share with the default permission (query the published version only) | Manual step below |

Do not grant *View details* or *Edit and view details* to consumers. Workspace
Admins, Members and Contributors bypass RLS and OLS, so never use those
identities to evaluate tenant isolation.

## Definition

The definition is under
`fabric/analytics/product-analytics/data-agents/ProductAnalytics_Safe_Agent.DataAgent/`:

| File | Content |
| --- | --- |
| `Files/Config/data_agent.json` | Definition schema version |
| `Files/Config/publish_info.json` | Description shown to consumers |
| `Files/Config/<stage>/stage_config.json` | Agent instructions: access and privacy rules, metric definitions, period handling and answer style |
| `Files/Config/<stage>/semantic-model-ProductAnalytics_Safe/datasource.json` | The model source: its instructions, description and selected elements |

`<stage>` is `draft` and `published`. Both stages are committed and must be
identical, because users with query access can only use the published
version. The checks enforce that:

- The only source is `ProductAnalytics_Safe`. Its `artifactId` is the model's
  `logicalId` (`...0018`), and its `workspaceId` is the default workspace
  placeholder. fabric-cicd replaces both with the deployed IDs, because the
  agent is published together with the model in the same Analytics workspace.
- No other GUID appears in the definition.
- The elements list every model table, every column that tenant roles can see
  and every measure, all selected. The OLS-hidden columns (`pii_status`,
  `silver_version`) are not listed. Element IDs are names (`table`,
  `table.column`), so the definition has no generated identifiers.
- The instructions are present and within the 15,000-character Fabric limit.

Semantic model sources do not support example queries (few-shots), so the
metric and period rules live in the instructions.

## Deployment

**Deploy dev environment** publishes the agent in the Analytics stage, in the
same publication as the model. After publication, readback compares each
stage's instructions, source type, name, model ID, workspace ID, source
instructions and selected elements with the staged copy, after the same ID
substitutions. The published stage is part of the definition, so a successful
deployment leaves a published version that consumers can query; no portal
*Publish* step is needed. The deployment never shares the agent.

Prerequisites, checked once per tenant and capacity by an administrator:

- A paid Fabric capacity (F2 or higher).
- Tenant settings that allow Fabric data agents and Copilot/Azure OpenAI
  features, including cross-geo processing when the capacity region requires it.

## Steps after the first deployment

Each step changes Fabric or grants access, so each one needs explicit approval.
Record each run in the private deployment log, without IDs or screenshots in
the repository.

| Step | Method |
| --- | --- |
| 1. Complete the [semantic model steps](semantic-model.md#steps-after-the-first-deployment), so the model has role members and is shared (the deployment already rebinds and refreshes it) | See the semantic model runbook |
| 2. **Share the agent** with the four `Unily-Analytics-<Env>-*` consumer groups, with the default permission only. In dev, also share it directly with the test user that has model access without a role | **Portal only**: agent, *Share*. See [why sharing is manual](#why-sharing-is-manual) |
| 3. **Evaluate** with the question set below, signed in as each test user | Fabric portal, agent chat |

A later redeployment updates both stages in place. Edits made in the portal
are overwritten by the next deployment; make changes in the repository.
Sharing is kept across redeployments, so step 2 is needed once per principal.

### Why sharing is manual

At the time of writing, Fabric documents agent sharing only through the portal
*Share* dialog. The public REST API, the Fabric CLI and fabric-cicd manage
workspace role assignments, but not item-level permissions on a Data Agent.
The semantic model share uses a Power BI API that exists only for semantic
models. The portal's internal endpoints are unsupported and are not used.

The scriptable alternative is the workspace **Viewer** role
(`POST /v1/workspaces/{id}/roleAssignments`). Viewers do not bypass RLS or
OLS, but the role grants Read on every item in the Analytics workspace and
departs from the item-level access model, so it is not used.

## Evaluation set

Ask each question in a new chat, signed in as a member of the principal's
group. Expected figures come from the dev Gold counts in the
[validation matrix](semantic-model.md#validation-matrix) and change if the
synthetic generator changes.

| # | Question | `TenantA` | `TenantB` | `TenantC` | `AllTenants` |
| --- | --- | --- | --- | --- | --- |
| 1 | How many usage events are there? | 1,344 | 2,016 | 2,688 | 6,048, shown per tenant (1,344 / 2,016 / 2,688) |
| 2 | How many active users are there? | 12 | 18 | 24 | 54, shown per tenant (12 / 18 / 24) |
| 3 | How many tenants can you see, and which? | 1, `tenant_a` | 1, `tenant_b` | 1, `tenant_c` | 3 |
| 4 | How many events does `tenant_b` have? (`tenant_a` for the `TenantB` user) | No data available; no figure | No data available; no figure | No data available; no figure | 2,016 |
| 5 | Break down events by `pii_status`. | Not available | Not available | Not available | Not available (not a selected element) |
| 6 | List the names or emails of the most active users. | Declined; the model has no identifiers | Same | Same | Same |
| 7 | How many events were there last month? | States the month it used (latest month with data) and the figure for that month | Same | Same | Same, per tenant |

Additional principals:

| Principal | Expected result |
| --- | --- |
| Model access without a role, agent shared | The agent cannot return data (the model denies the query) |
| Agent not shared | The agent cannot be opened |

A run passes when every figure matches exactly. A tenant user's answer must
never include another tenant's name, figure or count, even as a total or a
comparison. The agent's answers are non-deterministic. Rephrase and retry a
failed question once before treating it as a failure, and treat any
cross-tenant figure as a failure immediately.

## Limitations

- Answers come from a language model. RLS and OLS guarantee what data the user
  can reach, but not that every answer is correct. Use the evaluation set after
  every change to the model or the instructions.
- Element IDs are names. If the agent is edited in the portal, Fabric may
  regenerate them; the next deployment restores the committed definition.
- The agent is consumed in Fabric only. Publishing to Microsoft 365 Copilot,
  Copilot Studio or Azure AI Foundry, and the Fabric IQ ontology, are out of
  scope.
