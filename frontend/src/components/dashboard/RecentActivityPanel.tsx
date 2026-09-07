"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import type { RecentActivityItem } from "@/types/api";

export function RecentActivityPanel({
  items,
  loading,
  error,
}: {
  items: RecentActivityItem[] | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) return <BrutalCard eyebrow="Activity" title="Recent activity"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Activity" title="Recent activity">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!items || items.length === 0) {
    return (
      <BrutalCard eyebrow="Activity" title="Recent activity">
        <BrutalEmptyState title="No activity" description="No recent events for this workspace." />
      </BrutalCard>
    );
  }
  return (
    <BrutalCard eyebrow="Activity" title="Recent activity">
      <ul className="space-y-2">
        {items.slice(0, 8).map((it) => (
          <li key={it.id} className="border border-outline-variant bg-surface px-3 py-2">
            <p className="flex items-center gap-2 text-sm font-bold text-on-surface">
              {it.event_type} <BrutalBadge tone="muted">{it.source ?? "system"}</BrutalBadge>
            </p>
            <p className="font-mono text-xs text-on-surface-variant">{it.created_at ? new Date(it.created_at).toLocaleString() : ""}</p>
          </li>
        ))}
      </ul>
    </BrutalCard>
  );
}
