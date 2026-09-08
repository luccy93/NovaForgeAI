"use client";

import { useEffect, useMemo, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type {
  ChangeSummaryOut,
  ChurnMetricsOut,
  ContributorStatsOut,
  HotspotOut,
  ImpactAnalysisOut,
  OwnershipSummaryOut,
  QualitySummary,
  SecurityScanOut,
  SmellScanOut,
  TestCoverageOut,
  TestGapOut,
} from "@/types/code";
import { ApiError } from "@/lib/api-client";

function sessionExpired() {
  window.location.href = "/auth/login";
}

type TabId = "impact" | "security" | "quality" | "tests" | "ownership" | "history";

// Loads each intelligence tab's data on demand (only when the user opens it),
// always against the real backend. Any failing tab shows an honest error with
// retry — a failed analysis never blanks the whole workspace.
export function IntelligencePanel({ repoId }: { repoId: string | null }) {
  const [active, setActive] = useState<TabId>("impact");
  const [results, setResults] = useState<Partial<Record<TabId, unknown>>>({});
  const [loading, setLoading] = useState<Partial<Record<TabId, boolean>>>({});
  const [errors, setErrors] = useState<Partial<Record<TabId, string | null>>>({});

  const loadTab = async (tab: TabId) => {
    const token = getToken();
    if (!token || !repoId) return;
    setLoading((prev) => ({ ...prev, [tab]: true }));
    setErrors((prev) => ({ ...prev, [tab]: null }));
    const fetchTab = getTabFetcher(token, repoId, tab);
    try {
      const data = await fetchTab();
      setResults((prev) => ({ ...prev, [tab]: data }));
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setErrors((prev) => ({
        ...prev,
        [tab]: e instanceof Error ? e.message : `Failed to load ${tab} intelligence`,
      }));
    } finally {
      setLoading((prev) => ({ ...prev, [tab]: false }));
    }
  };

  // The parent remounts this panel for each repository (key change), so local
  // state resets naturally. Load the active tab on demand.
  useEffect(() => {
    if (repoId && !loading[active]) {
      void loadTab(active);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId, active]);

  const selected = {
    ...results,
  };

  const tabs = useMemo(
    () => [
      { id: "impact" as const, label: "Impact", content: renderTab(active, selected, loading, errors, () => loadTab("impact")) },
      { id: "security" as const, label: "Security", content: renderTab(active, selected, loading, errors, () => loadTab("security")) },
      { id: "quality" as const, label: "Quality", content: renderTab(active, selected, loading, errors, () => loadTab("quality")) },
      { id: "tests" as const, label: "Tests", content: renderTab(active, selected, loading, errors, () => loadTab("tests")) },
      { id: "ownership" as const, label: "Ownership", content: renderTab(active, selected, loading, errors, () => loadTab("ownership")) },
      { id: "history" as const, label: "History", content: renderTab(active, selected, loading, errors, () => loadTab("history")) },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [active, loading, errors, results, repoId],
  );

  const activeTab = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div className="flex h-full flex-col min-h-0">
      <div className="bg-surface px-1 pt-1">
        <div role="tablist" aria-label="Code intelligence" className="flex flex-wrap gap-1">
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
      <div className="min-h-0 flex-1 overflow-y-auto bg-surface-container/50 p-3">{activeTab.content}</div>
    </div>
  );
}

function getTabFetcher(token: string, repoId: string, tab: TabId): () => Promise<unknown> {
  switch (tab) {
    case "impact":
      return () => api.ciImpactAnalyze(token, repoId, { change_type: "modify" });
    case "security":
      return () => api.ciSecurityScan(token, repoId);
    case "quality":
      return () => api.ciQualitySummary(token, repoId);
    case "tests":
      return api.ciTests.bind(null, token, repoId);
    case "ownership":
      return api.ciOwnership.bind(null, token, repoId);
    case "history":
      return api.ciChangeSummary.bind(null, token, repoId);
  }
}

function renderTab(
  active: TabId,
  selected: Partial<Record<TabId, unknown>>,
  loading: Partial<Record<TabId, boolean>>,
  errors: Partial<Record<TabId, string | null>>,
  onRetry: () => void,
) {
  // Only the active tab is loaded; others show an idle hint until opened.
  if (loading[active]) {
    return <BrutalSkeleton className="h-40 w-full" label="Loading intelligence" />;
  }
  if (errors[active]) {
    return (
      <BrutalErrorState
        title="Intelligence unavailable"
        description={errors[active] ?? undefined}
        onRetry={onRetry}
      />
    );
  }
  if (!selected[active]) {
    return (
      <BrutalEmptyState
        title={active === "impact" ? "Impact analysis" : `${active} intelligence`}
        description="Opening this tab loads analysis from the backend."
      />
    );
  }
  return <TabContent tab={active} data={selected[active]} onRetry={onRetry} />;
}

function TabContent({ tab, data }: { tab: TabId; data: unknown; onRetry: () => void }) {
  switch (tab) {
    case "impact":
      return <ImpactView data={data as ImpactAnalysisOut} />;
    case "security":
      return <SecurityView data={data as SecurityScanOut} />;
    case "quality":
      return <QualityView data={data as QualitySummary} />;
    case "tests":
      return <TestsView data={data as TestCoverageOut} />;
    case "ownership":
      return <OwnershipView data={data as OwnershipSummaryOut} />;
    case "history":
      return <HistoryView data={data as ChangeSummaryOut} />;
  }
}

function StatGrid({ items }: { items: Array<{ label: string; value: string }> }) {
  return (
    <dl className="grid grid-cols-2 gap-2">
      {items.map((item) => (
        <div key={item.label} className="border border-outline bg-surface p-3">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{item.label}</dt>
          <dd className="mt-1 font-mono text-lg font-bold text-on-surface">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ImpactView({ data }: { data: ImpactAnalysisOut }) {
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Affected files", value: String(data.affected_files) },
          { label: "Affected symbols", value: String(data.affected_symbols) },
          { label: "Impact score", value: data.impact_score.toFixed(2) },
          { label: "Risk", value: data.risk_level },
        ]}
      />
      <ListBlock
        title="Breaking changes"
        items={data.breaking_changes.map((b) => `${b.symbol_name} (${b.file_path}:${b.line}) — ${b.reason}`)}
        empty="No breaking changes detected."
      />
      <ListBlock
        title="Potentially unused"
        items={data.unused_items.map((u) => `${u.symbol_name} (${u.file_path}:${u.line})`)}
        empty="No unused items detected."
      />
    </div>
  );
}

function SecurityView({ data }: { data: SecurityScanOut }) {
  const sev = data.by_severity ?? {};
  const bySeverity = Object.entries(sev).map(([k, v]) => `${k}:${v}`);
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Vulnerabilities", value: String(data.total_vulnerabilities) },
          ...bySeverity.map((s) => ({ label: "Severity", value: s })),
        ]}
      />
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Findings</h3>
      {data.vulnerabilities.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">No vulnerabilities detected in the indexed code.</p>
      ) : (
        <ul className="space-y-1">
          {data.vulnerabilities.map((v) => (
            <li key={v.id} className="border border-outline bg-surface p-2">
              <span className="flex items-center gap-2">
                <BrutalBadge tone={v.severity === "high" || v.severity === "critical" ? "error" : "yellow"}>
                  {v.severity}
                </BrutalBadge>
                <span className="truncate font-mono text-xs text-on-surface">{v.vulnerability_type}</span>
              </span>
              <p className="mt-1 text-sm text-on-surface-variant">{v.message}</p>
              {v.recommendation ? (
                <p className="mt-1 font-mono text-[11px] text-primary-container">{v.recommendation}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function QualityView({ data }: { data: QualitySummary }) {
  const sev = data.smells_by_severity ?? {};
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Files analyzed", value: String(data.total_files) },
          { label: "Code lines", value: data.total_code_lines.toLocaleString() },
          { label: "Avg complexity", value: String(data.avg_complexity) },
          { label: "Avg maintainability", value: String(data.avg_maintainability) },
          { label: "Code smells", value: String(data.total_smells) },
        ]}
      />
      {Object.keys(sev).length > 0 ? (
        <ListBlock
          title="Smells by severity"
          items={Object.entries(sev).map(([k, v]) => `${k}: ${v}`)}
          empty=""
        />
      ) : null}
    </div>
  );
}

function TestsView({ data }: { data: TestCoverageOut }) {
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Test files", value: String(data.total_test_files) },
          { label: "Test functions", value: String(data.total_test_functions) },
        ]}
      />
      {data.frameworks_used.length > 0 ? (
        <p className="text-sm text-on-surface-variant">Frameworks: {data.frameworks_used.join(", ")}</p>
      ) : null}
    </div>
  );
}

function OwnershipView({ data }: { data: OwnershipSummaryOut }) {
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Total files", value: String(data.total_files) },
          { label: "Owned files", value: String(data.owned_files) },
          { label: "Coverage", value: `${(data.ownership_coverage * 100).toFixed(1)}%` },
          { label: "Contributors", value: String(data.total_contributors) },
          { label: "Bus risk files", value: String(data.bus_risk_files) },
          { label: "Unowned files", value: String(data.unowned_files) },
        ]}
      />
    </div>
  );
}

function HistoryView({ data }: { data: ChangeSummaryOut }) {
  return (
    <div className="space-y-3">
      <StatGrid
        items={[
          { label: "Commits", value: String(data.total_commits) },
          { label: "Files changed", value: String(data.total_files_changed) },
          { label: "Authors", value: String(data.total_authors) },
          { label: "Date range (days)", value: String(data.date_range_days) },
          { label: "Avg commits/day", value: String(data.avg_commits_per_day) },
        ]}
      />
    </div>
  );
}

function ListBlock({ title, items, empty }: { title: string; items: string[]; empty: string }) {
  return (
    <div>
      <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{title}</h3>
      {items.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">{empty}</p>
      ) : (
        <ul className="mt-1 space-y-1">
          {items.map((item, i) => (
            <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// Keep type imports referenced to prevent lint removal.
export type {
  ChangeSummaryOut,
  ChurnMetricsOut,
  ContributorStatsOut,
  HotspotOut,
  ImpactAnalysisOut,
  OwnershipSummaryOut,
  QualitySummary,
  SecurityScanOut,
  SmellScanOut,
  TestCoverageOut,
  TestGapOut,
};