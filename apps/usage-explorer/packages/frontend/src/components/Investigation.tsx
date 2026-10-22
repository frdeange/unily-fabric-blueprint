import { ArrowRight, BookmarkPlus, Search } from 'lucide-react';
import { VegaVisual, useCssTheme } from '@microsoft/fabric-visuals';
import type { VisualizationSpec } from '@microsoft/fabric-visuals';
import type { DataTable } from '@microsoft/fabric-visuals-core';

import type { AdoptionRow } from '@/lib/adoption';
import { numberLabel, periodLabel, previousPeriod } from '@/lib/adoption';
import { Change, Empty, Metric } from './workbench-parts';

interface Props {
  totals: AdoptionRow[];
  features: AdoptionRow[];
  tenant: string;
  period: string;
  feature: string;
  setTenant: (value: string) => void;
  setPeriod: (value: string) => void;
  setFeature: (value: string) => void;
  save: (row: AdoptionRow, previous: AdoptionRow | undefined) => void;
  canSave: boolean;
}

const trendSpec: VisualizationSpec = {
  $schema: 'https://vega.github.io/schema/vega-lite/v6.json',
  width: 'container',
  height: 'container',
  mark: { type: 'line' },
  encoding: {
    color: { value: 'currentColor' },
    x: { field: 'month', type: 'ordinal', sort: null, title: null },
    y: {
      field: 'events',
      type: 'quantitative',
      title: 'Recorded events',
      scale: { zero: true },
    },
    tooltip: [
      { field: 'month', type: 'ordinal', title: 'Month' },
      { field: 'events', type: 'quantitative', title: 'Events' },
    ],
  },
};

export function Investigation({
  totals,
  features,
  tenant,
  period,
  feature,
  setTenant,
  setPeriod,
  setFeature,
  save,
  canSave,
}: Props) {
  const theme = useCssTheme();
  const tenants = [...new Set(totals.map((row) => row.tenant))].sort();
  const periods = [
    ...new Set(
      totals.filter((row) => row.tenant === tenant).map((row) => row.period),
    ),
  ]
    .sort()
    .reverse();
  const current = totals.find(
    (row) => row.tenant === tenant && row.period === period,
  );
  const prior = totals.find(
    (row) => row.tenant === tenant && row.period === previousPeriod(period),
  );
  const featureRows = features
    .filter((row) => row.tenant === tenant && row.period === period)
    .sort((a, b) => b.events - a.events);
  const selected = feature
    ? featureRows.find((row) => row.feature === feature)
    : current;
  const previous = feature
    ? features.find(
        (row) =>
          row.tenant === tenant &&
          row.period === previousPeriod(period) &&
          row.feature === feature,
      )
    : prior;
  const trend = totals
    .filter((row) => row.tenant === tenant)
    .sort((a, b) => a.period.localeCompare(b.period));
  const trendData: DataTable = {
    columns: [
      { name: 'month', displayName: 'Month' },
      { name: 'events', displayName: 'Events', format: '#,##0' },
    ],
    rows: trend.map((row) => [periodLabel(row.period), row.events]),
  };

  return (
    <div className="space-y-600">
      <section className="flex flex-wrap items-end justify-between gap-400 rounded-2xl border bg-card p-500">
        <div>
          <p className="wb-eyebrow">01 / Investigate</p>
          <h2 className="mt-100 text-600 font-semibold">
            Find the story behind the usage
          </h2>
          <p className="mt-100 text-300 text-muted-foreground">
            Select a tenant and a month. Open a feature to build a focused
            evidence trail.
          </p>
        </div>
        <div className="flex flex-wrap gap-300">
          <label className="wb-field">
            Tenant
            <select
              value={tenant}
              onChange={(event) => {
                setTenant(event.target.value);
                setFeature('');
              }}
              className="wb-input"
            >
              {tenants.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label className="wb-field">
            Period
            <select
              value={period}
              onChange={(event) => {
                setPeriod(event.target.value);
                setFeature('');
              }}
              className="wb-input"
            >
              {periods.map((value) => (
                <option value={value} key={value}>
                  {periodLabel(value)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {!current ? (
        <Empty title="No observations in this context">
          Choose a tenant and period with available source data.
        </Empty>
      ) : (
        <>
          <dl className="grid gap-400 sm:grid-cols-2 xl:grid-cols-4">
            <Metric
              label="Recorded events"
              value={numberLabel(current.events)}
              detail={
                <Change value={current.events} previous={prior?.events} />
              }
            />
            <Metric
              label="Active users"
              value={numberLabel(current.activeUsers)}
              detail={
                <Change
                  value={current.activeUsers}
                  previous={prior?.activeUsers}
                />
              }
            />
            <Metric
              label="Events per active user"
              value={
                current.activeUsers
                  ? (current.events / current.activeUsers).toFixed(1)
                  : 'Not available'
              }
              detail={
                <span className="text-200 text-muted-foreground">
                  Events / distinct active users
                </span>
              }
            />
            <Metric
              label="Average event duration"
              value={
                current.avgDuration == null
                  ? 'Not available'
                  : `${current.avgDuration.toFixed(1)} s`
              }
              detail={
                <span className="text-200 text-muted-foreground">
                  Duration, not a satisfaction score
                </span>
              }
            />
          </dl>

          <div className="grid items-start gap-500 xl:grid-cols-3">
            <div className="space-y-500 xl:col-span-2">
              <section className="wb-panel">
                <div className="flex flex-wrap items-center justify-between gap-300">
                  <div>
                    <p className="wb-eyebrow">Feature investigation</p>
                    <h3 className="mt-100 text-500 font-semibold">
                      Where are people spending their attention?
                    </h3>
                  </div>
                  <button
                    className="wb-secondary"
                    onClick={() => setFeature('')}
                    disabled={!feature}
                  >
                    Whole tenant
                  </button>
                </div>
                <div className="mt-500 overflow-x-auto">
                  <table className="w-full text-left text-300">
                    <caption className="sr-only">
                      Feature activity for {tenant}, {periodLabel(period)}.
                      Select a feature to inspect its evidence.
                    </caption>
                    <thead className="text-200 text-muted-foreground">
                      <tr>
                        <th className="pb-300">Feature</th>
                        <th className="pb-300 text-right">Events</th>
                        <th className="pb-300 text-right">Active users</th>
                        <th className="pb-300 text-right">Event share</th>
                        <th>
                          <span className="sr-only">Investigate</span>
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {featureRows.map((row) => (
                        <tr
                          key={row.feature}
                          className={
                            feature === row.feature ? 'bg-accent' : 'border-t'
                          }
                        >
                          <td className="py-400 pr-300">
                            <button
                              className="text-left font-semibold text-primary hover:underline"
                              aria-pressed={feature === row.feature}
                              onClick={() => setFeature(row.feature!)}
                            >
                              {row.feature}
                            </button>
                            <p className="mt-100 text-200 text-muted-foreground">
                              {row.category}
                            </p>
                          </td>
                          <td className="py-400 text-right font-numeric">
                            {numberLabel(row.events)}
                          </td>
                          <td className="py-400 text-right font-numeric">
                            {numberLabel(row.activeUsers)}
                          </td>
                          <td className="py-400 pl-300 text-right font-numeric">
                            {current.events
                              ? `${((row.events / current.events) * 100).toFixed(1)}%`
                              : 'N/A'}
                          </td>
                          <td className="pl-300">
                            <ArrowRight
                              className="icon-size-200 text-muted-foreground"
                              aria-hidden="true"
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {featureRows.length === 0 && (
                    <p className="py-500 text-300 text-muted-foreground">
                      No feature observations returned for this context.
                    </p>
                  )}
                </div>
                <p className="mt-300 text-200 text-muted-foreground">
                  Users can use multiple features. Feature-level user counts
                  must not be added together.
                </p>
              </section>

              <section className="wb-panel">
                <p className="wb-eyebrow">Monthly context</p>
                <h3 className="mt-100 text-500 font-semibold">
                  Activity over the available months
                </h3>
                <div className="mt-400" aria-label="Monthly event trend">
                  <VegaVisual
                    spec={trendSpec}
                    data={trendData}
                    theme={theme}
                    className="text-primary"
                    style={{ height: 'var(--wb-trend-height)' }}
                  />
                </div>
                <div
                  className="mt-300 flex flex-wrap gap-200"
                  aria-label="Trend values and period shortcuts"
                >
                  {trend.map((row) => (
                    <button
                      key={row.period}
                      className="wb-secondary"
                      aria-pressed={period === row.period}
                      onClick={() => {
                        setPeriod(row.period);
                        setFeature('');
                      }}
                    >
                      {periodLabel(row.period)}: {numberLabel(row.events)}{' '}
                      events
                    </button>
                  ))}
                </div>
                <p className="mt-500 text-200 text-muted-foreground">
                  Recorded events, not normalized by month length. A missing
                  previous calendar month is not treated as zero.
                </p>
              </section>
            </div>

            <aside
              className="space-y-400 xl:sticky xl:top-600"
              aria-label="Evidence inspector"
            >
              <section className="wb-panel border-primary">
                <div className="flex items-center gap-200 text-primary">
                  <Search className="icon-size-200" aria-hidden="true" />
                  <p className="wb-eyebrow">Evidence inspector</p>
                </div>
                <h3 className="mt-400 text-600 font-semibold">
                  {feature || 'Whole-tenant view'}
                </h3>
                <p className="mt-100 text-300 text-muted-foreground">
                  {tenant} / {periodLabel(period)}
                </p>
                {selected ? (
                  <>
                    <dl className="mt-500 space-y-400">
                      <div className="flex justify-between gap-300">
                        <dt className="text-muted-foreground">Events</dt>
                        <dd className="font-numeric font-semibold">
                          {numberLabel(selected.events)}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-300">
                        <dt className="text-muted-foreground">Active users</dt>
                        <dd className="font-numeric font-semibold">
                          {numberLabel(selected.activeUsers)}
                        </dd>
                      </div>
                      <div className="flex justify-between gap-300">
                        <dt className="text-muted-foreground">Avg. duration</dt>
                        <dd className="font-numeric font-semibold">
                          {selected.avgDuration == null
                            ? 'N/A'
                            : `${selected.avgDuration.toFixed(1)} s`}
                        </dd>
                      </div>
                    </dl>
                    <div className="mt-400 border-t pt-400">
                      <Change
                        value={selected.events}
                        previous={previous?.events}
                      />
                    </div>
                    <button
                      className="wb-primary mt-500 w-full"
                      onClick={() => save(selected, previous)}
                      disabled={!canSave}
                    >
                      <BookmarkPlus
                        className="icon-size-200"
                        aria-hidden="true"
                      />{' '}
                      Capture a diagnosis
                    </button>
                    {!canSave && (
                      <p className="mt-200 text-200 text-muted-foreground">
                        Saving needs the workbench data service. Check the
                        saved-records connection above.
                      </p>
                    )}
                  </>
                ) : (
                  <p className="mt-400 text-300">
                    This feature has no observation in the selected context.
                    Select another feature.
                  </p>
                )}
              </section>
              <section className="rounded-2xl border p-500">
                <p className="wb-eyebrow">Evidence, not inference</p>
                <p className="mt-300 text-300 text-muted-foreground">
                  These are observations from a synthetic lab. There is no churn
                  prediction, target benchmark, or confirmed Unily workflow.
                  Your interpretation is saved separately from the figures.
                </p>
              </section>
            </aside>
          </div>
        </>
      )}
    </div>
  );
}
