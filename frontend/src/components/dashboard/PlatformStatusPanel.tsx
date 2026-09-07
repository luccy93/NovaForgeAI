"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import type { HealthDependencies } from "@/types/api";

function statusTone(status: string): "yellow" | "default" | "error" | "muted" {
  const s = status.toLowerCase();
  if (s === "healthy" || s === "operational") return "yellow";
  if (s === "degraded") return "default";
  if (s === "down" || s === "offline" || s === "unhealthy") return "error";
  return "muted";
}

export function PlatformStatusPanel({
  data,
  loading,
  error,
  onRetry,
}: {
  data: HealthDependencies | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  if (loading) return <BrutalCard eyebrow="Platform" title="System status"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Platform" title="System status">
        <div className="border border-error bg-surface p-4 text-sm text-error" role="alert">
          <p className="font-bold">Temporarily unavailable</p>
          <p className="text-on-surface-variant">{error}</p>
          <button onClick={onRetry} className="mt-2 border border-outline px-3 py-1 text-xs uppercase tracking-widest hover:border-primary-container">Retry</button>
        </div>
      </BrutalCard>
    );
  }
  if (!data) {
    return (
      <BrutalCard eyebrow="Platform" title="System status">
        <BrutalEmptyState title="No data" description="No health data available for this workspace." />
      </BrutalCard>
    );
  }
  const overall = data.status || "UNKNOWN";
  return (
    <BrutalCard eyebrow="Platform" title="System status" actions={<BrutalBadge tone={statusTone(overall)}>{overall}</BrutalBadge>}>
      <ul className="space-y-2">
        {Object.entries(data.checks || {}).map(([name, check]) => (
          <li key={name} className="flex items-center justify-between border border-outline-variant bg-surface px-3 py-2">
            <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{name}</span>
            <span className="flex items-center gap-2">
              <BrutalBadge tone={statusTone(check.status)}>{check.status}</BrutalBadge>
              {typeof check.latency_ms === "number" ? <span className="font-mono text-xs text-on-surface-variant">{check.latency_ms}ms</span> : null}
            </span>
          </li>
        ))}
        {Object.keys(data.checks || {}).length === 0 ? <li className="text-sm text-on-surface-variant">No checks reported</li> : null}
      </ul>
    </BrutalCard>
  );
}
