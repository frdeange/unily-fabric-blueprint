export interface AdoptionRow {
  tenant: string;
  period: string;
  events: number;
  activeUsers: number;
  avgDuration: number | null;
  feature?: string;
  category?: string;
}

interface QueryTable {
  columns: readonly { name: string }[];
  rows: readonly (readonly unknown[])[];
}

function numberValue(value: unknown, label: string, integer = false): number {
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value < 0 ||
    (integer && !Number.isSafeInteger(value))
  ) {
    throw new Error(`Unexpected ${label} in the semantic-model response.`);
  }
  return value;
}

function textValue(value: unknown, label: string): string {
  if (typeof value !== 'string' || !value.trim() || value.length > 200) {
    throw new Error(`Unexpected ${label} in the semantic-model response.`);
  }
  return value;
}

export function parseAdoption(
  table: QueryTable,
  features = false,
): AdoptionRow[] {
  if (table.rows.length > (features ? 5000 : 1000)) {
    throw new Error(
      "The result exceeds this demo's supported size. Narrow the source before using it.",
    );
  }
  const indexes = new Map(
    table.columns.map((column, index) => [column.name, index]),
  );
  const required = [
    'dim_tenant[tenant_id]',
    'dim_date[year]',
    'dim_date[month]',
    '[Events]',
    '[ActiveUsers]',
    '[AvgDuration]',
    ...(features
      ? ['dim_feature[feature_name]', 'dim_feature[feature_category]']
      : []),
  ];
  for (const name of required) {
    if (!indexes.has(name))
      throw new Error(`The model response is missing ${name}.`);
  }
  return table.rows.map((row) => {
    const get = (name: string): unknown => row[indexes.get(name)!];
    const year = numberValue(get('dim_date[year]'), 'year', true);
    const month = numberValue(get('dim_date[month]'), 'month', true);
    if (year < 1900 || year > 9999 || month < 1 || month > 12) {
      throw new Error(
        'Invalid calendar period in the semantic-model response.',
      );
    }
    const duration = get('[AvgDuration]');
    return {
      tenant: textValue(get('dim_tenant[tenant_id]'), 'tenant'),
      period: `${year}-${String(month).padStart(2, '0')}`,
      events: numberValue(get('[Events]') ?? 0, 'event count', true),
      activeUsers: numberValue(
        get('[ActiveUsers]') ?? 0,
        'active user count',
        true,
      ),
      avgDuration:
        duration == null ? null : numberValue(duration, 'average duration'),
      ...(features
        ? {
            feature: textValue(get('dim_feature[feature_name]'), 'feature'),
            category: textValue(
              get('dim_feature[feature_category]'),
              'feature category',
            ),
          }
        : {}),
    };
  });
}

export function previousPeriod(period: string): string {
  const [year, month] = period.split('-').map(Number);
  return month === 1
    ? `${year - 1}-12`
    : `${year}-${String(month - 1).padStart(2, '0')}`;
}

export function percentChange(
  current: number,
  previous?: number | null,
): number | null {
  return previous == null || previous === 0
    ? null
    : ((current - previous) / previous) * 100;
}

export function periodLabel(period: string): string {
  return new Intl.DateTimeFormat('en', {
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(`${period}-01T00:00:00Z`));
}

export function dueLabel(date: string): string {
  if (!date) return 'No due date';
  const parsed = new Date(`${date}T00:00:00Z`);
  return Number.isNaN(parsed.getTime())
    ? 'Invalid due date'
    : new Intl.DateTimeFormat('en', {
        dateStyle: 'medium',
        timeZone: 'UTC',
      }).format(parsed);
}

export function isOverdue(
  dueDate: string,
  status: string,
  today = new Date().toISOString().slice(0, 10),
): boolean {
  return status !== 'Done' && Boolean(dueDate) && dueDate < today;
}

export const numberLabel = (value: number) => value.toLocaleString('en');
