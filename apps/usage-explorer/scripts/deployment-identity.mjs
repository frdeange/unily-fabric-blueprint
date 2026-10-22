import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const guid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const accessRights = new Set([
  'None', 'Read', 'ReadWrite', 'ReadReshare', 'ReadExplore',
  'ReadWriteReshare', 'ReadWriteExplore', 'ReadReshareExplore',
  'ReadWriteReshareExplore',
]);

function requiredGuid(value, name) {
  if (typeof value !== 'string' || !guid.test(value)) {
    throw new Error(`${name} must be a GUID.`);
  }
  return value.toLowerCase();
}

// These claims are diagnostics from an Azure CLI token, not token validation.
export function inspectIdentity(token, expectedClient, expectedTenant) {
  let claims;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) throw new Error();
    claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  } catch {
    throw new Error('Cannot inspect deployment token claims.');
  }
  if (!claims || typeof claims !== 'object') {
    throw new Error('Cannot inspect deployment token claims.');
  }
  const client = requiredGuid(claims.appid ?? claims.azp, 'Token client');
  const tenant = requiredGuid(claims.tid, 'Token tenant');
  const objectId = requiredGuid(claims.oid, 'Token principal');
  if (client !== requiredGuid(expectedClient, 'Configured client') ||
      tenant !== requiredGuid(expectedTenant, 'Configured tenant')) {
    throw new Error('Deployment token does not match the configured client and tenant.');
  }
  if (claims.scp || (claims.idtyp !== undefined && claims.idtyp !== 'app')) {
    throw new Error('Deployment token is not an app-only identity.');
  }
  return { client, tenant, objectId };
}

export function summarizeModelAccess(body, objectId) {
  if (!Array.isArray(body?.value)) {
    throw new Error('Model access response has an unexpected shape.');
  }
  const rights = body.value
    .filter((entry) => entry?.principalType === 'App' &&
      typeof entry.identifier === 'string' &&
      entry.identifier.toLowerCase() === objectId)
    .map((entry) => entry.datasetUserAccessRight);
  if (rights.some((right) => !accessRights.has(right))) {
    throw new Error('Model access response contains an unknown permission value.');
  }
  return {
    directPrincipalEntry: rights.length > 0,
    directAccessRights: [...new Set(rights)],
    directBuildObserved: rights.some((right) => right.includes('Explore')),
  };
}

export async function diagnose(env, acquireToken, request = fetch, log = console.log) {
  const identity = inspectIdentity(env.RAYFIN_TOKEN, env.AZURE_CLIENT_ID, env.AZURE_TENANT_ID);
  const workspace = requiredGuid(env.RAYFIN_WORKSPACE_ID, 'Workspace');
  const model = requiredGuid(env.RAYFIN_SEMANTIC_MODEL_ID, 'Semantic model');
  log('Deployment token client and tenant match configuration; app-only principal claim present.');
  let token;
  try {
    token = acquireToken();
  } catch {
    throw new Error('Cannot acquire a Power BI diagnostic token; no token details logged.');
  }
  const powerBiIdentity = inspectIdentity(token, identity.client, identity.tenant);
  if (powerBiIdentity.objectId !== identity.objectId) {
    throw new Error('Fabric and Power BI token principal claims differ.');
  }
  log('Fabric and Power BI token principal claims match.');
  let response;
  try {
    response = await request(
      `https://api.powerbi.com/v1.0/myorg/groups/${workspace}/datasets/${model}/users`,
      {
        headers: { Authorization: `Bearer ${token}` },
        redirect: 'error',
        signal: AbortSignal.timeout(30_000),
      },
    );
  } catch {
    throw new Error('Model access diagnostic request failed; no response details logged.');
  }
  if (!response.ok) {
    // This endpoint requires Reshare. Its rejection is not proof of missing Build.
    log(`Model access inspection unavailable (HTTP ${response.status}); effective Build access remains unverified.`);
    return;
  }
  let body;
  try {
    body = await response.json();
  } catch {
    throw new Error('Model access response is not JSON; no response body logged.');
  }
  log(JSON.stringify(summarizeModelAccess(body, identity.objectId)));
  log('Direct entries do not resolve inherited group access or the workload Build validation path.');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    await diagnose(process.env, () => execFileSync('az', [
      'account', 'get-access-token', '--resource', 'https://analysis.windows.net/powerbi/api',
      '--query', 'accessToken', '-o', 'tsv',
    ], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 30_000 }).trim());
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
