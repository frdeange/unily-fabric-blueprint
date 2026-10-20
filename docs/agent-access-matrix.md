# Agent access enforcement matrix

This document records the dev-lab validation of how the
`ProductAnalytics_Safe` security model is enforced through direct queries and
agent entry points. The test uses the same synthetic users and expected
outcomes as the [semantic model validation matrix](semantic-model.md#validation-matrix).

The evidence was collected on 8 October 2026. No workspace role, item
permission, tenant setting, licence or Fabric item was changed as part of this
validation.

## Test identities

| User | Intended access | User licence |
| --- | --- | --- |
| `testuser1` | `TenantA` role and consumer-group shares | Power BI Pro through Microsoft 365 E5 |
| `testuser2` | `TenantB` role and consumer-group shares | Power BI Pro through Microsoft 365 E5 |
| `testuser3` | `TenantC` role and consumer-group shares | Power BI Pro through Microsoft 365 E5 |
| `testuser4` | Direct model and agent shares, but no model role | Power BI Pro through Microsoft 365 E5 |
| `testuser5` | `UnilyAll` role and consumer-group shares | Power BI Free |
| `testuser6` | Viewer of the Data workspace; no Analytics model or agent share | Power BI Free |
| `testuser7` | Contributor to the Data workspace; no Analytics model or agent share | Power BI Free |

The direct-query and MCP probes acquired delegated tokens for each test user.
Portal checks used the same signed-in user. Administrators and the deployment
service principal were not used as consumer test identities because elevated
workspace roles bypass model RLS and OLS.

## Summary

| Path | Identity reaching the model | Result | RLS/OLS conclusion |
| --- | --- | --- | --- |
| Direct semantic model query | Signed-in user | Tested for all seven users | Enforced as expected |
| Power BI Copilot | Signed-in user | Not run; prerequisites and consumer access are incomplete | Expected to apply, not evidenced in this lab |
| Fabric Data Agent portal | Signed-in user | Passed for `testuser1`; group-shared access failed for other sampled users | Enforced for the one successful user; access gap blocks the full matrix |
| Published Data Agent MCP endpoint | Bearer-token user | Passed only for `testuser1`; other shared users were rejected before a query | Enforced for the one successful user; access gap blocks the full matrix |
| Data Agent in Copilot Studio | User or maker, selectable per tool | Not run; required builder licence is unavailable | Must use **User** authentication to preserve per-user enforcement |
| Data Agent in Microsoft 365 Copilot | Signed-in Microsoft 365 user | Not run; the agent was not published to Agent Store | Documented to preserve underlying RLS/OLS, not evidenced in this lab |

`Not run` is not a pass. It records a product, licence or environment
prerequisite that prevented a real-user test without changing the approved lab
configuration.

### Path by user

| User | Direct model | Power BI Copilot | Fabric Data Agent | Copilot Studio | Microsoft 365 Copilot |
| --- | --- | --- | --- | --- | --- |
| `testuser1` | Allowed: `TenantA`; OLS enforced | Not run: prerequisites incomplete | Allowed in portal and MCP; `TenantA` enforced | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser2` | Allowed: `TenantB`; OLS enforced | Not run: prerequisites incomplete | Denied unexpectedly in portal and MCP | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser3` | Allowed: `TenantC`; OLS enforced | Not run: prerequisites incomplete | MCP denied unexpectedly; portal not run | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser4` | Denied as expected: no RLS role | Not run: prerequisites incomplete | MCP denied before the model query; portal not run | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser5` | Allowed: all tenants; OLS allowed | Not run: Power BI Free on F2 | Denied unexpectedly in portal and MCP | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser6` | Denied as expected: no model access | Not run: no model access and Power BI Free on F2 | Denied as expected: no agent share | Not run: builder licence absent | Not run: agent not in Agent Store |
| `testuser7` | Denied as expected: no model access | Not run: no model access and Power BI Free on F2 | Denied as expected: no agent share | Not run: builder licence absent | Not run: agent not in Agent Store |

## Direct semantic model query

The test called Power BI `executeQueries` with a delegated token for each
user. It ran a tenant/count query and a separate query against the
OLS-protected `fact_usage_event[pii_status]` column.

| User | Outcome | Observed data | OLS probe |
| --- | --- | --- | --- |
| `testuser1` | Allowed | `tenant_a`: 1,344 events, 12 active users | Denied |
| `testuser2` | Allowed | `tenant_b`: 2,016 events, 18 active users | Denied |
| `testuser3` | Allowed | `tenant_c`: 2,688 events, 24 active users | Denied |
| `testuser4` | Denied | `RLSNotAuthorizedForModel` | Denied by the same model authorization check |
| `testuser5` | Allowed | All three tenants: 6,048 events, 54 active users | Allowed, as expected for `UnilyAll` |
| `testuser6` | Denied | `PowerBIEntityNotFound` | Denied |
| `testuser7` | Denied | `PowerBIEntityNotFound` | Denied |

This path satisfies the expected RLS and OLS matrix. It also establishes that
the source model and role membership work independently of any agent surface.

## Power BI Copilot

No real-user result is claimed for this path.

The lab capacity meets the documented minimum of paid F2. However:

- the repository model does not explicitly enable Q&A
  (`definition.pbism` has no `settings.qnaEnabled: true`);
- no report-scoped Copilot test asset is part of this implementation;
- the tenant and standalone Power BI Copilot settings were not changed or
  asserted by this test; and
- on capacity below F64, a Power BI Free user cannot consume shared Power BI
  content. Therefore `testuser5`, `testuser6` and `testuser7` cannot provide
  equivalent consumer-path evidence on the current F2 capacity.

Microsoft documents that Power BI Copilot uses the signed-in user's existing
permissions and that semantic-model RLS and OLS continue to apply. This is the
expected result for `testuser1` through `testuser4`, but it remains an
unverified expectation in this lab.

## Fabric Data Agent

The agent and semantic model permissions were inspected through the Fabric
admin APIs:

- the four consumer groups have Read on the published agent;
- `testuser4` has a direct Read share;
- `testuser1`, `testuser2` and `testuser5` are members of the corresponding
  shared groups; and
- the model direct-query results prove the model grants and roles are active.

### Portal and MCP results

| User | Fabric portal | Published MCP endpoint | Security result |
| --- | --- | --- | --- |
| `testuser1` | Allowed; the evaluation questions returned the expected `TenantA` results | Allowed; returned 1,344 events | RLS and OLS enforced |
| `testuser2` | Agent absent from OneLake catalog; direct link denied | Rejected as not authorized during MCP initialization | Query never reached the model |
| `testuser3` | Not manually run | Rejected as not authorized during MCP initialization | Query never reached the model |
| `testuser4` | Not manually run | Rejected as not authorized during MCP initialization | Query never reached the model |
| `testuser5` | Agent absent from OneLake catalog; direct link denied | Rejected as not authorized during MCP initialization | Query never reached the model |
| `testuser6` | Denied by design; no agent share | Rejected as not authorized | Expected denial |
| `testuser7` | Denied by design; no agent share | Rejected as not authorized | Expected denial |

`testuser1` began working after a temporary Analytics workspace Viewer
assignment was added and removed during the earlier investigation. No other
permission remained. This history, together with identical group-share
configuration for the tenant groups, makes stale permission materialization or
cache state a plausible explanation, but not a confirmed root cause.

The observed behavior conflicts with the documented Data Agent sharing model,
which says that Read on the published agent and Read on a semantic-model source
are sufficient and that workspace access is not required. The test therefore
does not recommend adding Viewer as a workaround: it grants Read to every item
in the Analytics workspace and would hide the product gap.

## Copilot Studio

No real-user result is claimed for this path. Microsoft documents these
prerequisites for adding a Fabric Data Agent as a Copilot Studio tool:

- paid F2 or higher capacity;
- a published Fabric Data Agent;
- same-tenant Fabric and Copilot Studio resources;
- access to the agent and its source;
- a Microsoft 365 Copilot licence and an appropriate Copilot Studio user
  licence for each builder or manager; and
- applicable cross-geo AI tenant settings.

The lab tenant has a Power Virtual Agents subscription but no subscribed
Microsoft 365 Copilot SKU, so the documented builder prerequisite cannot be
met without a licence change.

Copilot Studio offers two authentication modes. **User** passes the chatting
user's identity and is the only acceptable mode for this security matrix.
**Maker** uses the maker's access for every consumer and would intentionally
bypass the per-user RLS test objective.

Even after licensing is resolved, the Fabric group-share gap must be fixed
first because the Copilot Studio selector lists only Data Agents visible to
the configuring account.

## Microsoft 365 Copilot

No real-user result is claimed for this path. The Fabric Data Agent was not
published to the Microsoft Copilot Agent Store because that changes its
distribution and was not approved as part of this read-only validation.
Copilot extensibility at tenant level was also not asserted.

Microsoft documents that this path:

- requires paid F2 or higher capacity, compatible user licensing and the same
  account and tenant in Fabric and Microsoft Copilot;
- requires the agent to be published to Agent Store;
- requires recipients to have access to both the agent and its sources; and
- fully respects row-level and column-level security on the underlying data.

The security expectation is therefore the same as the Fabric Data Agent path,
but the lab has no execution evidence for it.

## Gaps and escalation notes

### Fabric CAT: group-shared Data Agent access is inconsistent

Escalate with the following reproducible evidence:

1. A published Data Agent has default Read shares for the `TenantA`,
   `TenantB`, `TenantC` and `AllTenants` security groups.
2. The semantic model has corresponding Read shares and role membership.
3. Direct queries succeed with the expected RLS result for users in all four
   groups.
4. `testuser1` can open and query the agent in the portal and through MCP.
5. `testuser2` cannot discover the agent in OneLake catalog or open its direct
   link, and MCP rejects the same user as not authorized.
6. MCP also rejects the sampled `TenantC`, direct-share and `AllTenants`
   users before any semantic-model query.
7. The only known differentiator is that `testuser1` previously received and
   then lost a temporary workspace Viewer assignment.

Ask Fabric CAT to confirm:

- whether Data Agent item shares to Entra security groups are supported on the
  portal and MCP surfaces;
- whether a workspace role is being incorrectly required or cached;
- how effective item permissions can be refreshed without granting broader
  workspace access; and
- whether the published MCP endpoint has a different authorization contract
  from the portal.

Do not include tenant IDs, workspace IDs, item IDs, user principal names,
tokens or screenshots in a public escalation.

### Product and environment prerequisites

| Gap | Required next action |
| --- | --- |
| Power BI Copilot not evidenced | Explicitly enable Q&A in the model, confirm tenant/standalone Copilot settings, and run the tenant-role users through a supported Copilot surface |
| Free users on F2 cannot consume shared Power BI content | Assign Pro/PPU for the test or repeat on F64+; do not reinterpret the current portal denial as an RLS result |
| Copilot Studio builder licence absent | Obtain the documented Microsoft 365 Copilot and Copilot Studio licensing, then test with **User** authentication |
| Agent not published to Microsoft Copilot Agent Store | Obtain approval to publish, confirm Copilot extensibility, and rerun the same question set per user |
| Data Agent group shares not consistently effective | Resolve with Fabric CAT before treating either downstream Copilot integration as validated |

## Microsoft documentation

- [Copilot for Power BI overview](https://learn.microsoft.com/power-bi/create-reports/copilot-introduction)
- [Fabric Data Agent sharing and permission management](https://learn.microsoft.com/fabric/data-science/data-agent-sharing)
- [Use a Fabric Data Agent as a tool in Copilot Studio](https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-copilot-studio-tool)
- [Consume a Fabric Data Agent in Microsoft Copilot](https://learn.microsoft.com/fabric/data-science/data-agent-microsoft-365-copilot)
- [Fabric and Power BI licences](https://learn.microsoft.com/fabric/enterprise/licenses)
