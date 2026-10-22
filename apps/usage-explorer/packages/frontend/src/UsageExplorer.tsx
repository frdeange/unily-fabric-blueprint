import { DataGrid } from '@microsoft/fabric-datagrid';
import { VegaVisual, useCssTheme } from '@microsoft/fabric-visuals';
import type { VisualizationSpec } from '@microsoft/fabric-visuals';
import type { DataTable } from '@microsoft/fabric-visuals-core';
import { useMemo } from 'react';

import { useSemanticModelQuery } from '@/hooks/use-semantic-model-query';
import { bindTable, monthLabel, readKpis } from '@/lib/usage-model';
import type { UsageQuery } from '@/queries/usage';
import {
  USAGE_CONNECTION,
  featureQuery,
  kpiQuery,
  monthlyQuery,
  tenantQuery,
} from '@/queries/usage';

type Loaded =
  | { state: 'loading' }
  | { state: 'error'; message: string }
  | { state: 'ready'; table: DataTable };

function useUsageTable(definition: UsageQuery): Loaded {
  const { data, isLoading, error } = useSemanticModelQuery({
    connection: USAGE_CONNECTION,
    query: definition.query,
  });

  return useMemo<Loaded>(() => {
    if (error) return { state: 'error', message: error.message };
    if (isLoading || !data) return { state: 'loading' };
    if (data.status === 'error') {
      return { state: 'error', message: data.error.message };
    }
    try {
      return { state: 'ready', table: bindTable(data.table, definition) };
    } catch (e) {
      return { state: 'error', message: (e as Error).message };
    }
  }, [data, isLoading, error, definition]);
}

function Panel({
  title,
  loaded,
  children,
}: {
  title: string;
  loaded: Loaded;
  children: (table: DataTable) => React.ReactNode;
}) {
  return (
    <section className="rounded-lg border p-4">
      <h2 className="mb-3 text-sm font-semibold">{title}</h2>
      {loaded.state === 'loading' && (
        <p role="status" className="text-sm opacity-70">
          Loading live data from the semantic model...
        </p>
      )}
      {loaded.state === 'error' && (
        <p role="alert" className="text-sm text-red-600">
          Query failed: {loaded.message}
        </p>
      )}
      {loaded.state === 'ready' && children(loaded.table)}
    </section>
  );
}

const barSpec = (field: string): VisualizationSpec => ({
  $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
  mark: 'bar',
  encoding: {
    x: { field: 'tenant', type: 'nominal', sort: '-y' },
    y: { field, type: 'quantitative' },
  },
});

const trendSpec: VisualizationSpec = {
  $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
  mark: { type: 'line', point: true },
  encoding: {
    x: { field: 'month', type: 'ordinal' },
    y: { field: 'events', type: 'quantitative' },
  },
};

export function UsageExplorer() {
  const theme = useCssTheme();
  const kpis = useUsageTable(kpiQuery);
  const tenants = useUsageTable(tenantQuery);
  const features = useUsageTable(featureQuery);
  const monthly = useUsageTable(monthlyQuery);

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Tenant Product Usage Explorer</h1>
        <p className="text-sm opacity-70">
          Live view of the synthetic ProductAnalytics lab model. Data is
          synthetic and does not represent any real customer.
        </p>
      </header>

      <Panel title="Key figures" loaded={kpis}>
        {(table) => {
          const k = readKpis(table);
          if (!k) return <p className="text-sm">No data returned.</p>;
          const items: [string, string][] = [
            ['Events', k.events.toLocaleString()],
            ['Active users', k.activeUsers.toLocaleString()],
            ['Tenants', k.tenants.toLocaleString()],
            ['Avg. duration (s)', k.avgDuration.toFixed(1)],
          ];
          return (
            <dl className="grid grid-cols-2 gap-4 md:grid-cols-4">
              {items.map(([label, value]) => (
                <div key={label}>
                  <dt className="text-xs uppercase opacity-70">{label}</dt>
                  <dd className="text-2xl font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          );
        }}
      </Panel>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Events by tenant" loaded={tenants}>
          {(table) => (
            <VegaVisual
              spec={barSpec('events')}
              data={table}
              theme={theme}
              style={{ height: 260 }}
            />
          )}
        </Panel>
        <Panel title="Active users by tenant" loaded={tenants}>
          {(table) => (
            <VegaVisual
              spec={barSpec('activeUsers')}
              data={table}
              theme={theme}
              style={{ height: 260 }}
            />
          )}
        </Panel>
      </div>

      <Panel title="Events per month" loaded={monthly}>
        {(table) => {
          const rows = table.rows.map((r) => [
            monthLabel(r[0], r[1]),
            r[2],
            r[3],
          ]) as DataTable['rows'];
          const trend: DataTable = {
            columns: [
              { name: 'month', displayName: 'Month' },
              { name: 'events', displayName: 'Events', format: '#,##0' },
              {
                name: 'activeUsers',
                displayName: 'Active users',
                format: '#,##0',
              },
            ],
            rows,
          };
          return (
            <VegaVisual
              spec={trendSpec}
              data={trend}
              theme={theme}
              style={{ height: 260 }}
            />
          );
        }}
      </Panel>

      <Panel title="Feature usage" loaded={features}>
        {(table) => (
          <div style={{ height: 260 }}>
            <DataGrid data={table} theme={theme} />
          </div>
        )}
      </Panel>
    </main>
  );
}
