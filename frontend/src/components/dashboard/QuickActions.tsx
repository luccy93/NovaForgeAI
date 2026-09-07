"use client";

import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";

export function QuickActions() {
  return (
    <BrutalCard eyebrow="Actions" title="Quick actions">
      <div className="grid grid-cols-2 gap-2">
        <BrutalButton href="/dashboard" variant="yellow" size="sm">Search knowledge</BrutalButton>
        <BrutalButton href="/ai-kit" variant="default" size="sm">Open AI</BrutalButton>
        <BrutalButton href="/workflows" variant="default" size="sm">New workflow</BrutalButton>
        <BrutalButton href="/integrations" variant="default" size="sm">Connect integration</BrutalButton>
        <BrutalButton href="/security" variant="default" size="sm">View security</BrutalButton>
        <BrutalButton href="/governance" variant="default" size="sm">View governance</BrutalButton>
      </div>
    </BrutalCard>
  );
}
