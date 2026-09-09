"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
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
  AccessRequestItem,
  SecOpsAlert,
  SecOpsDashboard,
  SecOpsEvent,
  SecOpsFinding,
  SecOpsResponseRecord,
  SecOpsRiskSnapshot,
} from "@/types/security";
import { SECOPS_ALERT_STATUSES, SECOPS_FINDING_STATUSES } from "@/types/security";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function severityTone(severity: string | undefined): "error" | "yellow" | "muted" | "default" {
  if (severity === "CRITICAL" || severity === "HIGH") return "error";
  if (severity === "MEDIUM") return "yellow";
  return "default";
}

function alertTone(status: string | undefined): "error" | "yellow" | "muted" | "default" {
  if (status === "OPEN" || status === "INVESTIGATING") return "error";
  if (status === "ACKNOWLEDGED" || status === "CONTAINED") return "yellow";
  if (status === "RESOLVED" || status === "FALSE_POSITIVE") return "muted";
  return "default";
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface">{value}</span>
    </div>
  );
}

/** Renders only primitive values verbatim from the backend payload — never derives metrics. */
function PrimitiveRows({ data }: { data: unknown }) {
  if (!data || typeof data !== "object") {
    return <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No values reported.</p>;
  }
  const entries = Object.entries(data).filter(
    ([key, value]) =>
      !key.startsWith("_") &&
      (typeof value === "string" || typeof value === "number" || typeof value === "boolean") &&
      String(value).trim() !== "",
  );
  if (entries.length === 0) {
    return <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No values reported.</p>;
  }
  return (
    <div>
      {entries.map(([key, value]) => (
        <StatRow key={key} label={key.replace(/_/g, " ")} value={typeof value === "boolean" ? (value ? "yes" : "no") : String(value)} />
      ))}
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

interface PrivilegedAccessRow {
  id: string;
  identity?: string;
  resource?: string;
  status?: string;
  privilege_level?: string;
}

const UNAVAILABLE_CAPABILITIES: UnavailableCapability[] = [
  { key: "realtime", label: "Realtime", reason: "No security SSE subscription endpoint configured" },
  { key: "iam-audit", label: "IAM Audit Log", reason: "IAM audit endpoints are unauthenticated; not consumed here" },
  { key: "blast-radius", label: "Blast Radius", reason: "Requires an explicit case or entity identifier" },
  { key: "simulation", label: "Attack Simulation", reason: "Explicit-action surface (POST only), not a dashboard feed" },
];

type PendingMutation =
  | { kind: "alert-status"; alert: SecOpsAlert }
  | { kind: "finding-status"; finding: SecOpsFinding }
  | { kind: "response"; record: SecOpsResponseRecord; action: "approve" | "execute" | "verify" }
  | { kind: "access-approve"; request: AccessRequestItem }
  | null;

export function SecurityWorkspace() {
  const pushToast = useToastStore((s) => s.push);

  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [dashboard, setDashboard] = useState<SecOpsDashboard | null>(null);
  const [dashboardError, setDashboardError] = useState<string | null>(null);
  const [posture, setPosture] = useState<Record<string, unknown> | null>(null);
  const [postureError, setPostureError] = useState<string | null>(null);
  const [coverage, setCoverage] = useState<Record<string, unknown> | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [slo, setSlo] = useState<Record<string, unknown> | null>(null);
  const [sloError, setSloError] = useState<string | null>(null);
  const [risk, setRisk] = useState<SecOpsRiskSnapshot | null>(null);
  const [riskError, setRiskError] = useState<string | null>(null);

  const [events, setEvents] = useState<SecOpsEvent[] | null>(null);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [eventsCategory, setEventsCategory] = useState("ALL");
  const [eventsSeverity, setEventsSeverity] = useState("ALL");

  const [alerts, setAlerts] = useState<SecOpsAlert[] | null>(null);
  const [alertsError, setAlertsError] = useState<string | null>(null);
  const [alertsStatus, setAlertsStatus] = useState("ALL");
  const [alertsSeverity, setAlertsSeverity] = useState("ALL");

  const [findings, setFindings] = useState<SecOpsFinding[] | null>(null);
  const [findingsError, setFindingsError] = useState<string | null>(null);

  const [responses, setResponses] = useState<SecOpsResponseRecord[] | null>(null);
  const [responsesError, setResponsesError] = useState<string | null>(null);

  const [zeroTrustPosture, setZeroTrustPosture] = useState<Record<string, unknown> | null>(null);
  const [zeroTrustPostureError, setZeroTrustPostureError] = useState<string | null>(null);
  const [privileged, setPrivileged] = useState<PrivilegedAccessRow[] | null>(null);
  const [privilegedError, setPrivilegedError] = useState<string | null>(null);
  const [accessRequests, setAccessRequests] = useState<AccessRequestItem[] | null>(null);
  const [accessRequestsError, setAccessRequestsError] = useState<string | null>(null);

  const [pendingMutation, setPendingMutation] = useState<PendingMutation>(null);
  const [mutationDraft, setMutationDraft] = useState<{ status: string; reason: string }>({
    status: SECOPS_ALERT_STATUSES[0],
    reason: "",
  });
  const [submitting, setSubmitting] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const filtersRef = useRef({ eventsCategory: "ALL", eventsSeverity: "ALL", alertsStatus: "ALL", alertsSeverity: "ALL" });

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
    setPostureError(null);
    setCoverageError(null);
    setSloError(null);
    setRiskError(null);
    setEventsError(null);
    setAlertsError(null);
    setFindingsError(null);
    setResponsesError(null);
    setZeroTrustPostureError(null);
    setPrivilegedError(null);
    setAccessRequestsError(null);

    const filters = filtersRef.current;

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

    async function settle<T>(
      load: () => Promise<T>,
      set: (value: T | null) => void,
      onError: (message: string) => void,
      errorMessage: string,
    ) {
      try {
        const value = await guarded(load);
        if (value !== null && seq === seqRef.current) set(value);
      } catch (e) {
        if (seq !== seqRef.current) return;
        onError(e instanceof Error ? e.message : errorMessage);
      }
    }

    await Promise.all([
      settle(() => api.secOpsDashboard(token), setDashboard, setDashboardError, "Security dashboard unavailable"),
      settle(() => api.secOpsPosture(token), (value) => setPosture(value as Record<string, unknown>), setPostureError, "Posture unavailable"),
      settle(() => api.secOpsCoverage(token), (value) => setCoverage(value as Record<string, unknown>), setCoverageError, "Coverage unavailable"),
      settle(() => api.secOpsSlo(token), (value) => setSlo(value as Record<string, unknown>), setSloError, "SLO unavailable"),
      settle(() => api.secOpsRisk(token), setRisk, setRiskError, "Risk snapshot unavailable"),
      settle(
        () =>
          api.secOpsEvents(token, {
            category: filters.eventsCategory !== "ALL" ? filters.eventsCategory : undefined,
            severity: filters.eventsSeverity !== "ALL" ? filters.eventsSeverity : undefined,
            limit: 50,
          }),
        (value) => setEvents(value?.items ?? null),
        setEventsError,
        "Security events unavailable",
      ),
      settle(
        () =>
          api.secOpsAlerts(token, {
            status: filters.alertsStatus !== "ALL" ? filters.alertsStatus : undefined,
            severity: filters.alertsSeverity !== "ALL" ? filters.alertsSeverity : undefined,
            limit: 50,
          }),
        (value) => setAlerts(value?.items ?? null),
        setAlertsError,
        "Security alerts unavailable",
      ),
      settle(() => api.secOpsFindings(token), (value) => setFindings(value?.items ?? null), setFindingsError, "Findings unavailable"),
      settle(() => api.secOpsResponses(token), (value) => setResponses(value?.items ?? null), setResponsesError, "Responses unavailable"),
      settle(
        () => api.zeroTrustPosture(token),
        (value) => setZeroTrustPosture(value as Record<string, unknown>),
        setZeroTrustPostureError,
        "Zero-trust posture unavailable",
      ),
      settle(
        () => api.zeroTrustPrivilegedAccess(token),
        (value) => setPrivileged(value?.items ?? null),
        setPrivilegedError,
        "Privileged access unavailable",
      ),
      settle(
        () => api.zeroTrustAccessRequests(token),
        (value) => setAccessRequests(value?.items ?? null),
        setAccessRequestsError,
        "Access requests unavailable",
      ),
    ]);

    if (seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
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
    void loadAll();

    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setDashboard(null);
      setPosture(null);
      setCoverage(null);
      setSlo(null);
      setRisk(null);
      setEvents(null);
      setAlerts(null);
      setFindings(null);
      setResponses(null);
      setZeroTrustPosture(null);
      setPrivileged(null);
      setAccessRequests(null);
      setDashboardError(null);
      setPostureError(null);
      setCoverageError(null);
      setSloError(null);
      setRiskError(null);
      setEventsError(null);
      setAlertsError(null);
      setFindingsError(null);
      setResponsesError(null);
      setZeroTrustPostureError(null);
      setPrivilegedError(null);
      setAccessRequestsError(null);
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

  const canSecureWrite = hasPermission(permissions, PERMISSIONS.secOpsWrite);
  const canSecureRead = hasPermission(permissions, PERMISSIONS.secOpsRead) || canSecureWrite;
  const canZeroTrustWrite = hasPermission(permissions, PERMISSIONS.zeroTrustWrite);

  function updateEventsFilter(field: "category" | "severity", value: string) {
    if (field === "category") {
      setEventsCategory(value);
      filtersRef.current.eventsCategory = value;
    } else {
      setEventsSeverity(value);
      filtersRef.current.eventsSeverity = value;
    }
    void loadAll();
  }

  function updateAlertsFilter(field: "status" | "severity", value: string) {
    if (field === "status") {
      setAlertsStatus(value);
      filtersRef.current.alertsStatus = value;
    } else {
      setAlertsSeverity(value);
      filtersRef.current.alertsSeverity = value;
    }
    void loadAll();
  }

  async function handleAlertStatusUpdate() {
    if (!pendingMutation || pendingMutation.kind !== "alert-status") return;
    const alert = pendingMutation.alert;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.secOpsUpdateAlertStatus(token, alert.id, mutationDraft.status, mutationDraft.reason.trim() || undefined);
      setPendingMutation(null);
      pushToast("success", `Alert ${alert.id.slice(0, 8)} → ${mutationDraft.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update alert status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleFindingStatusUpdate() {
    if (!pendingMutation || pendingMutation.kind !== "finding-status") return;
    const finding = pendingMutation.finding;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.secOpsUpdateFindingStatus(token, finding.id, mutationDraft.status);
      setPendingMutation(null);
      pushToast("success", `Finding ${finding.id.slice(0, 8)} → ${mutationDraft.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update finding status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResponseAction() {
    if (!pendingMutation || pendingMutation.kind !== "response") return;
    const { record, action } = pendingMutation;
    const recordId = record.id ?? "";
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      if (action === "approve") {
        await api.secOpsApproveResponse(token, recordId);
        pushToast("success", `Response ${recordId.slice(0, 8)} approved`);
      } else if (action === "execute") {
        await api.secOpsExecuteResponse(token, recordId);
        pushToast("success", `Response ${recordId.slice(0, 8)} executed`);
      } else {
        await api.secOpsVerifyResponse(token, recordId);
        pushToast("success", `Response ${recordId.slice(0, 8)} verified`);
      }
      setPendingMutation(null);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update response", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleAccessApprove() {
    if (!pendingMutation || pendingMutation.kind !== "access-approve") return;
    const request = pendingMutation.request;
    setSubmitting(true);
    const token = getToken();
    try {
      if (!token) {
        sessionExpired();
        return;
      }
      await api.zeroTrustApproveAccessRequest(token, request.id, request.binding_hash);
      setPendingMutation(null);
      pushToast("success", `Access request ${request.id.slice(0, 8)} approved`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to approve access request", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  const modalTitle =
    pendingMutation?.kind === "alert-status"
      ? "Update alert status?"
      : pendingMutation?.kind === "finding-status"
        ? "Update finding status?"
        : pendingMutation?.kind === "response"
          ? pendingMutation.action === "verify"
            ? "Verify response containment?"
            : pendingMutation.action === "approve"
              ? "Approve response?"
              : "Execute response?"
          : "Approve access request?";

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
        <div className="flex items-center gap-2">
          {!canSecureWrite && !canSecureRead && !canZeroTrustWrite ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no secops permissions
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <BrutalCard eyebrow="Signal" title="Security overview">
          <PanelBody
            loading={loading}
            error={dashboardError}
            onRetry={() => void loadAll()}
            emptyTitle="No security signals"
            emptyDescription="Security signals appear here once detection rules fire."
          >
            {dashboard ? (
              <div className="space-y-3">
                <StatRow label="Open alerts" value={String(dashboard.alerts?.total ?? 0)} />
                <StatRow label="Findings" value={String(dashboard.findings?.total ?? 0)} />
                <StatRow label="Cases" value={String(dashboard.cases?.total ?? 0)} />
                <StatRow label="Indicators" value={String(dashboard.indicators?.total ?? 0)} />
                {dashboard.alerts?.by_severity ? (
                  <div className="border-t border-outline pt-2">
                    <PrimitiveRows data={dashboard.alerts.by_severity} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Risk" title="Current posture & coverage">
          <PanelBody
            loading={loading}
            error={riskError || postureError}
            onRetry={() => void loadAll()}
            emptyTitle="No posture reported"
            emptyDescription="Posture becomes available once risk snapshots are calculated."
          >
            {risk ? (
              <div className="space-y-3">
                <StatRow label="Risk score" value={String(risk.risk_score ?? 0)} />
                <StatRow label="Severity" value={risk.severity ? risk.severity.toUpperCase() : "—"} />
                <StatRow label="Calculated" value={formatDateTime(risk.calculated_at)} />
              </div>
            ) : (
              <div className="space-y-3">
                <StatRow label="Risk score" value="—" />
                <StatRow label="Severity" value="—" />
                <StatRow label="Calculated" value="—" />
              </div>
            )}
            {posture ? (
              <div className="border-t border-outline pt-2">
                <p className="mb-1 font-mono text-xs uppercase tracking-widest text-primary-container">Posture indicators</p>
                {posture.indicators !== undefined && posture.indicators !== null ? (
                  <PrimitiveRows data={posture.indicators} />
                ) : (
                  <PrimitiveRows data={posture} />
                )}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Ops" title="Coverage & SLO">
          <PanelBody
            loading={loading}
            error={coverageError || sloError}
            onRetry={() => void loadAll()}
            emptyTitle="No coverage data"
            emptyDescription="Coverage and SLO are computed from the posture engine."
          >
            {coverage || slo ? (
              <div className="space-y-3">
                {coverage ? (
                  <div>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Coverage</p>
                    {coverage.asset_coverage !== undefined && coverage.asset_coverage !== null ? (
                      <div className="mb-1">
                        <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Asset coverage</p>
                        <PrimitiveRows data={coverage.asset_coverage} />
                      </div>
                    ) : null}
                    <PrimitiveRows data={coverage} />
                  </div>
                ) : null}
                {slo ? (
                  <div>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">SLO</p>
                    {slo.observed !== undefined && slo.observed !== null ? (
                      <div className="mb-1">
                        <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Observed</p>
                        <PrimitiveRows data={slo.observed} />
                      </div>
                    ) : null}
                    {slo.slo_targets !== undefined && slo.slo_targets !== null ? (
                      <div className="mb-1">
                        <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Targets</p>
                        <PrimitiveRows data={slo.slo_targets} />
                      </div>
                    ) : null}
                    <PrimitiveRows data={slo} />
                  </div>
                ) : null}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="Zero trust" title="Identity · access · machine posture">
          <PanelBody
            loading={loading}
            error={zeroTrustPostureError}
            onRetry={() => void loadAll()}
            emptyTitle="No zero-trust posture"
            emptyDescription="Zero-trust posture signals appear here once evaluated."
          >
            {zeroTrustPosture ? (
              <div className="space-y-4">
                {Object.entries(zeroTrustPosture).map(([section, value]) => (
                  <div key={section}>
                    <p className="mb-1 font-mono text-xs uppercase tracking-widest text-primary-container">
                      {section.replace(/_/g, " ")}
                    </p>
                    <PrimitiveRows data={value ?? {}} />
                  </div>
                ))}
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="JIT" title="Privileged access & requests">
          <div className="space-y-5">
            <div>
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Privileged sessions</p>
              <PanelBody
                loading={loading}
                error={privilegedError}
                onRetry={() => void loadAll()}
                emptyTitle="No privileged access"
                emptyDescription="High-clearance privileged sessions appear here once granted."
              >
                {privileged && privileged.length > 0 ? (
                  <ul className="space-y-2">
                    {privileged.map((item) => (
                      <li key={item.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{item.identity ?? item.id}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {item.resource ?? "—"} · {item.privilege_level ?? "—"}
                          </p>
                        </div>
                        <BrutalBadge tone={item.status === "ACTIVE" ? "yellow" : "default"}>{item.status ?? "UNKNOWN"}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </div>
            <div>
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Access requests</p>
              <PanelBody
                loading={loading}
                error={accessRequestsError}
                onRetry={() => void loadAll()}
                emptyTitle="No access requests"
                emptyDescription="Just-in-time access requests appear here once raised."
              >
                {accessRequests && accessRequests.length > 0 ? (
                  <ul className="space-y-2">
                    {accessRequests.map((request) => (
                      <li key={request.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                        <div className="min-w-0">
                          <p className="truncate text-sm text-on-surface">{request.identity ?? request.id}</p>
                          <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                            {request.resource ?? "—"} · {request.action ?? "—"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2">
                          <BrutalBadge tone={request.status === "APPROVED" ? "yellow" : request.status === "DENIED" ? "error" : "default"}>
                            {request.status ?? "UNKNOWN"}
                          </BrutalBadge>
                          {canZeroTrustWrite && request.status !== "APPROVED" ? (
                            <BrutalButton size="sm" variant="ghost" onClick={() => setPendingMutation({ kind: "access-approve", request })}>
                              Approve
                            </BrutalButton>
                          ) : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </PanelBody>
            </div>
          </div>
        </BrutalCard>
      </div>

      <BrutalCard
        eyebrow="Activity"
        title="Security events · audit trail"
        actions={
          <div className="flex gap-2">
            <BrutalSelect
              aria-label="Event category filter"
              value={eventsCategory}
              onChange={(event) => updateEventsFilter("category", event.target.value)}
              options={[
                { value: "ALL", label: "All categories" },
                { value: "AUTH", label: "AUTH" },
                { value: "APPLICATION", label: "APPLICATION" },
                { value: "NETWORK", label: "NETWORK" },
                { value: "DATA", label: "DATA" },
                { value: "THREAT", label: "THREAT" },
              ]}
            />
            <BrutalSelect
              aria-label="Event severity filter"
              value={eventsSeverity}
              onChange={(event) => updateEventsFilter("severity", event.target.value)}
              options={[
                { value: "ALL", label: "All severities" },
                { value: "INFO", label: "INFO" },
                { value: "LOW", label: "LOW" },
                { value: "MEDIUM", label: "MEDIUM" },
                { value: "HIGH", label: "HIGH" },
                { value: "CRITICAL", label: "CRITICAL" },
              ]}
            />
          </div>
        }
      >
        <PanelBody
          loading={loading}
          error={eventsError}
          onRetry={() => void loadAll()}
          emptyTitle="No security events"
          emptyDescription="Events appear here once ingested by the security pipeline."
        >
          {events && events.length > 0 ? (
            <ul className="space-y-2">
              {events.map((event) => (
                <li key={event.event_id} className="flex flex-wrap items-baseline justify-between gap-3 border border-outline bg-surface p-3">
                  <div className="min-w-0">
                    <p className="truncate font-mono text-sm text-on-surface">{event.event_id}</p>
                    <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {event.source ?? "—"} · {event.category ?? "—"} · {event.action ?? "—"}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                      {event.actor ? `actor ${event.actor}` : ""}
                    </span>
                    <BrutalBadge tone={severityTone(event.severity)}>{event.severity ?? "INFO"}</BrutalBadge>
                    <span className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{formatDateTime(event.created_at)}</span>
                  </div>
                </li>
              ))}
            </ul>
          ) : null}
        </PanelBody>
      </BrutalCard>

      <div className="grid gap-6 lg:grid-cols-2">
        <BrutalCard eyebrow="Detections" title="Security alerts">
          <PanelBody
            loading={loading}
            error={alertsError}
            onRetry={() => void loadAll()}
            emptyTitle="No security alerts"
            emptyDescription="Alerts fire from detection rules once events are ingested."
          >
            {alerts && alerts.length > 0 ? (
              <div className="space-y-3">
                <div className="flex gap-2">
                  <BrutalSelect
                    aria-label="Alert status filter"
                    value={alertsStatus}
                    onChange={(event) => updateAlertsFilter("status", event.target.value)}
                    options={[
                      { value: "ALL", label: "All statuses" },
                      { value: "OPEN", label: "OPEN" },
                      { value: "ACKNOWLEDGED", label: "ACKNOWLEDGED" },
                      { value: "INVESTIGATING", label: "INVESTIGATING" },
                      { value: "CONTAINED", label: "CONTAINED" },
                      { value: "RESOLVED", label: "RESOLVED" },
                      { value: "FALSE_POSITIVE", label: "FALSE_POSITIVE" },
                    ]}
                  />
                  <BrutalSelect
                    aria-label="Alert severity filter"
                    value={alertsSeverity}
                    onChange={(event) => updateAlertsFilter("severity", event.target.value)}
                    options={[
                      { value: "ALL", label: "All severities" },
                      { value: "INFO", label: "INFO" },
                      { value: "LOW", label: "LOW" },
                      { value: "MEDIUM", label: "MEDIUM" },
                      { value: "HIGH", label: "HIGH" },
                      { value: "CRITICAL", label: "CRITICAL" },
                    ]}
                  />
                </div>
                <ul className="space-y-2">
                  {alerts.map((alert) => (
                    <li key={alert.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm text-on-surface">{alert.rule_name || alert.id}</p>
                        <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                          {alert.severity ?? "—"} · {alert.confidence !== undefined ? `confidence ${alert.confidence}` : ""}
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <BrutalBadge tone={alertTone(alert.status)}>{alert.status ?? "UNKNOWN"}</BrutalBadge>
                        {canSecureWrite ? (
                          <BrutalButton
                            size="sm"
                            variant="ghost"
                            onClick={() => {
                              setMutationDraft({
                                status: alert.status === "ACKNOWLEDGED" ? "RESOLVED" : "ACKNOWLEDGED",
                                reason: "",
                              });
                              setPendingMutation({ kind: "alert-status", alert });
                            }}
                          >
                            Update
                          </BrutalButton>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </PanelBody>
        </BrutalCard>

        <BrutalCard eyebrow="Findings" title="Security findings">
          <PanelBody
            loading={loading}
            error={findingsError}
            onRetry={() => void loadAll()}
            emptyTitle="No findings"
            emptyDescription="Findings appear here once policy or detection surfaces report them."
          >
            {findings && findings.length > 0 ? (
              <ul className="space-y-2">
                {findings.map((finding) => (
                  <li key={finding.id} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{finding.finding || finding.id}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {finding.resource ?? "—"} · {finding.severity ?? "—"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <BrutalBadge tone={alertTone(finding.status)}>{finding.status ?? "UNKNOWN"}</BrutalBadge>
                      {canSecureWrite ? (
                        <BrutalButton
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setMutationDraft({ status: SECOPS_FINDING_STATUSES[0], reason: "" });
                            setPendingMutation({ kind: "finding-status", finding });
                          }}
                        >
                          Update
                        </BrutalButton>
                      ) : null}
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </PanelBody>
        </BrutalCard>
      </div>

      <BrutalCard eyebrow="Response" title="Approved response workflow">
        <PanelBody
          loading={loading}
          error={responsesError}
          onRetry={() => void loadAll()}
          emptyTitle="No responses"
          emptyDescription="Responses are created from cases through the approved-response workflow."
        >
          {responses && responses.length > 0 ? (
            <ul className="space-y-2">
              {responses.map((record) => {
                const recordId = record.id ?? "";
                return (
                  <li key={recordId} className="flex flex-wrap items-center justify-between gap-3 border border-outline bg-surface p-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm text-on-surface">{record.action || recordId}</p>
                      <p className="truncate font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                        {record.requested_by ? `requested by ${record.requested_by}` : ""}
                        {record.approved_by ? ` · approved by ${record.approved_by}` : ""}
                      </p>
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <BrutalBadge tone={record.status === "COMPLETED" ? "muted" : record.status === "APPROVED" ? "yellow" : "default"}>
                        {record.status ?? "UNKNOWN"}
                      </BrutalBadge>
                      {canSecureWrite && record.status === "REQUESTED" ? (
                        <BrutalButton size="sm" variant="ghost" onClick={() => setPendingMutation({ kind: "response", record, action: "approve" })}>
                          Approve
                        </BrutalButton>
                      ) : null}
                      {canSecureWrite && record.status === "APPROVED" ? (
                        <BrutalButton size="sm" variant="ghost" onClick={() => setPendingMutation({ kind: "response", record, action: "execute" })}>
                          Execute
                        </BrutalButton>
                      ) : null}
                      {canSecureRead && record.status === "COMPLETED" ? (
                        <BrutalButton size="sm" variant="ghost" onClick={() => setPendingMutation({ kind: "response", record, action: "verify" })}>
                          Verify
                        </BrutalButton>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : null}
        </PanelBody>
      </BrutalCard>

      <BrutalCard eyebrow="Capabilities" title="Unavailable security surfaces">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
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
          These surfaces have no authenticated read endpoint in the current backend. IAM audit endpoints exist but are unauthenticated and are
          never consumed by this workspace.
        </p>
      </BrutalCard>

      <BrutalModal
        open={pendingMutation !== null}
        title={modalTitle}
        onClose={() => {
          if (!submitting) setPendingMutation(null);
        }}
        actions={
          <>
            <BrutalButton variant="default" disabled={submitting} onClick={() => setPendingMutation(null)}>
              Cancel
            </BrutalButton>
            <BrutalButton
              variant="yellow"
              disabled={submitting}
              onClick={() => {
                if (pendingMutation?.kind === "alert-status") void handleAlertStatusUpdate();
                else if (pendingMutation?.kind === "finding-status") void handleFindingStatusUpdate();
                else if (pendingMutation?.kind === "response") void handleResponseAction();
                else if (pendingMutation?.kind === "access-approve") void handleAccessApprove();
              }}
            >
              {submitting ? "Submitting…" : "Confirm"}
            </BrutalButton>
          </>
        }
      >
        {pendingMutation?.kind === "alert-status" ? (
          <div className="space-y-4">
            <p className="text-sm text-on-surface-variant">
              Update alert <span className="font-mono text-on-surface">{pendingMutation.alert.id.slice(0, 8)}</span> (
              {pendingMutation.alert.rule_name || "unnamed rule"}). The platform remains the source of truth.
            </p>
            <BrutalSelect
              label="Target status"
              aria-label="Target status"
              value={mutationDraft.status}
              onChange={(event) => setMutationDraft((prev) => ({ ...prev, status: event.target.value }))}
              options={SECOPS_ALERT_STATUSES.map((status) => ({ value: status, label: status }))}
            />
            <div>
              <label htmlFor="alert-reason" className="mb-2 block font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                Reason
              </label>
              <textarea
                id="alert-reason"
                rows={2}
                value={mutationDraft.reason}
                onChange={(event) => setMutationDraft((prev) => ({ ...prev, reason: event.target.value }))}
                className="w-full border border-outline bg-surface px-3 py-2 text-sm text-on-surface outline-none focus:border-primary-container"
                placeholder="Optional rationale for the audit trail"
              />
            </div>
          </div>
        ) : null}

        {pendingMutation?.kind === "finding-status" ? (
          <div className="space-y-4">
            <p className="text-sm text-on-surface-variant">
              Update finding <span className="font-mono text-on-surface">{pendingMutation.finding.id.slice(0, 8)}</span> (
              {pendingMutation.finding.finding || "unnamed"}). The platform remains the source of truth.
            </p>
            <BrutalSelect
              label="Target status"
              aria-label="Target status"
              value={mutationDraft.status}
              onChange={(event) => setMutationDraft((prev) => ({ ...prev, status: event.target.value }))}
              options={SECOPS_FINDING_STATUSES.map((status) => ({ value: status, label: status }))}
            />
          </div>
        ) : null}

        {pendingMutation?.kind === "response" ? (
          <p className="text-sm text-on-surface-variant">
            {pendingMutation.action === "approve"
              ? "Approve the response for execution. Execution remains a separate explicit step."
              : pendingMutation.action === "execute"
                ? "Execute the approved response through the approved tool mapping. No arbitrary commands are run."
                : "Verify that the executed response contained the incident. Approval requires secops:read."}{" "}
            <span className="font-mono text-on-surface">{pendingMutation.record.action || pendingMutation.record.id}</span> — the platform
            remains the source of truth.
          </p>
        ) : null}

        {pendingMutation?.kind === "access-approve" ? (
          <div className="space-y-3">
            <p className="text-sm text-on-surface-variant">
              Approve just-in-time access for <span className="font-mono text-on-surface">{pendingMutation.request.identity ?? pendingMutation.request.id}</span>{" "}
              to <span className="font-mono text-on-surface">{pendingMutation.request.resource ?? "—"}</span> ({pendingMutation.request.action ?? "—"}).
            </p>
            {pendingMutation.request.binding_hash ? (
              <div className="border border-outline bg-surface p-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                binding hash · {pendingMutation.request.binding_hash}
              </div>
            ) : null}
          </div>
        ) : null}
      </BrutalModal>
    </div>
  );
}