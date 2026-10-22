import assert from 'node:assert/strict';
import test from 'node:test';
import { diagnose, inspectIdentity, summarizeModelAccess } from './deployment-identity.mjs';

const client = '00000000-0000-4000-8000-000000000001';
const tenant = '00000000-0000-4000-8000-000000000002';
const objectId = '00000000-0000-4000-8000-000000000003';
const token = (claims = {}) => `header.${Buffer.from(JSON.stringify({
  appid: client, tid: tenant, oid: objectId, idtyp: 'app', ...claims,
})).toString('base64url')}.signature`;
const env = {
  RAYFIN_TOKEN: token(), AZURE_CLIENT_ID: client, AZURE_TENANT_ID: tenant,
  RAYFIN_WORKSPACE_ID: client, RAYFIN_SEMANTIC_MODEL_ID: tenant,
};

test('accepts matching v1/v2 app claims and rejects wrong or delegated identities', () => {
  assert.equal(inspectIdentity(token(), client, tenant).objectId, objectId);
  assert.equal(inspectIdentity(token({ appid: undefined, azp: client }), client, tenant).client, client);
  for (const claims of [{ appid: objectId }, { tid: objectId }, { scp: 'Dataset.Read.All' }, { idtyp: 'user' }]) {
    assert.throws(() => inspectIdentity(token(claims), client, tenant));
  }
  for (const bad of ['not-a-token', 'a.bnVsbA.b', 'a.e30.b']) {
    assert.throws(() => inspectIdentity(bad, client, tenant));
  }
});

test('uses exact app object identity and reports only allowlisted rights', () => {
  assert.deepEqual(summarizeModelAccess({ value: [
    { principalType: 'App', identifier: objectId, datasetUserAccessRight: 'ReadWriteExplore' },
    { principalType: 'User', identifier: objectId, datasetUserAccessRight: 'ReadWriteReshareExplore' },
    { principalType: 'App', identifier: client, datasetUserAccessRight: 'Read' },
  ] }, objectId), {
    directPrincipalEntry: true, directAccessRights: ['ReadWriteExplore'], directBuildObserved: true,
  });
  assert.equal(summarizeModelAccess({ value: [] }, objectId).directPrincipalEntry, false);
  assert.throws(() => summarizeModelAccess({}, objectId));
  assert.throws(() => summarizeModelAccess({ value: [
    { principalType: 'App', identifier: objectId, datasetUserAccessRight: 'sensitive-data' },
  ] }, objectId));
});

test('403 is explicitly inconclusive, not a missing-Build verdict; logs omit credentials and identifiers', async () => {
  const logs = [];
  await diagnose(env, () => token(), async (url, options) => {
    assert.equal(options.redirect, 'error');
    assert.equal(options.headers.Authorization, `Bearer ${token()}`);
    return { ok: false, status: 403 };
  }, (line) => logs.push(line));
  assert.match(logs.join('\n'), /unavailable \(HTTP 403\).*unverified/);
  for (const secret of [client, tenant, objectId, token()]) {
    assert.ok(!logs.join('\n').includes(secret));
  }
});

test('fails before requesting access when cross-audience principal changes', async () => {
  let called = false;
  await assert.rejects(diagnose(env, () => token({ oid: client }), async () => {
    called = true;
  }, () => {}), /principal claims differ/);
  assert.equal(called, false);
});

test('sanitizes token acquisition and network errors', async () => {
  await assert.rejects(diagnose(env, () => { throw new Error(token()); }, fetch, () => {}),
    /Cannot acquire a Power BI diagnostic token; no token details logged\./);
  await assert.rejects(diagnose(env, () => token(), async () => { throw new Error(token()); }, () => {}),
    /diagnostic request failed; no response details logged\./);
});

test('successful inspection logs only matching permissions, not response identities', async () => {
  const logs = [];
  await diagnose(env, () => token(), async () => ({
    ok: true,
    json: async () => ({ value: [
      { principalType: 'App', identifier: objectId, datasetUserAccessRight: 'ReadWriteExplore' },
      { principalType: 'User', identifier: 'private@example.invalid', datasetUserAccessRight: 'Read' },
    ] }),
  }), (line) => logs.push(line));
  assert.match(logs.join('\n'), /"directBuildObserved":true/);
  for (const sensitive of [objectId, client, tenant, token(), 'private@example.invalid']) {
    assert.ok(!logs.join('\n').includes(sensitive));
  }
});

test('successful HTTP with invalid JSON or shape is a failure, never permission success', async () => {
  await assert.rejects(diagnose(env, () => token(), async () => ({
    ok: true, json: async () => { throw new Error('sensitive-body'); },
  }), () => {}), /not JSON; no response body logged/);
  await assert.rejects(diagnose(env, () => token(), async () => ({
    ok: true, json: async () => ({}),
  }), () => {}), /unexpected shape/);
});
