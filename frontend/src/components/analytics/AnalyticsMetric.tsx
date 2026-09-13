"use client";

/**
 * Executive Analytics metric primitives (Phase 28, C1 read-only).
 *
 * Formatting rules: a value is rendered only from backend-reported numbers.
 * null/undefined/NaN render as an em-dash — never as 0 unless the backend
 * explicitly returned 0. Cents are backend ints; USD floats stay floats.
 */

export function formatInt(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return Math.round(value).toLocaleString("en-US");
}

export function formatDecimal(value: number | null | undefined, digits = 2): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return value.toLocaleString("en-US", { maximumFractionDigits: digits });
}

export function formatUsd(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `$${value.toLocaleString("en-US", { maximumFractionDigits: 2 })}`;
}

/** FinOps amounts are integer cents — divide by 100 for USD display. */
export function formatCentsUsd(cents: number | null | undefined): string | null {
  if (typeof cents !== "number" || !Number.isFinite(cents)) return null;
  return formatUsd(cents / 100);
}

/** Ratio in [0, 1] as reported by the backend (e.g. change_failure_rate). */
export function formatRatioPercent(value: number | null | undefined): string | null {
  if (typeof value !== "number" || !Number.isFinite(value)) return null;
  return `${(value * 100).toLocaleString("en-US", { maximumFractionDigits: 2 })}%`;
}

export function AnalyticsMetric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | null;
  hint?: string;
}) {
  return (
    <div className="border border-outline bg-surface p-3">
      <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{label}</p>
      <p className="mt-1 font-mono text-xl text-on-surface">{value ?? "—"}</p>
      {hint ? <p className="mt-1 text-[11px] text-on-surface-variant">{hint}</p> : null}
    </div>
  );
}
