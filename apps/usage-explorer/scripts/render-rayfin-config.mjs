// Replaces the committed placeholder IDs in rayfin/rayfin.yml with values from the
// environment, so no real workspace or item identifiers live in source control.
// Usage: node scripts/render-rayfin-config.mjs [--check]
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const GUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const PLACEHOLDERS = {
  RAYFIN_WORKSPACE_ID: '00000000-0000-4000-8000-000000000001',
  RAYFIN_SEMANTIC_MODEL_ID: '00000000-0000-4000-8000-000000000002',
};

export function render(source, env) {
  let output = source;
  for (const [name, placeholder] of Object.entries(PLACEHOLDERS)) {
    const value = env[name];
    if (!value || !GUID.test(value)) {
      throw new Error(`${name} must be set to a GUID.`);
    }
    if (!output.includes(placeholder)) {
      throw new Error(`Placeholder for ${name} not found in rayfin.yml.`);
    }
    output = output.replaceAll(placeholder, value);
  }
  return output;
}

const isMain = process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) {
  const file = resolve(dirname(fileURLToPath(import.meta.url)), '../rayfin/rayfin.yml');
  const source = readFileSync(file, 'utf8');
  if (process.argv.includes('--check')) {
    for (const placeholder of Object.values(PLACEHOLDERS)) {
      if (!source.includes(placeholder)) {
        throw new Error(`Committed rayfin.yml must keep placeholder ${placeholder}.`);
      }
    }
    console.log('rayfin.yml placeholders OK');
  } else {
    writeFileSync(file, render(source, process.env));
    console.log('rayfin.yml rendered from environment');
  }
}
