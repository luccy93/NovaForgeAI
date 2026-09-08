"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { ObservabilityDashboard } from "@/types/api";
import type {
  AiopsStatus,
  AlertFatigueReport,
  ObservabilityAlertsResponse,
  ObservabilityQuality,
  SreAnalytics,
  SreStatusComponent,
  SreStatusSummary,
} from "@/types/observability";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

const STATUS_ORDER = ["operational", "degraded", "partial_outage", "major_outage"];

function formatPercents(value: number | null): string {
  if (value === null || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="font-mono text-sm text-on-surface">{value}</span>
    </div>
  );
}

function LoadingPanel({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: rows }).map((_, index) => (
        <BrutalSkeleton key={index} className="h-8" label="Loading panel" />
      ))}
    </div>
  );
}

function PanelBody({
  loading,
  error,
  onRetry,
  children,
  emptyTitle,
  emptyDescription,
}: {
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  children: ReactNode;
  emptyTitle: string;
  emptyDescription?: string;
}) {
  if (loading) return <LoadingPanel />;
  if (error) {
    return <BrutalErrorState title="Unavailable" description={error} onRetry={onRetry} />;
  }
  if (children === undefined || children === null) {
    return <BrutalEmptyState title={emptyTitle} description={emptyDescription} />;
  }
  return <div>{children}</div>;
}

interface UnavailableCapability {
  key: string;
  label: string;
  reason: string;
}

const UNAVAILABLE_CAPABILITIES: UnavailableCapability[] = [
  { key: "realtime", label: "Realtime", reason: "No operational SSE subscription endpoint" },
  { key: "workers", label: "Workers", reason: "No routed worker status endpoint" },
  { key: "eventbus", label: "Event Bus", reason: "No event-bus status GET endpoint" },
  { key: "logs", label: "Logs", reason: "Ingest-only POST; no read feed" },
  { key: "traces", label: "Traces", reason: "Only empty correlate endpoint" },
  { key: "events-feed", label: "Events Feed", reason: "No global feed GET endpoint" },
];

function HealthMap({ health }: { health: Record<string, unknown> }) {
  const entries = Object.entries(health ?? {});
  if (entries.length === 0) {
    return <BrutalEmptyState title="No service health registered" description="Register services to see health here." />;
  }
  return (
    <ul className="space-y-1">
      {entries.map(([resource, status]) => (
        <li key={resource} className="flex items-baseline justify-between gap-4">
          <span className="text-sm text-on-surface">{resource}</span>
          <BrutalBadge tone={String(status) === "healthy" || String(status) === "HEALTHY" || String(status) === "ok" ? "yellow" : String(status) === "unhealthy" ? "error" : "muted"}>
            {String(status).toUpperCase()}
          </BrutalBadge>
        </li>
      ))}
    </ul>
  );
}

export function ObservabilityWorkspace() {
  const [dashboard, setDashboard] = useState<ObservabilityDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);

  const [statusSummary, setStatusSummary] = useState<SreStatusSummary | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [statusComponents, setStatusComponents] = useState<SreStatusComponent[] | null>(null);
  const [statusComponentsError, setStatusComponentsError] = useState<string | null>(null);

  const [aiops, setAiops] = useState<AiopsStatus | null>(null);
  const [aiopsError, setAiopsError] = useState<string | null>(null);

  const [analytics, setAnalytics] = useState<SreAnalytics | null>(null);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);

  const [alerts, setAlerts] = useState<ObservabilityAlertsResponse | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);

  const [fatigue, setFatigue] = useState<AlertFatigueReport | null>(null);
  const [fatigueError, setFatigueError] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setDashboardError(null);
    setStatusError(null);
    setStatusComponentsError(null);
    setAiopsError(null);
    setAnalyticsError(null);
    setAlertsError(null);
    setFatigueError(null);

    async function guarded<T>(load: () => Promise<T>): Promise<T | null> {
      try {
        return await load();
      } catch (e) {
        if (seq !== seqRef.current) return null;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return null;
        }
        throw e;
      }
    }

    async function settle<T>(load: () => Promise<T>, set: (value: T | null) => void, onError: (message: string) => void, errorMessage: string) {
      try {
        const value = await guarded(load);
        if (value !== null && seq === seqRef.current) set(value);
      } catch (e) {
        if (seq !== seqRef.current) return;
        onError(e instanceof Error ? e.message : errorMessage);
      }
    }

    void Promise.all([
      settle(() => api.observabilityDashboard(token), setDashboard, setDashboardError, "Dashboard unavailable"),
      settle(() => api.sreStatusSummary(token), setStatusSummary, setStatusError, "Status unavailable"),
      settle(() => api.sreStatusComponents(token, { limit: 100 }), (value) => setStatusComponents(value?.items ?? null), setStatusComponentsError, "Components unavailable"),
      settle(() => api.observabilityAiopsStatus(token), setAiops, setAiopsError, "AIOps status unavailable"),
      settle(() => api.sreAnalytics(token, 30), setAnalytics, setAnalyticsError, "Analytics unavailable"),
      settle(() => api.observabilityAlerts(token), setAlerts, setAlertsError, "Alerts unavailable"),
      settle(() => api.observabilityAlertFatigue(token), setFatigue, setFatigueError, "Fatigue report unavailable"),
    ]).then(() => {
      if (seq === seqRef.current) {
        setUpdatedAt(new Date().toLocaleTimeString());
        setLoading(false);
      }
    });
  }, []);

  useEffect(() => {
    void loadAll();

    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setDashboard(null);
      setStatusSummary(null);
      setStatusComponents(null);
      setAiops(null);
      setAnalytics(null);
      setAlerts(null);
      setFatigue(null);
      setDashboardError(null);
      setStatusError(null);
      setStatusComponentsError(null);
      setAiopsError(null);
      setAnalyticsError(null);
      setAlertsError(null);
      setFatigueError(null);
      setLoading(true);
      void loadAll();
    };
    window.addEventListener("tenant:switched", resetForContextSwitch as EventListener);
    window.addEventListener("workspace:switched", resetForContextSwitch as EventListener);

    return () => {
      window.removeEventListener("tenant:switched", resetForContextSwitch as EventListener);
      window.removeEventListener("workspace:switched", resetForContextSwitch as EventListener);
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, [loadAll]);

  const quality: ObservabilityQuality | null =
    aiops && aiops.quality && "overall_score" in aiops.quality ? (aiops.quality as ObservabilityQuality) : null;

  const statusOrdered = (summary: SreStatusSummary) => {
    const known = STATUS_ORDER.filter((status) => (summary.by_status[status] ?? 0) > 0);
    const extra = Object.entries(summary.by_status)
      .filter(([status]) => !STATUS_ORDER.includes(status))
      .map(([status, count]) => `${status}: ${count}`);
    return [...known.map((status) => `${status}: ${summary.by_status[status]}`), ...extra];
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border border-outline bg-surface-container px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant" aria-live="polite">
            <span className="h-2 w-2 bg-muted" aria-hidden="true" />
            Realtime: UNAVAILABLE
          </span>
          <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            {updatedAt ? `Updated ${updatedAt}` : "Loading…"}
          </span>
        </div>
        <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
          {loading ? "Refreshing…" : "Refresh"}
        </BrutalButton>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <BrutalCard eyebrow="Status" title="Service health">
          <PanelBody
            loading={loading}
            error={statusError}
            onRetry={() => void loadAll()}
            emptyTitle="No status components"
            emptyDescription="Register status components from the SRE service catalog."
          >
            {statusSummary ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Overall</span>
                  <BrutalBadge tone={statusSummary.overall === "operational" ? "yellow" : statusSummary.overall === "major_outage" ? "error" : "default"}>
                    {statusSummary.overall.toUpperCase()}
                  </BrutalBadge>
                </div>
                <StatRow label="Components" value={String(statusSummary.components)} />
                {statusOrdered(statusSummary).map((line) => {
                  const [statusLabel, count] = line.split(": ");
                  return <StatRow key={statusLabel} label={statusLabel} value={count} />;
                })}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Platform" title="Registered services">
          <PanelBody
            loading={loading}
            error={dashboardError}
            onRetry={() => void loadAll()}
            emptyTitle="No services registered"
            emptyDescription="Observability services appear here once registered."
          >
            {dashboard ? (
              <div className="space-y-3">
                <StatRow label="Service count" value={String(dashboard.services)} />
                <HealthMap health={dashboard.health ?? {}} />
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Status page" title="Components">
          <PanelBody
            loading={loading}
            error={statusComponentsError}
            onRetry={() => void loadAll()}
            emptyTitle="No status components"
            emptyDescription="Status components appear here once configured."
          >
            {statusComponents && statusComponents.length > 0 ? (
              <ul className="space-y-1">
                {statusComponents.map((component) => (
                  <li key={component.component_id} className="flex items-baseline justify-between gap-4">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{component.name}</p>
                      {component.service_id ? (
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{component.service_id}</p>
                      ) : null}
                    </div>
                    <BrutalBadge tone={component.status === "operational" ? "yellow" : component.status === "major_outage" ? "error" : "default"}>
                      {component.status.toUpperCase()}
                    </BrutalBadge>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="AIOps" title="Pipeline & telemetry quality">
          <PanelBody
            loading={loading}
            error={aiopsError}
            onRetry={() => void loadAll()}
            emptyTitle="AIOps status unavailable"
            emptyDescription="AIOps status could not be loaded."
          >
            {aiops ? (
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {(aiops.stages ?? []).map((stage) => (
                    <BrutalBadge key={stage} tone="muted">
                      {String(stage)}
                    </BrutalBadge>
                  ))}
                </div>
                {quality ? (
                  <div className="space-y-2">
                    <StatRow label="Quality grade" value={quality.grade.toUpperCase()} />
                    <StatRow label="Quality score" value={String(quality.overall_score)} />
                    <div>
                      {Object.entries(quality.breakdown).map(([key, item]) => (
                        <div key={key} className="flex items-baseline justify-between gap-4 py-1">
                          <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{key}</span>
                          <span className="font-mono text-sm text-on-surface">{item.score !== undefined ? String(item.score) : "—"}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : null}
                <p className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  {aiops.disclaimer}
                </p>
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Operations" title={`Incident analytics · ${analytics?.period_days ?? 30} days`}>
          <PanelBody
            loading={loading}
            error={analyticsError}
            onRetry={() => void loadAll()}
            emptyTitle="No analytics"
            emptyDescription="Analytics are computed from real incident and deployment records."
          >
            {analytics ? (
              <div className="space-y-1">
                <StatRow label="Incidents · total" value={String(analytics.incidents.total)} />
                <StatRow label="Incidents · open" value={String(analytics.incidents.open)} />
                <StatRow label="MTTD (hours)" value={analytics.incidents.mttd_hours !== null ? String(analytics.incidents.mttd_hours) : "—"} />
                <StatRow label="MTTA (hours)" value={analytics.incidents.mtta_hours !== null ? String(analytics.incidents.mtta_hours) : "—"} />
                <StatRow label="MTTM (hours)" value={analytics.incidents.mttm_hours !== null ? String(analytics.incidents.mttm_hours) : "—"} />
                <StatRow label="MTTR (hours)" value={analytics.incidents.mttr_hours !== null ? String(analytics.incidents.mttr_hours) : "—"} />
                <StatRow label="Deployments · total" value={String(analytics.deployments.total)} />
                <StatRow label="Change failure rate" value={formatPercents(analytics.deployments.change_failure_rate)} />
                <StatRow label="Alerts · total" value={String(analytics.alerts.total)} />
                <StatRow label="Alerts · firing" value={String(analytics.alerts.firing)} />
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="Alerts" title="Recent runtime alerts">
          <PanelBody
            loading={loading}
            error={alertsError}
            onRetry={() => void loadAll()}
            emptyTitle="No alerts"
            emptyDescription="Runtime alerts appear here once they fire."
          >
            {alerts && alerts.items.length > 0 ? (
              <ul className="space-y-2">
                {alerts.items.map((alert) => (
                  <li key={alert.id} className="flex items-baseline justify-between gap-4 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{alert.resource}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {alert.severity} · {alert.fingerprint}
                      </p>
                    </div>
                    <BrutalBadge tone={alert.status === "RESOLVED" ? "yellow" : alert.status === "FIRING" ? "error" : "default"}>
                      {alert.status}
                    </BrutalBadge>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Noise" title="Alert fatigue (24h)">
          <PanelBody
            loading={loading}
            error={fatigueError}
            onRetry={() => void loadAll()}
            emptyTitle="No fatigue signals"
            emptyDescription="Receipts are healthy when an incident is resolved; nudge your reviewers."
          >
            {fatigue ? (
              <div className="space-y-3">
                <StatRow label="Alerts in window" value={String(fatigue.total)} />
                {(fatigue.recommendations ?? []).filter((recommendation) => recommendation !== null).length > 0 ? (
                  <ul className="space-y-1">
                    {(fatigue.recommendations ?? []).map((recommendation, index) => (
                      <li key={index} className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                        {recommendation.type.toUpperCase()} {recommendation.action ? `· ${recommendation.action.toUpperCase()}` : ""}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No noise signals detected.</p>
                )}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <BrutalCard eyebrow="Capabilities" title="Unavailable operations surfaces">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {UNAVAILABLE_CAPABILITIES.map((capability) => (
            <div key={capability.key} className="border border-outline bg-surface p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="font-bold text-on-surface">{capability.label}</span>
                <BrutalBadge tone="error">UNAVAILABLE</BrutalBadge>
              </div>
              <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{capability.reason}</p>
            </div>
          ))}
        </div>
        <p className="mt-4 border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          These surfaces have no authenticated read endpoint in the current backend. Use the manual refresh control above.
        </p>
      </BrutalCard>
    </div>
  );
}