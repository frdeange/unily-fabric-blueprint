import { describe, expect, it } from 'vitest';

import {
  dueLabel,
  isOverdue,
  parseAdoption,
  percentChange,
  periodLabel,
  previousPeriod,
} from './adoption';

const table = {
  columns: [
    'dim_tenant[tenant_id]',
    'dim_date[year]',
    'dim_date[month]',
    '[Events]',
    '[ActiveUsers]',
    '[AvgDuration]',
  ].map((name) => ({ name })),
  rows: [['tenant_example', 2026, 9, 120, 5, 30]],
};

describe('verified source contract', () => {
  it('reads values by column name, even when the source reorders columns', () => {
    expect(
      parseAdoption({
        columns: [...table.columns].reverse(),
        rows: [[...table.rows[0]].reverse()],
      }),
    ).toEqual([
      {
        tenant: 'tenant_example',
        period: '2026-09',
        events: 120,
        activeUsers: 5,
        avgDuration: 30,
      },
    ]);
  });

  it('rejects missing columns rather than mislabelling observations', () => {
    expect(() =>
      parseAdoption({ ...table, columns: table.columns.slice(1) }),
    ).toThrow(/missing/);
  });

  it.each([NaN, Infinity, -1, '120', 1.5])(
    'rejects an invalid event count (%s)',
    (value) => {
      expect(() =>
        parseAdoption({
          ...table,
          rows: [['tenant_example', 2026, 9, value, 5, 30]],
        }),
      ).toThrow();
    },
  );

  it('does not disguise a missing duration as zero', () => {
    expect(
      parseAdoption({
        ...table,
        rows: [['tenant_example', 2026, 9, 0, 0, null]],
      })[0].avgDuration,
    ).toBeNull();
  });

  it('rejects truncated or unexpectedly large source results', () => {
    expect(() =>
      parseAdoption({
        ...table,
        rows: Array.from({ length: 1001 }, () => table.rows[0]),
      }),
    ).toThrow(/exceeds/);
  });
});

describe('comparisons and dates', () => {
  it('uses the previous calendar month, including across a year boundary', () => {
    expect(previousPeriod('2026-01')).toBe('2025-12');
    expect(previousPeriod('2026-09')).toBe('2026-08');
  });
  it('does not invent a change when there is no comparable denominator', () => {
    expect(percentChange(120)).toBeNull();
    expect(percentChange(120, 0)).toBeNull();
    expect(percentChange(120, 100)).toBe(20);
    expect(percentChange(0, 100)).toBe(-100);
  });
  it('formats date-only fields without a local-timezone shift', () => {
    expect(periodLabel('2026-09')).toBe('Sep 2026');
    expect(dueLabel('2026-09-01')).toBe('Sep 1, 2026');
    expect(dueLabel('')).toBe('No due date');
    expect(dueLabel('not-a-date')).toBe('Invalid due date');
  });
  it('does not mark completed or undated actions overdue', () => {
    expect(isOverdue('2026-09-01', 'Planned', '2026-09-02')).toBe(true);
    expect(isOverdue('2026-09-02', 'Planned', '2026-09-02')).toBe(false);
    expect(isOverdue('2026-09-01', 'Done', '2026-09-02')).toBe(false);
    expect(isOverdue('', 'Planned', '2026-09-02')).toBe(false);
  });
});
