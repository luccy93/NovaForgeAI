"use client";

/**
 * Executive Analytics trend chart (Phase 28, C1 read-only).
 *
 * Pure-CSS bars over backend-provided buckets only — no chart library, no
 * interpolation, no smoothing, no fabricated baselines. Buckets render
 * exactly as returned (capped at the most recent 30 for layout).
 */

export interface TrendDatum {
  key: string;
  label: string;
  value: number;
  title?: string;
}

export function AnalyticsTrend({
  data,
  ariaLabel,
  emptyMessage = "No buckets reported.",
}: {
  data: Array<TrendDatum>;
  ariaLabel: string;
  emptyMessage?: string;
}) {
  const ordered = [...data].slice(-30);
  if (ordered.length === 0) {
    return (
      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{emptyMessage}</p>
    );
  }
  const max = Math.max(...ordered.map((d) => d.value), 1);
  const first = ordered[0].label;
  const last = ordered[ordered.length - 1].label;
  return (
    <div>
      <div className="flex h-28 items-end gap-1" role="img" aria-label={`${ariaLabel} (${first} to ${last})`}>
        {ordered.map((d) => (
          <div
            key={d.key}
            className="min-w-0 flex-1 border border-outline bg-primary-container"
            style={{ height: `${Math.max(Math.round((d.value / max) * 100), 3)}%` }}
            title={d.title ?? `${d.label}: ${d.value}`}
          />
        ))}
      </div>
      <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        {first} → {last} · max {Math.max(...ordered.map((d) => d.value)).toLocaleString("en-US")}
      </p>
      <ul className="sr-only">
        {ordered.map((d) => (
          <li key={d.key}>{d.title ?? `${d.label}: ${d.value}`}</li>
        ))}
      </ul>
    </div>
  );
}
