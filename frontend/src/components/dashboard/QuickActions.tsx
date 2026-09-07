"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";

export interface QuickAction {
  id: string;
  label: string;
  href: string;
  variant: "yellow" | "default";
  description: string;
}

/**
 * Capability-aware quick actions. Only routes that actually exist today are
 * exposed. Future modules register their action here when their page ships —
 * never render a link to a route that does not exist.
 */
export const QUICK_ACTIONS: QuickAction[] = [
  { id: "search-knowledge", label: "Search Knowledge", href: "/dashboard#knowledge", variant: "yellow", description: "Search the knowledge base" },
  { id: "open-ai", label: "Open AI", href: "/ai-kit", variant: "default", description: "Agents, tools and playground" },
];

export function QuickActions() {
  return (
    <BrutalCard eyebrow="Actions" title="Quick actions">
      <ul className="grid grid-cols-2 gap-2">
        {QUICK_ACTIONS.map((action) => (
          <li key={action.id}>
            <BrutalButton href={action.href} variant={action.variant} size="sm" className="w-full">
              {action.label}
            </BrutalButton>
            <p className="mt-1 px-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
              {action.description}
            </p>
          </li>
        ))}
      </ul>
    </BrutalCard>
  );
}