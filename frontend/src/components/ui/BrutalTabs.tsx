"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface BrutalTab {
  id: string;
  label: string;
  content: ReactNode;
}

export function BrutalTabs({ tabs, initialId }: { tabs: Array<BrutalTab>; initialId?: string }) {
  const [active, setActive] = useState(initialId ?? tabs[0]?.id);
  const current = tabs.find((tab) => tab.id === active) ?? tabs[0];
  return (
    <div>
      <div role="tablist" aria-label="Sections" className="mb-4 flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            onClick={() => setActive(tab.id)}
            className={cn(
              "border px-4 py-2 font-mono text-xs uppercase tracking-widest transition-colors",
              tab.id === active
                ? "border-primary-container bg-primary-container text-black"
                : "border-outline bg-transparent text-on-surface-variant hover:border-on-surface hover:text-on-surface",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{current?.content}</div>
    </div>
  );
}
