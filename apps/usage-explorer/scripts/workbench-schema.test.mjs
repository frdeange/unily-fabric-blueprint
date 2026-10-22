import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  ConfigGenerator,
  SchemaAnalyzer,
} from '@microsoft/rayfin-core/analysis';
import { schema } from '../packages/data/dist/index.js';

const config = new ConfigGenerator('mssql').generateConfig(
  new SchemaAnalyzer(schema, 'mssql', { log() {} }).analyzeEntities(),
);

test('only explicitly private workbench entities are registered', () => {
  assert.deepEqual(Object.keys(config.entities).sort(), [
    'Diagnosis',
    'FollowUp',
  ]);
  for (const entity of Object.values(config.entities)) {
    assert.deepEqual(
      entity.permissions.map((permission) => permission.role),
      ['authenticated'],
    );
    const actions = entity.permissions[0].actions;
    assert.deepEqual(actions.map((action) => action.action).sort(), [
      'create',
      'read',
      'update',
    ]);
    for (const action of actions) {
      assert.equal(action.policy.database, '@claims.sub eq @item.owner_id');
    }
  }
});

test('updates cannot transfer ownership, replace evidence or relink actions', () => {
  const updateFields = (name) =>
    config.entities[name].permissions[0].actions.find(
      (action) => action.action === 'update',
    ).fields.include;
  assert.deepEqual(updateFields('Diagnosis'), ['notes', 'title']);
  assert.deepEqual(updateFields('FollowUp'), [
    'dueDate',
    'notes',
    'priority',
    'status',
    'title',
    'updatedAt',
  ]);
});

test('MSSQL string columns are bounded, including generated enums', () => {
  for (const entity of Object.values(config.entities)) {
    for (const field of Object.values(entity['x-schema'].fields)) {
      assert.doesNotMatch(field.dbType, /MAX/i);
    }
  }
  assert.equal(
    config.entities.FollowUp['x-schema'].fields.status.dbType,
    'NVARCHAR(11)',
  );
  assert.equal(
    config.entities.FollowUp['x-schema'].fields.priority.dbType,
    'NVARCHAR(6)',
  );
});
