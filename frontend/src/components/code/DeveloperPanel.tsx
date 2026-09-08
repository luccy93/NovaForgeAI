"use client";

import { useState } from "react";
import { DeveloperAgents } from "@/components/code/DeveloperAgents";
import { DeveloperChanges } from "@/components/code/DeveloperChanges";
import { DeveloperExplain } from "@/components/code/DeveloperExplain";
import { DeveloperGraph } from "@/components/code/DeveloperGraph";
import { DeveloperPatches } from "@/components/code/DeveloperPatches";
import { DeveloperTests } from "@/components/code/DeveloperTests";

type DevTabId = "explain" | "changes" | "tests" | "graph" | "agents" | "patches";

const tabs: Array<{ id: DevTabId; label: string }> = [
  { id: "explain", label: "Explain" },
  { id: "changes", label: "Changes" },
  { id: "tests", label: "Tests" },
  { id: "graph", label: "Graph" },
  { id: "agents", label: "Agents" },
  { id: "patches", label: "Patches" },
];

export function DeveloperPanel({
  repoId,
  defaultBranch,
}: {
  repoId: string;
  defaultBranch?: string | null;
}) {
  const [active, setActive] = useState<DevTabId>("explain");

  return (
    <section
      aria-label="Developer intelligence"
      className="flex h-80 w-full shrink-0 flex-col border-t border-outline bg-surface"
    >
      <div className="border-b border-outline-variant px-1 pt-1">
        <div role="tablist" aria-label="Developer intelligence" className="flex flex-wrap gap-1">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={tab.id === active}
              onClick={() => setActive(tab.id)}
              className={
                tab.id === active
                  ? "border border-primary-container bg-primary-container px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-black"
                  : "border border-outline bg-transparent px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant hover:border-on-surface"
              }
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto bg-surface-container/50 p-3">
        {active === "explain" ? <DeveloperExplain repoId={repoId} /> : null}
        {active === "changes" ? <DeveloperChanges repoId={repoId} /> : null}
        {active === "tests" ? <DeveloperTests repoId={repoId} defaultBranch={defaultBranch} /> : null}
        {active === "graph" ? <DeveloperGraph repoId={repoId} /> : null}
        {active === "agents" ? <DeveloperAgents repoId={repoId} /> : null}
        {active === "patches" ? <DeveloperPatches repoId={repoId} /> : null}
      </div>
    </section>
  );
}