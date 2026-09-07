"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";

export function SecurityPanel({
  data,
  loading,
  error,
  supported = true,
}: {
  data: Record<string, unknown> | null;
  loading: boolean;
  error: string | null;
  supported?: boolean;
}) {
  if (!supported) return null;
  if (loading) return <BrutalCard eyebrow="Security" title="Security posture"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Security" title="Security posture">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!data || Object.keys(data).length === 0) {
    return (
      <BrutalCard eyebrow="Security" title="Security posture">
        <BrutalEmptyState title="No data" description="No activity recorded for this workspace." />
      </BrutalCard>
    );
  }
  // Try to extract common fields without assuming shape
  const risk = (data as Record<string, unknown>).risk_score ?? (data as Record<string, unknown>).risk;
  const findings = (data as Record<string, unknown>).open_findings ?? (data as Record<string, unknown>).total ?? null;
  return (
    <BrutalCard eyebrow="Security" title="Security posture">
      <div className="space-y-2 text-sm">
        <p><span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Findings: </span>{typeof findings === "number" ? findings : "—"}</p>
        <p className="flex items-center gap-2"><span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Risk:</span> {typeof risk === "number" || typeof risk === "string" ? <BrutalBadge tone={String(risk).toLowerCase().includes("high") || Number(risk) > 70 ? "error" : "muted"}>{String(risk)}</BrutalBadge> : "—"}</p>
        <a href="/security" className="inline-block border border-outline px-3 py-1 font-mono text-xs uppercase tracking-widest hover:border-primary-container">View security</a>
      </div>
    </BrutalCard>
  );
}
