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

  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const idx = tabs.findIndex((t) => t.id === active);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = tabs[(idx + 1) % tabs.length];
      setActive(next.id);
      document.getElementById(`brutal-tab-${next.id}`)?.focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = tabs[(idx - 1 + tabs.length) % tabs.length];
      setActive(prev.id);
      document.getElementById(`brutal-tab-${prev.id}`)?.focus();
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(tabs[0].id);
      document.getElementById(`brutal-tab-${tabs[0].id}`)?.focus();
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(tabs[tabs.length - 1].id);
      document.getElementById(`brutal-tab-${tabs[tabs.length - 1].id}`)?.focus();
    }
  }

  return (
    <div>
      <div role="tablist" aria-label="Sections" className="mb-4 flex flex-wrap gap-2" onKeyDown={onKeyDown}>
        {tabs.map((tab) => (
          <button
            key={tab.id}
            id={`brutal-tab-${tab.id}`}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            aria-controls={`brutal-panel-${tab.id}`}
            tabIndex={tab.id === active ? 0 : -1}
            onClick={() => setActive(tab.id)}
            className={cn(
              "border px-4 py-2 font-mono text-xs uppercase tracking-widest transition-colors focus-visible:outline-2 focus-visible:outline-primary-container",
              tab.id === active
                ? "border-primary-container bg-primary-container text-black"
                : "border-outline bg-transparent text-on-surface-variant hover:border-on-surface hover:text-on-surface",
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel" id={`brutal-panel-${current?.id}`} aria-labelledby={`brutal-tab-${current?.id}`}>
        {current?.content}
      </div>
    </div>
  );
}
