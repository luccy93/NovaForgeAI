"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalBadge } from "@/components/ui/BrutalBadge";

export function GovernancePanel({
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
  if (loading) return <BrutalCard eyebrow="Governance" title="Governance"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Governance" title="Governance">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!data || Object.keys(data).length === 0) {
    return (
      <BrutalCard eyebrow="Governance" title="Governance">
        <BrutalEmptyState title="No data" description="No activity recorded for this workspace." />
      </BrutalCard>
    );
  }
  const violations = (data as Record<string, unknown>).violations ?? (data as Record<string, unknown>).violations_24h;
  const posture = (data as Record<string, unknown>).posture_score ?? (data as Record<string, unknown>).score;
  return (
    <BrutalCard eyebrow="Governance" title="Governance">
      <div className="space-y-2 text-sm">
        <p><span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Violations (24h): </span>{typeof violations === "number" ? violations : "—"}</p>
        <p className="flex items-center gap-2"><span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Posture:</span> {posture !== undefined ? <BrutalBadge>{String(posture)}</BrutalBadge> : "—"}</p>
        <a href="/governance" className="inline-block border border-outline px-3 py-1 font-mono text-xs uppercase tracking-widest hover:border-primary-container">View governance</a>
      </div>
    </BrutalCard>
  );
}
