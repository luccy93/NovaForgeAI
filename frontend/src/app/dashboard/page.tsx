"use client";

/* eslint-disable react-hooks/set-state-in-effect -- dashboard must clear stale tenant data synchronously on switch */

import { useEffect, useState, useCallback } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { CommandPalette } from "@/components/navigation/CommandPalette";
import { PlatformStatusPanel } from "@/components/dashboard/PlatformStatusPanel";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { AiActivityPanel } from "@/components/dashboard/AiActivityPanel";
import { WorkflowPanel } from "@/components/dashboard/WorkflowPanel";
import { SecurityPanel } from "@/components/dashboard/SecurityPanel";
import { GovernancePanel } from "@/components/dashboard/GovernancePanel";
import { IntegrationsPanel } from "@/components/dashboard/IntegrationsPanel";
import { RecentActivityPanel } from "@/components/dashboard/RecentActivityPanel";
import { QuickActions } from "@/components/dashboard/QuickActions";
import { api, clearToken, getToken } from "@/lib/api";
import type { ApiUser, FinOpsSummary, KnowledgeHit, HealthDependencies, WorkflowHealth, WorkflowRun, AiUsageItem, IntegrationItem, RecentActivityItem } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";
import { useTenantStore } from "@/stores/tenant";

export default function DashboardPage() {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [summary, setSummary] = useState<FinOpsSummary | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<KnowledgeHit>>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);
  const pushToast = useToastStore((s) => s.push);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);

  // Platform status
  const [health, setHealth] = useState<HealthDependencies | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [healthError, setHealthError] = useState<string | null>(null);

  // AI activity
  const [aiItems, setAiItems] = useState<AiUsageItem[] | null>(null);
  const [aiLoading, setAiLoading] = useState(true);
  const [aiError, setAiError] = useState<string | null>(null);
  const [aiSupported, setAiSupported] = useState(true);

  // Workflows
  const [wfHealth, setWfHealth] = useState<WorkflowHealth | null>(null);
  const [wfRuns, setWfRuns] = useState<WorkflowRun[] | null>(null);
  const [wfLoading, setWfLoading] = useState(true);
  const [wfError, setWfError] = useState<string | null>(null);

  // Security
  const [secData, setSecData] = useState<Record<string, unknown> | null>(null);
  const [secLoading, setSecLoading] = useState(true);
  const [secError, setSecError] = useState<string | null>(null);
  const [secSupported, setSecSupported] = useState(true);

  // Governance
  const [govData, setGovData] = useState<Record<string, unknown> | null>(null);
  const [govLoading, setGovLoading] = useState(true);
  const [govError, setGovError] = useState<string | null>(null);
  const [govSupported, setGovSupported] = useState(true);

  // Integrations
  const [intItems, setIntItems] = useState<IntegrationItem[] | null>(null);
  const [intLoading, setIntLoading] = useState(true);
  const [intError, setIntError] = useState<string | null>(null);
  const [intSupported, setIntSupported] = useState(true);

  // Recent activity
  const [activity, setActivity] = useState<RecentActivityItem[] | null>(null);
  const [actLoading, setActLoading] = useState(true);
  const [actError, setActError] = useState<string | null>(null);

  // Knowledge metric
  const [knowledgeCount, setKnowledgeCount] = useState<number | null>(null);
  const [knowledgeCountLoading, setKnowledgeCountLoading] = useState(true);

  useEffect(() => {
    function onKeys(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((value) => !value);
      }
    }
    document.addEventListener("keydown", onKeys);
    return () => document.removeEventListener("keydown", onKeys);
  }, []);

  function sessionExpired() {
    clearToken();
    window.location.href = "/auth/login";
  }

  const fetchAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      window.location.href = "/auth/login";
      return;
    }
    setLoading(true);
    setHealthLoading(true);
    setAiLoading(true);
    setWfLoading(true);
    setSecLoading(true);
    setGovLoading(true);
    setIntLoading(true);
    setActLoading(true);
    setKnowledgeCountLoading(true);
    setError("");
    setHealthError(null);
    setAiError(null);
    setWfError(null);
    setSecError(null);
    setGovError(null);
    setIntError(null);
    setActError(null);

    try {
      const [me, finops] = await Promise.all([api.me(token), api.finopsSummary(token)]);
      setUser(me);
      setSummary(finops);
      setLastUpdated(new Date().toLocaleTimeString());
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message = e instanceof Error ? e.message : "Failed to load dashboard";
      setError(message);
      pushToast("error", message);
    } finally {
      setLoading(false);
    }

    // Platform health - no auth needed but try with token
    try {
      const h = await api.healthDependencies();
      setHealth(h);
    } catch (e) {
      setHealthError(e instanceof Error ? e.message : "Health unavailable");
    } finally {
      setHealthLoading(false);
    }

    // AI activity
    try {
      const res = await api.aiUsage(token, 5);
      setAiItems(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setAiSupported(false);
      else setAiError(e instanceof Error ? e.message : "AI unavailable");
    } finally {
      setAiLoading(false);
    }

    // Workflows
    try {
      const [h, runsRes] = await Promise.all([
        api.workflowHealth(token).catch(() => null),
        api.listWorkflowRuns(token, 5).catch(() => ({ items: [] })),
      ]);
      setWfHealth(h as WorkflowHealth | null);
      setWfRuns((runsRes as { items: WorkflowRun[] })?.items ?? []);
    } catch (e) {
      setWfError(e instanceof Error ? e.message : "Workflows unavailable");
    } finally {
      setWfLoading(false);
    }

    // Security - hide panel if backend capability not available
    try {
      const s = await api.securityDashboard(token);
      setSecData(s as Record<string, unknown>);
      setSecSupported(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setSecSupported(false);
        setSecData(null);
      } else setSecError(e instanceof Error ? e.message : "Security unavailable");
    } finally {
      setSecLoading(false);
    }

    // Governance
    try {
      const g = await api.governancePosture(token);
      setGovData(g as Record<string, unknown>);
      setGovSupported(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setGovSupported(false);
        setGovData(null);
      } else setGovError(e instanceof Error ? e.message : "Governance unavailable");
    } finally {
      setGovLoading(false);
    }

    // Integrations
    try {
      const res = await api.integrationsList(token);
      setIntItems(res.items ?? []);
      setIntSupported(true);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setIntSupported(false);
        setIntItems([]);
      } else setIntError(e instanceof Error ? e.message : "Integrations unavailable");
    } finally {
      setIntLoading(false);
    }

    // Recent activity
    try {
      const res = await api.recentActivity(token, 8);
      setActivity(res.events ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setActivity([]);
      else setActError(e instanceof Error ? e.message : "Activity unavailable");
    } finally {
      setActLoading(false);
    }

    // Knowledge metric (for top card)
    try {
      const res = await api.knowledgeHistory(token, 1);
      setKnowledgeCount(res.total ?? 0);
    } catch {
      setKnowledgeCount(null);
    } finally {
      setKnowledgeCountLoading(false);
    }
  }, [pushToast]);

  useEffect(() => {
    void fetchAll();
    // Re-fetch on tenant/workspace switch - clear stale data first
    const handler = () => {
      setSummary(null);
      setHealth(null);
      setAiItems(null);
      setWfHealth(null);
      setWfRuns(null);
      setSecData(null);
      setGovData(null);
      setIntItems(null);
      setActivity(null);
      setKnowledgeCount(null);
      setResults([]);
      void fetchAll();
    };
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
    };
  }, [fetchAll, organizationId, workspaceId]);

  async function onSearch() {
    const token = getToken();
    if (!token || !query.trim()) return;
    setError("");
    setSearching(true);
    try {
      const res = await api.knowledgeSearch(token, query.trim());
      setResults(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message = e instanceof Error ? e.message : "Search failed";
      setError(message);
      pushToast("error", message);
    } finally {
      setSearching(false);
    }
  }

  function logout() {
    clearToken();
    window.location.href = "/";
  }

  const email = typeof user?.email === "string" ? user.email : null;
  const orgLabel = organizationId ? `Org ${organizationId.slice(0, 8)}` : null;
  const wsLabel = workspaceId ? `WS ${workspaceId.slice(0, 8)}` : email ? "Workspace" : null;

  return (
    <AppShell
      email={email}
      workspaceLabel={wsLabel ?? orgLabel ?? (email ? "Workspace" : null)}
      onLogout={logout}
      onOpenPalette={() => setPaletteOpen(true)}
      onOpenSearch={() => setPaletteOpen(true)}
    >
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <div className="border-b border-outline bg-surface">
        <div className="mx-auto flex max-w-[1600px] flex-wrap items-center justify-between gap-4 px-4 py-4 lg:px-6">
          <div>
            <h1 className="font-mono text-xs uppercase tracking-widest text-primary-container">Command Center</h1>
            <p className="text-sm text-on-surface-variant">
              {orgLabel ?? "No org"} {workspaceId ? `· ${wsLabel}` : ""} {lastUpdated ? `· Updated ${lastUpdated}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <BrutalButton variant="ghost" size="sm" onClick={() => void fetchAll()}>Refresh</BrutalButton>
            <span className="font-mono text-xs text-on-surface-variant">{new Date().toLocaleDateString()}</span>
          </div>
        </div>
      </div>

      <div className="mx-auto w-full max-w-[1600px] px-4 py-6 lg:px-6">
        {error ? (
          <div className="mb-6">
            <BrutalErrorState title="Request failed" description={error} onRetry={() => void fetchAll()} />
          </div>
        ) : null}

        {/* Top metrics - only real values */}
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard eyebrow="Spend" title="Current spend" value={summary ? summary.spend_cents : null} loading={loading} error={error || null} hint={summary ? `${summary.cost_records} records · ${summary.total_tokens} tokens` : undefined} />
          <MetricCard eyebrow="AI" title="AI executions" value={summary ? summary.ai_executions : null} loading={loading} hint={summary ? `${summary.ai_tokens} tokens` : undefined} />
          <MetricCard eyebrow="Workflows" title="Active runs" value={wfHealth ? wfHealth.total - (wfHealth.failed ?? 0) : null} loading={wfLoading} error={wfError} hint={wfHealth ? `${wfHealth.success_rate ? Math.round(wfHealth.success_rate * 100) + "% success" : ""}` : undefined} />
          <MetricCard eyebrow="Knowledge" title="Queries" value={knowledgeCount} loading={knowledgeCountLoading} hint={knowledgeCount !== null ? `${knowledgeCount} total queries` : "Use search below"} />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <PlatformStatusPanel data={health} loading={healthLoading} error={healthError} onRetry={() => void fetchAll()} />
          <AiActivityPanel items={aiItems} loading={aiLoading} error={aiError} supported={aiSupported} />
          <WorkflowPanel health={wfHealth} runs={wfRuns} loading={wfLoading} error={wfError} />
        </div>

        <div className="mt-6 grid gap-6 md:grid-cols-2">
          <BrutalCard eyebrow="Account" title={email ? String(user?.username ?? "Account") : "Account"}>
            {loading ? <BrutalSkeleton className="h-16" /> : user ? (
              <div className="space-y-1 text-body-md">
                <p><span className="text-on-surface-variant">Email: </span>{String(user.email ?? "—")}</p>
                <p><span className="text-on-surface-variant">Username: </span>{String(user.username ?? "—")}</p>
              </div>
            ) : <BrutalEmptyState title="Not signed in" description="Sign in to load your account." />}
          </BrutalCard>
          <BrutalCard eyebrow="FinOps" title="Usage">
            {loading ? <BrutalSkeleton className="h-16" /> : summary ? (
              <div className="space-y-1 text-body-md">
                <p><span className="text-on-surface-variant">Spend (cents): </span>{String(summary.spend_cents ?? 0)}</p>
                <p><span className="text-on-surface-variant">Cost records: </span>{String(summary.cost_records ?? 0)}</p>
                <p><span className="text-on-surface-variant">Total tokens: </span>{String(summary.total_tokens ?? 0)}</p>
                <a href="/finops" className="mt-2 inline-block border border-outline px-3 py-1 font-mono text-xs uppercase tracking-widest hover:border-primary-container">View FinOps</a>
              </div>
            ) : <BrutalEmptyState title="No usage yet" description="Usage appears here once recorded." />}
          </BrutalCard>
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <SecurityPanel data={secData} loading={secLoading} error={secError} supported={secSupported} />
          <GovernancePanel data={govData} loading={govLoading} error={govError} supported={govSupported} />
          <IntegrationsPanel items={intItems} loading={intLoading} error={intError} supported={intSupported} />
        </div>

        <div className="mt-6 grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <BrutalCard eyebrow="Knowledge" title="Search">
              <div className="mb-4 flex flex-col gap-4 sm:flex-row">
                <div className="flex-1">
                  <BrutalInput aria-label="Search the knowledge base" placeholder="Search the knowledge base…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void onSearch(); }} />
                </div>
                <BrutalButton variant="yellow" size="md" onClick={() => void onSearch()}>{searching ? "Searching…" : "Search"}</BrutalButton>
              </div>
              {searching ? <BrutalSkeleton className="h-24" label="Searching" /> : results.length > 0 ? (
                <ul className="space-y-3">
                  {results.map((r, i) => (
                    <li key={String(r.document_id ?? r.chunk_id ?? i)} className="border border-outline p-4">
                      <p className="font-bold text-on-surface">{String(r.title ?? r.document_id ?? "Result")}</p>
                      <p className="text-sm text-on-surface-variant">{String(r.snippet ?? r.citation ?? "")}</p>
                      <p className="mt-1 font-mono text-xs text-on-surface-variant">score: {String(r.score ?? "—")}</p>
                    </li>
                  ))}
                </ul>
              ) : <BrutalEmptyState title="No results yet" description="Try a search above." />}
              {results.length > 0 ? <p className="mt-2 font-mono text-xs text-on-surface-variant">{results.length} results</p> : null}
            </BrutalCard>
          </div>
          <div className="space-y-6">
            <RecentActivityPanel items={activity} loading={actLoading} error={actError} />
            <QuickActions />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
