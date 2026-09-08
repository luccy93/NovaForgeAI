"use client";

import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { cn } from "@/lib/utils";
import type {
  KnowledgeFreshnessStats,
  KnowledgeSource,
  KnowledgeUsageStats,
} from "@/types/knowledge";

function statusTone(status: string): "default" | "yellow" | "error" {
  const s = status.toUpperCase();
  if (s === "ACTIVE") return "yellow";
  if (s === "DELETED" || s === "FAILED" || s === "ERROR") return "error";
  return "default";
}

function freshnessRow(label: string, value: number, total: number) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
        {label}
      </span>
      <span className="font-mono text-xs text-on-surface">{value}</span>
      <span className="h-2 w-16 overflow-hidden border border-outline bg-surface-container">
        <span
          className="block h-full bg-primary-container"
          style={{ width: `${pct}%` }}
          aria-hidden="true"
        />
      </span>
    </div>
  );
}

export function KnowledgeSourcesPanel({
  sources,
  sourcesLoading,
  sourcesError,
  freshness,
  usage,
  onRetry,
}: {
  sources: KnowledgeSource[] | null;
  sourcesLoading: boolean;
  sourcesError: string | null;
  freshness: KnowledgeFreshnessStats | null;
  usage: KnowledgeUsageStats | null;
  onRetry: () => void;
}) {
  const activeSources = (sources ?? []).filter((s) => s.status.toUpperCase() !== "DELETED");

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto" aria-label="Knowledge sources">
      <div className="border-b border-outline px-4 py-3">
        <p className="text-xs font-mono uppercase tracking-widest text-primary-container">
          Knowledge platform
        </p>

        {freshness ? (
          <div className="mt-3 space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
              Freshness · {freshness.total} indexed
            </p>
            {freshnessRow("Fresh", freshness.fresh, freshness.total)}
            {freshnessRow("Aging", freshness.aging, freshness.total)}
            {freshnessRow("Stale", freshness.stale, freshness.total)}
          </div>
        ) : null}

        {usage ? (
          <div className="mt-3 space-y-1">
            <p className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
              Usage (24h)
            </p>
            <div className="flex items-center justify-between">
              <span className="font-mono text-xs text-on-surface">{usage.total_queries} queries</span>
              <span className="font-mono text-xs text-on-surface-variant">
                {usage.avg_latency_ms} ms avg
              </span>
            </div>
            {usage.top_terms.length > 0 ? (
              <p className="font-mono text-[10px] text-on-surface-variant">
                {usage.top_terms.slice(0, 4).join(" · ")}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>

      <div className="flex items-center justify-between px-4 py-3">
        <p className="text-xs font-mono uppercase tracking-widest text-on-surface-variant">
          Sources · {activeSources.length}
        </p>
        <BrutalButton variant="ghost" size="sm" onClick={onRetry}>
          Refresh
        </BrutalButton>
      </div>

      {sourcesLoading ? (
        <div className="space-y-2 p-4" role="status" aria-label="Loading sources">
          <BrutalSkeleton className="h-16" />
          <BrutalSkeleton className="h-16" />
          <BrutalSkeleton className="h-16" />
        </div>
      ) : sourcesError ? (
        <p className="p-4 text-sm text-error" role="alert">
          {sourcesError}
        </p>
      ) : activeSources.length === 0 ? (
        <p className="px-4 pb-4 text-sm text-on-surface-variant">
          No active knowledge sources in this workspace.
        </p>
      ) : (
        <ul className="space-y-2 px-4 pb-4">
          {activeSources.map((source) => (
            <li key={source.source_id} className="border border-outline bg-surface p-3">
              <div className="flex items-center justify-between gap-2">
                <p className="min-w-0 truncate text-sm font-bold text-on-surface">{source.name}</p>
                <BrutalBadge tone={statusTone(source.status)} className={cn("shrink-0")}>
                  {source.status}
                </BrutalBadge>
              </div>
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                {source.source_type}
              </p>
              {source.last_ingested_at ? (
                <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
                  ingested {new Date(source.last_ingested_at).toLocaleDateString()}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}