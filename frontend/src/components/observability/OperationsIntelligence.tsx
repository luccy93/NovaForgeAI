"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { useToastStore } from "@/stores/toast";
import type {
  AlertFatigueReport,
  ObservabilityAlert,
  ObservabilityAlertsResponse,
  SreIncident,
  SreIncidentStatus,
  SreIncidentTimeline,
  SreService,
  SreServiceDependencies,
} from "@/types/observability";
import { INCIDENT_TRANSITIONS } from "@/types/observability";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

type Tab = "incidents" | "services" | "fatigue" | "handoff";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "incidents", label: "Incidents" },
  { id: "services", label: "Services" },
  { id: "fatigue", label: "Alert fatigue" },
  { id: "handoff", label: "AI handoff" },
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function formatDurationMinutes(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value} min`;
}

function incidentTone(status: SreIncidentStatus): "error" | "yellow" | "muted" | "default" {
  if (status === "resolved" || status === "closed") return "muted";
  if (status === "detected" || status === "investigating") return "error";
  return "yellow";
}

function alertTone(status: string): "error" | "yellow" | "muted" | "default" {
  if (status === "FIRING") return "error";
  if (status === "RESOLVED") return "muted";
  if (status === "ACKNOWLEDGED") return "yellow";
  return "default";
}

function CapRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="font-mono text-sm text-on-surface">{value}</span>
    </div>
  );
}

export function OperationsIntelligence({
  alerts,
  fatigue,
  onAlertsChanged,
}: {
  alerts: ObservabilityAlertsResponse | null;
  fatigue: AlertFatigueReport | null;
  onAlertsChanged: () => void;
}) {
  const pushToast = useToastStore((s) => s.push);

  const [permissions, setPermissions] = useState<string[]>([]);
  const [tab, setTab] = useState<Tab>("incidents");

  const [incidents, setIncidents] = useState<SreIncident[] | null>(null);
  const [incidentsError, setIncidentsError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<SreIncident | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [timeline, setTimeline] = useState<SreIncidentTimeline | null>(null);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [services, setServices] = useState<SreService[] | null>(null);
  const [servicesError, setServicesError] = useState<string | null>(null);
  const [selectedServiceId, setSelectedServiceId] = useState<string | null>(null);
  const [serviceDetail, setServiceDetail] = useState<SreService | null>(null);
  const [serviceDetailError, setServiceDetailError] = useState<string | null>(null);
  const [deps, setDeps] = useState<SreServiceDependencies | null>(null);
  const [depsError, setDepsError] = useState<string | null>(null);

  const [detailLoading, setDetailLoading] = useState(false);

  const [pendingTransition, setPendingTransition] = useState<{
    incidentId: string;
    title: string;
    status: SreIncidentStatus;
    target: string;
    note: string;
  } | null>(null);
  const [pendingResolveAlert, setPendingResolveAlert] = useState<ObservabilityAlert | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const notifyError = useCallback(
    (e: unknown, fallback: string, refetch?: () => void) => {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      if (e instanceof ApiError && e.status === 409) {
        pushToast("info", "State changed on the server; refreshing");
        refetch?.();
        return;
      }
      pushToast("error", e instanceof Error ? e.message : fallback);
    },
    [pushToast],
  );

  const loadIncidents = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    try {
      const response = await api.sreListIncidents(token, { limit: 50 });
      setIncidents(response.items);
      if (response.items.length > 0 && !selectedId) {
        setSelectedId(response.items[0].id);
      }
      setIncidentsError(null);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setIncidentsError(e instanceof Error ? e.message : "Incidents unavailable");
    }
  }, [selectedId]);

  const loadDetailAndTimeline = useCallback(async (incidentId: string) => {
    const token = getToken();
    if (!token) return;
    setDetailLoading(true);
    setDetailError(null);
    setTimelineError(null);
    try {
      const [incidentDetail, incidentTimeline] = await Promise.all([
        api.sreGetIncident(token, incidentId),
        api.sreIncidentTimeline(token, incidentId),
      ]);
      setDetail(incidentDetail);
      setTimeline(incidentTimeline);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setDetailError(e instanceof Error ? e.message : "Incident detail unavailable");
      setTimelineError(e instanceof Error ? e.message : "Timeline unavailable");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadServices = useCallback(async () => {
    const token = getToken();
    if (!token) return;
    setServicesError(null);
    try {
      const response = await api.sreListServices(token, { limit: 100 });
      setServices(response.items);
      if (response.items.length > 0 && !selectedServiceId) {
        setSelectedServiceId(response.items[0].id);
      }
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setServicesError(e instanceof Error ? e.message : "Services unavailable");
    }
  }, [selectedServiceId]);

  const loadServiceDetail = useCallback(async (serviceId: string) => {
    const token = getToken();
    if (!token) return;
    setServiceDetailError(null);
    setDepsError(null);
    try {
      const [service, dependencies] = await Promise.all([
        api.sreGetService(token, serviceId),
        api.sreServiceDependencies(token, serviceId),
      ]);
      setServiceDetail(service);
      setDeps(dependencies);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setServiceDetailError(e instanceof Error ? e.message : "Service detail unavailable");
      setDepsError(e instanceof Error ? e.message : "Dependencies unavailable");
    }
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let active = true;
    api
      .whoami(token)
      .then((whoami) => {
        if (active) setPermissions(whoami.permissions ?? []);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
        }
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    void Promise.all([loadIncidents(), loadServices()]);
  }, [loadIncidents, loadServices]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setTimeline(null);
      return;
    }
    void loadDetailAndTimeline(selectedId);
  }, [selectedId, loadDetailAndTimeline]);

  useEffect(() => {
    if (!selectedServiceId) {
      setServiceDetail(null);
      setDeps(null);
      return;
    }
    void loadServiceDetail(selectedServiceId);
  }, [selectedServiceId, loadServiceDetail]);

  useEffect(() => {
    const resetForContextSwitch = () => {
      setIncidents(null);
      setServices(null);
      setDetail(null);
      setTimeline(null);
      setServiceDetail(null);
      setDeps(null);
      setSelectedId(null);
      setSelectedServiceId(null);
      void Promise.all([loadIncidents(), loadServices()]);
    };
    window.addEventListener("tenant:switched", resetForContextSwitch as EventListener);
    window.addEventListener("workspace:switched", resetForContextSwitch as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", resetForContextSwitch as EventListener);
      window.removeEventListener("workspace:switched", resetForContextSwitch as EventListener);
    };
  }, [loadIncidents, loadServices]);

  const canOperate = hasPermission(permissions, PERMISSIONS.opsAdmin);

  async function handleAcknowledgeAlert(alert: ObservabilityAlert) {
    const token = getToken();
    if (!token) return;
    try {
      await api.acknowledgeAlert(token, alert.id);
      pushToast("success", `Alert ${alert.id} acknowledged`);
      onAlertsChanged();
    } catch (e) {
      notifyError(e, "Failed to acknowledge alert", onAlertsChanged);
    }
  }

  async function handleResolveAlert() {
    if (!pendingResolveAlert) return;
    const alert = pendingResolveAlert;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.resolveAlert(token, alert.id);
      setPendingResolveAlert(null);
      pushToast("success", `Alert ${alert.id} resolved`);
      onAlertsChanged();
    } catch (e) {
      notifyError(e, "Failed to resolve alert", onAlertsChanged);
    } finally {
      setSubmitting(false);
    }
  }

  async function handleTransition() {
    if (!pendingTransition) return;
    const { incidentId, status, target, note } = pendingTransition;
    if (!INCIDENT_TRANSITIONS[status]?.includes(target as SreIncidentStatus)) return;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      const updated = await api.incidentTransition(token, incidentId, { target, note });
      setPendingTransition(null);
      pushToast("success", `Incident moved to ${target}`);
      setIncidents((prev) =>
        prev ? prev.map((incident) => (incident.id === incidentId ? updated : incident)) : prev,
      );
      if (selectedId === incidentId) {
        setDetail(updated);
        const timelineResult = await api.sreIncidentTimeline(token, incidentId);
        setTimeline(timelineResult);
      }
    } catch (e) {
      notifyError(e, "Failed to transition incident");
    } finally {
      setSubmitting(false);
    }
  }

  const selectedIncident = detail ?? incidents?.find((incident) => incident.id === selectedId) ?? null;
  const targets = selectedIncident ? INCIDENT_TRANSITIONS[selectedIncident.status] ?? [] : [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap gap-2" aria-label="Operations sections">
          {TABS.map((item) => (
            <BrutalButton
              key={item.id}
              size="sm"
              variant={tab === item.id ? "default" : "ghost"}
              onClick={() => setTab(item.id)}
            >
              {item.label}
            </BrutalButton>
          ))}
        </div>
        {!canOperate ? (
          <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            Read-only view · admin actions hidden
          </span>
        ) : null}
      </div>

      {tab === "incidents" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="SRE" title="Incidents">
            {incidentsError ? (
              <BrutalErrorState title="Unavailable" description={incidentsError} onRetry={() => void loadIncidents()} />
            ) : incidents === null ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <BrutalSkeleton key={index} className="h-8" label="Loading incidents" />
                ))}
              </div>
            ) : incidents.length === 0 ? (
              <BrutalEmptyState title="No incidents" description="Incident records appear here once created." />
            ) : (
              <ul className="space-y-2">
                {incidents.map((incident) => (
                  <li key={incident.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedId(incident.id)}
                      className={
                        selectedId === incident.id
                          ? "w-full border border-primary-container bg-surface p-3 text-left"
                          : "w-full border border-outline bg-surface p-3 text-left hover:border-on-surface"
                      }
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-sm text-on-surface">{incident.title}</span>
                        <BrutalBadge tone={incidentTone(incident.status)}>{incident.status}</BrutalBadge>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-4 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        <span>{incident.incident_id}</span>
                        <span>{incident.severity}</span>
                        <span>{incident.service_id}</span>
                        <span>{formatDate(incident.detected_at)}</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Detail" title={selectedIncident ? "Incident record & audit trail" : "Incident record"}>
            {selectedId === null ? (
              <BrutalEmptyState title="Select an incident" description="Pick an incident to inspect its record and audit trail." />
            ) : detailLoading ? (
              <div className="space-y-2">
                {Array.from({ length: 5 }).map((_, index) => (
                  <BrutalSkeleton key={index} className="h-8" label="Loading incident detail" />
                ))}
              </div>
            ) : detailError ? (
              <BrutalErrorState title="Unavailable" description={detailError} onRetry={() => selectedId && void loadDetailAndTimeline(selectedId)} />
            ) : selectedIncident ? (
              <div className="space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <BrutalBadge tone={incidentTone(selectedIncident.status)}>{selectedIncident.status}</BrutalBadge>
                  <BrutalBadge tone="muted">{selectedIncident.severity}</BrutalBadge>
                  {canOperate && targets.length > 0 ? (
                    <BrutalButton
                      size="sm"
                      variant="yellow"
                      onClick={() =>
                        setPendingTransition({
                          incidentId: selectedIncident.id,
                          title: selectedIncident.title,
                          status: selectedIncident.status,
                          target: targets[0],
                          note: "",
                        })
                      }
                    >
                      Advance status
                    </BrutalButton>
                  ) : null}
                </div>
                <div className="space-y-1">
                  <CapRow label="Incident" value={selectedIncident.incident_id} />
                  <CapRow label="Service" value={selectedIncident.service_id} />
                  <CapRow label="Region" value={selectedIncident.region} />
                  <CapRow label="Commander" value={selectedIncident.commander} />
                  <CapRow label="Detected" value={formatDate(selectedIncident.detected_at)} />
                  <CapRow label="Mitigated" value={formatDate(selectedIncident.mitigated_at)} />
                  <CapRow label="Resolved" value={formatDate(selectedIncident.resolved_at)} />
                  <CapRow label="Closed" value={formatDate(selectedIncident.closed_at)} />
                  <CapRow label="Related alerts" value={selectedIncident.related_alerts.length > 0 ? String(selectedIncident.related_alerts.length) : "—"} />
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Root cause</p>
                  <p className="mt-1 text-sm text-on-surface">{selectedIncident.root_cause || "—"}</p>
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Detection</p>
                  <p className="mt-1 text-sm text-on-surface">{selectedIncident.detection || "—"}</p>
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Audit trail</p>
                  {timelineError ? (
                    <p className="mt-2 text-sm text-error">{timelineError}</p>
                  ) : timeline && timeline.events.length > 0 ? (
                    <ol className="mt-2 space-y-2">
                      {timeline.events.map((event, index) => (
                        <li key={index} className="border border-outline bg-surface p-3">
                          <div className="flex flex-wrap items-baseline justify-between gap-2">
                            <span className="font-mono text-[11px] uppercase tracking-widest text-on-surface">{event.event_type}</span>
                            <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{formatDate(event.occurred_at)}</span>
                          </div>
                          <p className="mt-1 text-sm text-on-surface-variant">{event.message}</p>
                          <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Actor: {event.actor}</p>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">No timeline events recorded.</p>
                  )}
                </div>
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {tab === "services" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Catalog" title="Services">
            {servicesError ? (
              <BrutalErrorState title="Unavailable" description={servicesError} onRetry={() => void loadServices()} />
            ) : services === null ? (
              <div className="space-y-2">
                {Array.from({ length: 4 }).map((_, index) => (
                  <BrutalSkeleton key={index} className="h-8" label="Loading services" />
                ))}
              </div>
            ) : services.length === 0 ? (
              <BrutalEmptyState title="No services registered" description="Register services in the SRE service catalog first." />
            ) : (
              <ul className="space-y-2">
                {services.map((service) => (
                  <li key={service.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedServiceId(service.id)}
                      className={
                        selectedServiceId === service.id
                          ? "w-full border border-primary-container bg-surface p-3 text-left"
                          : "w-full border border-outline bg-surface p-3 text-left hover:border-on-surface"
                      }
                    >
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="truncate text-sm text-on-surface">{service.name}</span>
                        <BrutalBadge tone={service.status === "operational" ? "yellow" : service.status === "major_outage" ? "error" : "default"}>
                          {service.status}
                        </BrutalBadge>
                      </div>
                      <div className="mt-1 flex flex-wrap gap-x-4 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        <span>{service.service_id}</span>
                        <span>{service.tier}</span>
                        <span>{service.team}</span>
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Detail" title="Service record & dependencies">
            {selectedServiceId === null ? (
              <BrutalEmptyState title="Select a service" description="Pick a service to inspect its record and dependencies." />
            ) : serviceDetailError ? (
              <BrutalErrorState title="Unavailable" description={serviceDetailError} onRetry={() => selectedServiceId && void loadServiceDetail(selectedServiceId)} />
            ) : serviceDetail ? (
              <div className="space-y-4">
                <div className="space-y-1">
                  <CapRow label="Service" value={serviceDetail.service_id} />
                  <CapRow label="Owner" value={serviceDetail.owner || "—"} />
                  <CapRow label="Team" value={serviceDetail.team || "—"} />
                  <CapRow label="Tier" value={serviceDetail.tier || "—"} />
                  <CapRow label="Criticality" value={serviceDetail.criticality || "—"} />
                  <CapRow label="RTO" value={formatDurationMinutes(serviceDetail.rto_minutes)} />
                  <CapRow label="RPO" value={formatDurationMinutes(serviceDetail.rpo_minutes)} />
                  <CapRow label="On-call" value={serviceDetail.on_call || "—"} />
                  <CapRow label="Deployment" value={serviceDetail.deployment_strategy || "—"} />
                  <CapRow label="Scaling" value={serviceDetail.scaling_strategy || "—"} />
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Description</p>
                  <p className="mt-1 text-sm text-on-surface">{serviceDetail.description || "—"}</p>
                </div>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Dependencies</p>
                  {depsError ? (
                    <p className="mt-2 text-sm text-error">{depsError}</p>
                  ) : deps && deps.dependencies.length > 0 ? (
                    <ul className="mt-2 space-y-2">
                      {deps.dependencies.map((dependency) => (
                        <li key={dependency.depends_on} className="flex items-baseline justify-between gap-3 border border-outline bg-surface p-3">
                          <div className="min-w-0">
                            <p className="truncate font-mono text-sm text-on-surface">{dependency.depends_on}</p>
                            <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{dependency.kind}</p>
                          </div>
                          <BrutalBadge tone={dependency.critical ? "error" : "muted"}>
                            {dependency.critical ? "CRITICAL" : "OPTIONAL"}
                          </BrutalBadge>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">No dependencies recorded.</p>
                  )}
                </div>
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {tab === "fatigue" ? (
        <BrutalCard eyebrow="Noise" title="Alert fatigue signal detail">
          <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            Fatigue is measured over the platform window and reflects real alert volume.
          </p>
          <div className="mt-4 space-y-1">
            <CapRow label="Alerts in window" value={fatigue ? String(fatigue.total) : String(alerts?.items.length ?? 0)} />
            <CapRow label="Live FIRING" value={String(alerts?.items.filter((alert) => alert.status === "FIRING").length ?? 0)} />
            <CapRow label="Live ACKNOWLEDGED" value={String(alerts?.items.filter((alert) => alert.status === "ACKNOWLEDGED").length ?? 0)} />
          </div>
          <div className="mt-4 space-y-4">
            {fatigue ? (
              <>
                <div>
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Duplicate noise</p>
                  {Object.keys(fatigue.duplicates ?? {}).length > 0 ? (
                    <ul className="mt-2 space-y-1">
                      {Object.entries(fatigue.duplicates ?? {}).map(([fingerprint, count]) => (
                        <li key={fingerprint} className="flex items-baseline justify-between gap-3 border border-outline bg-surface p-3">
                          <span className="truncate font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{fingerprint}</span>
                          <span className="font-mono text-sm text-on-surface">{String(count)}×</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">No duplicate fingerprints.</p>
                  )}
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">High frequency</p>
                    {fatigue.high_frequency && fatigue.high_frequency.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {fatigue.high_frequency.map((fingerprint) => (
                          <li key={fingerprint} className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                            {fingerprint}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">None.</p>
                    )}
                  </div>
                  <div>
                    <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Flapping</p>
                    {fatigue.flapping && fatigue.flapping.length > 0 ? (
                      <ul className="mt-2 space-y-1">
                        {fatigue.flapping.map((fingerprint) => (
                          <li key={fingerprint} className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                            {fingerprint}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">None.</p>
                    )}
                  </div>
                </div>
                {fatigue.recommendations && fatigue.recommendations.length > 0 ? (
                  <div>
                    <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Recommendations</p>
                    <ul className="mt-2 space-y-1">
                      {fatigue.recommendations.map((recommendation, index) => (
                        <li key={index} className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                          {recommendation.type.toUpperCase()} {recommendation.action ? `· ${recommendation.action.toUpperCase()}` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </>
            ) : null}
            {alerts && alerts.items.length > 0 ? (
              <div>
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Live alerts</p>
                <ul className="mt-2 space-y-2">
                  {alerts.items.map((alert) => (
                    <li key={alert.id} className="flex flex-wrap items-baseline justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{alert.resource}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          {alert.severity} · {alert.fingerprint}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone={alertTone(alert.status)}>{alert.status}</BrutalBadge>
                        {canOperate && (alert.status === "FIRING" || alert.status === "SUPPRESSED") ? (
                          <BrutalButton size="sm" variant="ghost" onClick={() => void handleAcknowledgeAlert(alert)}>
                            Ack
                          </BrutalButton>
                        ) : null}
                        {canOperate && alert.status !== "RESOLVED" ? (
                          <BrutalButton size="sm" variant="ghost" onClick={() => setPendingResolveAlert(alert)}>
                            Resolve
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <div className="mt-4">
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Live alerts</p>
                <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">No alerts loaded.</p>
              </div>
            )}
          </div>
        </BrutalCard>
      ) : null}

      {tab === "handoff" ? (
        <BrutalCard eyebrow="Operations → AI" title="AI handoff">
          <p className="text-sm text-on-surface-variant">
            Hand the current operational context to the AI workspace. The handoff prompt includes the live
            alert volume and, when selected, the active incident record — the AI agent can then recommend next
            steps in the controlled AI workspace.
          </p>
          <ul className="mt-4 space-y-2">
            {alerts && alerts.items.length > 0 ? (
              <li className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                {String(alerts.items.length)} live alerts · {String(alerts.items.filter((alert) => alert.status === "FIRING").length)} firing
              </li>
            ) : null}
            {selectedIncident ? (
              <li className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                {selectedIncident.incident_id} · {selectedIncident.status} · {selectedIncident.severity}
              </li>
            ) : null}
          </ul>
          <BrutalButton href="/ai" variant="yellow" className="mt-4">
            Open AI workspace
          </BrutalButton>
        </BrutalCard>
      ) : null}

      <BrutalModal
        open={pendingTransition !== null}
        title="Transition incident?"
        onClose={() => {
          if (!submitting) setPendingTransition(null);
        }}
        actions={
          <>
            <BrutalButton variant="default" disabled={submitting} onClick={() => setPendingTransition(null)}>
              Cancel
            </BrutalButton>
            <BrutalButton variant="yellow" disabled={submitting} onClick={() => void handleTransition()}>
              {submitting ? "Transitioning…" : "Confirm transition"}
            </BrutalButton>
          </>
        }
      >
        {pendingTransition ? (
          <div className="space-y-4">
            <p className="text-sm text-on-surface-variant">
              <span className="font-bold text-on-surface">{pendingTransition.title}</span> is currently{" "}
              <span className="font-mono uppercase">{pendingTransition.status}</span>. Moving it to{" "}
              <span className="font-mono uppercase">{pendingTransition.target}</span> appends an audit event.
            </p>
            <BrutalSelect
              label="Target status"
              aria-label="Target status"
              value={pendingTransition.target}
              onChange={(event) =>
                setPendingTransition((prev) =>
                  prev ? { ...prev, target: event.target.value } : prev,
                )
              }
              options={targets.map((target) => ({ value: target, label: target }))}
            />
            <div>
              <label htmlFor="transition-note" className="mb-2 block font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Note
              </label>
              <textarea
                id="transition-note"
                rows={2}
                value={pendingTransition.note}
                onChange={(event) =>
                  setPendingTransition((prev) =>
                    prev ? { ...prev, note: event.target.value } : prev,
                  )
                }
                className="w-full border border-outline bg-surface px-3 py-2 text-sm text-on-surface outline-none focus:border-primary-container"
                placeholder="Optional context for the audit trail"
              />
            </div>
          </div>
        ) : null}
      </BrutalModal>

      <BrutalModal
        open={pendingResolveAlert !== null}
        title="Resolve alert?"
        onClose={() => {
          if (!submitting) setPendingResolveAlert(null);
        }}
        actions={
          <>
            <BrutalButton variant="default" disabled={submitting} onClick={() => setPendingResolveAlert(null)}>
              Cancel
            </BrutalButton>
            <BrutalButton variant="yellow" disabled={submitting} onClick={() => void handleResolveAlert()}>
              {submitting ? "Resolving…" : "Confirm resolve alert"}
            </BrutalButton>
          </>
        }
      >
        {pendingResolveAlert ? (
          <p className="text-sm text-on-surface-variant">
            Mark alert <span className="font-mono text-on-surface">{pendingResolveAlert.id}</span> for{" "}
            <span className="font-mono text-on-surface">{pendingResolveAlert.resource}</span> as resolved. The
            platform remains the source of truth.
          </p>
        ) : null}
      </BrutalModal>
    </div>
  );
}