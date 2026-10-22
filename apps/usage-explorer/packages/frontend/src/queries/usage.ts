import type { ColumnDef } from '@microsoft/fabric-visuals-core';

/** Name of the connector registered in rayfin/rayfin.yml. */
export const USAGE_CONNECTION = 'productanalytics';

export interface UsageQuery {
  query: string;
  /** Columns in the exact order the DAX query returns them. */
  columns: ColumnDef[];
}

export const kpiQuery: UsageQuery = {
  query: `EVALUATE
ROW(
  "Events", [Events],
  "ActiveUsers", [Active users],
  "Tenants", [Tenants],
  "AvgDuration", [Average duration (s)]
)`,
  columns: [
    { name: 'events', displayName: 'Events', format: '#,##0' },
    { name: 'activeUsers', displayName: 'Active users', format: '#,##0' },
    { name: 'tenants', displayName: 'Tenants', format: '#,##0' },
    { name: 'avgDuration', displayName: 'Avg. duration (s)', format: '#,##0.0' },
  ],
};

export const tenantQuery: UsageQuery = {
  query: `EVALUATE
SUMMARIZECOLUMNS(
  dim_tenant[tenant_id],
  "Events", [Events],
  "ActiveUsers", [Active users]
)
ORDER BY [Events] DESC`,
  columns: [
    { name: 'tenant', displayName: 'Tenant' },
    { name: 'events', displayName: 'Events', format: '#,##0' },
    { name: 'activeUsers', displayName: 'Active users', format: '#,##0' },
  ],
};

export const featureQuery: UsageQuery = {
  query: `EVALUATE
SUMMARIZECOLUMNS(
  dim_feature[feature_name],
  dim_feature[feature_category],
  "Events", [Events],
  "ActiveUsers", [Active users],
  "AvgDuration", [Average duration (s)]
)
ORDER BY [Events] DESC`,
  columns: [
    { name: 'feature', displayName: 'Feature' },
    { name: 'category', displayName: 'Category' },
    { name: 'events', displayName: 'Events', format: '#,##0' },
    { name: 'activeUsers', displayName: 'Active users', format: '#,##0' },
    { name: 'avgDuration', displayName: 'Avg. duration (s)', format: '#,##0.0' },
  ],
};

export const monthlyQuery: UsageQuery = {
  query: `EVALUATE
SUMMARIZECOLUMNS(
  dim_date[year],
  dim_date[month],
  "Events", [Events],
  "ActiveUsers", [Active users]
)
ORDER BY dim_date[year], dim_date[month]`,
  columns: [
    { name: 'year', displayName: 'Year' },
    { name: 'month', displayName: 'Month' },
    { name: 'events', displayName: 'Events', format: '#,##0' },
    { name: 'activeUsers', displayName: 'Active users', format: '#,##0' },
  ],
};
