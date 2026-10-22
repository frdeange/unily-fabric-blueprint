import type { DataTable } from '@microsoft/fabric-visuals-core';

import type { UsageQuery } from '@/queries/usage';

interface QueryTableLike {
  columns: readonly { name: string }[];
  rows: unknown[][];
}

/**
 * Binds query rows to the declared presentation columns. The column count is
 * checked so a changed model contract fails visibly instead of mislabelling data.
 */
export function bindTable(
  table: QueryTableLike,
  definition: UsageQuery
): DataTable {
  if (table.columns.length !== definition.columns.length) {
    throw new Error(
      `Unexpected result shape: expected ${definition.columns.length} columns, got ${table.columns.length}.`
    );
  }
  return {
    columns: definition.columns,
    rows: table.rows as DataTable['rows'],
  };
}

export interface Kpis {
  events: number;
  activeUsers: number;
  tenants: number;
  avgDuration: number;
}

export function readKpis(table: DataTable): Kpis | undefined {
  const row = table.rows[0];
  if (!row) return undefined;
  const [events, activeUsers, tenants, avgDuration] = row.map(Number);
  return { events, activeUsers, tenants, avgDuration };
}

/** Returns "month/year" labels in the order the rows arrive. */
export function monthLabel(year: unknown, month: unknown): string {
  return `${String(year)}-${String(month).padStart(2, '0')}`;
}
