"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import type { AiUsageItem } from "@/types/api";

export function AiActivityPanel({
  items,
  loading,
  error,
  supported = true,
}: {
  items: AiUsageItem[] | null;
  loading: boolean;
  error: string | null;
  supported?: boolean;
}) {
  if (!supported) return null;
  if (loading) return <BrutalCard eyebrow="AI" title="AI activity"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="AI" title="AI activity">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!items || items.length === 0) {
    return (
      <BrutalCard eyebrow="AI" title="AI activity">
        <BrutalEmptyState title="No data" description="No activity recorded for this workspace." />
      </BrutalCard>
    );
  }
  return (
    <BrutalCard eyebrow="AI" title="AI activity">
      <ul className="space-y-2">
        {items.slice(0, 5).map((it) => (
          <li key={it.id} className="flex items-center justify-between border border-outline-variant bg-surface px-3 py-2">
            <div>
              <p className="text-sm font-bold text-on-surface">{it.action} · {it.model ?? "unknown model"}</p>
              <p className="font-mono text-xs text-on-surface-variant">{new Date(it.created_at ?? "").toLocaleString()} · {it.total_tokens ?? 0} tokens</p>
            </div>
            <BrutalBadge tone="muted">{it.model?.split("/")[0] ?? it.action}</BrutalBadge>
          </li>
        ))}
      </ul>
    </BrutalCard>
  );
}
