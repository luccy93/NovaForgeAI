"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import type { WorkflowHealth, WorkflowRun } from "@/types/api";

function healthTone(rate?: number) {
  if (rate === undefined) return "muted" as const;
  if (rate >= 0.95) return "yellow" as const;
  if (rate >= 0.8) return "default" as const;
  return "error" as const;
}

export function WorkflowPanel({
  health,
  runs,
  loading,
  error,
}: {
  health: WorkflowHealth | null;
  runs: WorkflowRun[] | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <BrutalCard eyebrow="Workflows" title="Workflows & agents"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Workflows" title="Workflows & agents">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!health && (!runs || runs.length === 0)) {
    return (
      <BrutalCard eyebrow="Workflows" title="Workflows & agents">
        <BrutalEmptyState title="No data" description="No activity recorded for this workspace." />
      </BrutalCard>
    );
  }
  return (
    <BrutalCard eyebrow="Workflows" title="Workflows & agents" actions={health ? <BrutalBadge tone={healthTone(health.success_rate)}>{health.success} / {health.total} OK</BrutalBadge> : null}>
      {runs && runs.length ? (
        <ul className="space-y-2">
          {runs.slice(0, 5).map((r) => (
            <li key={r.run_id ?? r.id} className="flex items-center justify-between border border-outline-variant bg-surface px-3 py-2">
              <span className="font-mono text-xs text-on-surface">{r.run_id ?? r.id ?? "run"}</span>
              <BrutalBadge tone={r.status === "COMPLETED" || r.status === "success" ? "yellow" : r.status === "FAILED" ? "error" : "muted"}>{r.status}</BrutalBadge>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-on-surface-variant">No recent runs</p>
      )}
    </BrutalCard>
  );
}
