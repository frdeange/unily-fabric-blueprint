import {
  AlertCircle,
  ArrowDownRight,
  ArrowUpRight,
  Minus,
  RefreshCw,
} from 'lucide-react';
import type { ReactNode } from 'react';

import { percentChange } from '@/lib/adoption';

export function Notice({
  title,
  children,
  retry,
}: {
  title: string;
  children?: ReactNode;
  retry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex items-start gap-300 rounded-xl border border-destructive bg-card p-400"
    >
      <AlertCircle
        className="icon-size-300 shrink-0 text-destructive"
        aria-hidden="true"
      />
      <div className="flex-1">
        <p className="font-semibold">{title}</p>
        <div className="mt-100 text-300 text-muted-foreground">{children}</div>
      </div>
      {retry && (
        <button className="wb-secondary" onClick={retry}>
          <RefreshCw className="icon-size-200" /> Retry
        </button>
      )}
    </div>
  );
}

export function Empty({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-dashed bg-card p-800 text-center">
      <h3 className="text-500 font-semibold">{title}</h3>
      <div className="mx-auto mt-200 max-w-xl text-300 text-muted-foreground">
        {children}
      </div>
    </div>
  );
}

export function Change({
  value,
  previous,
}: {
  value: number;
  previous?: number | null;
}) {
  const change = percentChange(value, previous);
  if (change === null)
    return (
      <span className="text-200 text-muted-foreground">
        No comparable baseline
      </span>
    );
  const Icon =
    change === 0 ? Minus : change > 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex items-center gap-100 text-200 text-muted-foreground">
      <Icon className="icon-size-200" aria-hidden="true" />
      {change > 0 ? '+' : ''}
      {change.toFixed(1)}% vs prior month
    </span>
  );
}

export function Metric({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: ReactNode;
}) {
  return (
    <div className="rounded-2xl border bg-card p-500">
      <dt className="text-300 text-muted-foreground">{label}</dt>
      <dd className="mt-200 font-numeric text-hero-800 font-semibold tracking-tight">
        {value}
      </dd>
      <div className="mt-200">{detail}</div>
    </div>
  );
}
