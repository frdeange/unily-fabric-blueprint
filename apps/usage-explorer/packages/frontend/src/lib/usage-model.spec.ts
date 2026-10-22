import { describe, it, expect } from 'vitest';

import { bindTable, monthLabel, readKpis } from '@/lib/usage-model';
import { kpiQuery, tenantQuery } from '@/queries/usage';

describe('bindTable', () => {
  it('attaches presentation columns to rows', () => {
    const table = bindTable(
      {
        columns: [{ name: 'a' }, { name: 'b' }, { name: 'c' }],
        rows: [['tenant_x', 10, 2]],
      },
      tenantQuery
    );
    expect(table.columns.map((c) => c.name)).toEqual([
      'tenant',
      'events',
      'activeUsers',
    ]);
    expect(table.rows).toHaveLength(1);
  });

  it('fails visibly when the column count changes', () => {
    expect(() =>
      bindTable({ columns: [{ name: 'a' }], rows: [] }, tenantQuery)
    ).toThrow(/expected 3 columns, got 1/);
  });
});

describe('readKpis', () => {
  it('reads the single KPI row', () => {
    const table = bindTable(
      {
        columns: [{ name: 'a' }, { name: 'b' }, { name: 'c' }, { name: 'd' }],
        rows: [[100, 5, 2, 12.5]],
      },
      kpiQuery
    );
    expect(readKpis(table)).toEqual({
      events: 100,
      activeUsers: 5,
      tenants: 2,
      avgDuration: 12.5,
    });
  });

  it('returns undefined for an empty result', () => {
    expect(
      readKpis({ columns: kpiQuery.columns, rows: [] })
    ).toBeUndefined();
  });
});

describe('monthLabel', () => {
  it('zero-pads the month', () => {
    expect(monthLabel(2026, 9)).toBe('2026-09');
  });
});
