"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import type { IntegrationItem } from "@/types/api";

export function IntegrationsPanel({
  items,
  loading,
  error,
  supported = true,
}: {
  items: IntegrationItem[] | null;
  loading: boolean;
  error: string | null;
  supported?: boolean;
}) {
  if (!supported) return null;
  if (loading) return <BrutalCard eyebrow="Integrations" title="Integrations"><BrutalSkeleton className="h-32" /></BrutalCard>;
  if (error) {
    return (
      <BrutalCard eyebrow="Integrations" title="Integrations">
        <p className="text-sm text-error">Temporarily unavailable</p>
        <p className="text-xs text-on-surface-variant">{error}</p>
      </BrutalCard>
    );
  }
  if (!items || items.length === 0) {
    return (
      <BrutalCard eyebrow="Integrations" title="Integrations">
        <BrutalEmptyState title="No data" description="No integrations connected for this workspace." />
      </BrutalCard>
    );
  }
  return (
    <BrutalCard eyebrow="Integrations" title="Integrations">
      <ul className="space-y-2">
        {items.slice(0, 5).map((it) => (
          <li key={it.id} className="flex items-center justify-between border border-outline-variant bg-surface px-3 py-2">
            <span className="text-sm font-bold text-on-surface">{it.name ?? it.provider ?? it.id.slice(0, 8)}</span>
            <BrutalBadge tone={it.health === "healthy" || it.status === "ACTIVE" ? "yellow" : "muted"}>{it.health ?? it.status ?? "unknown"}</BrutalBadge>
          </li>
        ))}
      </ul>
      <a href="/integrations" className="mt-3 inline-block border border-outline px-3 py-1 font-mono text-xs uppercase tracking-widest hover:border-primary-container">Manage integrations</a>
    </BrutalCard>
  );
}
