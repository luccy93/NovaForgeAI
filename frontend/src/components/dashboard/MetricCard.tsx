"use client";

import { AnimatedCounter } from "@/components/ui/AnimatedCounter";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";

export function MetricCard({
  eyebrow,
  title,
  value,
  loading,
  error,
  hint,
}: {
  eyebrow: string;
  title: string;
  value: number | string | null;
  loading: boolean;
  error?: string | null;
  hint?: string;
}) {
  if (loading) return <BrutalCard eyebrow={eyebrow} title={title}><BrutalSkeleton className="h-12" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow={eyebrow} title={title}>
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (value === null || value === undefined) {
    return (
      <BrutalCard eyebrow={eyebrow} title={title}>
        <p className="text-sm text-on-surface-variant">No data</p>
        <p className="text-xs text-on-surface-variant">{hint ?? "No activity recorded for this workspace."}</p>
      </BrutalCard>
    );
  }
  const numeric = typeof value === "number" ? value : null;
  return (
    <BrutalCard eyebrow={eyebrow} title={title}>
      <p className="text-3xl font-bold text-on-surface">
        {numeric !== null ? <AnimatedCounter from={0} to={numeric} /> : value}
      </p>
      {hint ? <p className="mt-1 text-xs text-on-surface-variant">{hint}</p> : null}
    </BrutalCard>
  );
}
