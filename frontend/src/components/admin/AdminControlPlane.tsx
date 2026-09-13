"use client";

/* eslint-disable react-hooks/set-state-in-effect -- initial admin load and tenant/workspace subscription */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalTabs } from "@/components/ui/BrutalTabs";
import type {
  AdminAnalyticsEvent,
  AdminAuditLog,
  AdminFeatureFlag,
  AdminOrganization,
  AdminOverview,
  AdminUser,
  FeatureFlag,
  ZeroTrustReview,
} from "@/types/admin";
import type { ApiUser, ApiKeyOut, SessionOut, WhoAmI } from "@/types/api";
import type { Organization } from "@/types/org";
import type {
  AccessRequestItem,
  PrivilegedAccessItem,
  SecOpsDashboard,
  ZeroTrustPosture,
} from "@/types/security";
import type { GovernancePosture } from "@/types/governance";

function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function shortId(value?: string | null): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

function objectFieldCount(value: unknown): number | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return Object.keys(value).length;
  return null;
}

function Section({
  eyebrow,
  title,
  actions,
  loading,
  error,
  forbidden,
  empty,
  children,
}: {
  eyebrow: string;
  title: string;
  actions?: ReactNode;
  loading: boolean;
  error?: string | null;
  forbidden?: string | null;
  empty?: ReactNode | null;
  children: ReactNode;
}) {
  return (
    <BrutalCard eyebrow={eyebrow} title={title} actions={actions}>
      {loading ? <BrutalSkeleton className="h-32" label={`Loading ${title}`} /> : null}
      {!loading && forbidden ? (
        <BrutalEmptyState title="Admin access required" description={forbidden} />
      ) : null}
      {!loading && !forbidden && error ? <BrutalErrorState description={error} /> : null}
      {!loading && !forbidden && !error && empty ? empty : null}
      {!loading && !forbidden && !error && !empty ? children : null}
    </BrutalCard>
  );
}

export function AdminControlPlane() {
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);
  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState<string | null>(null);
  const [globalForbidden, setGlobalForbidden] = useState(false);
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [globalOrgs, setGlobalOrgs] = useState<AdminOrganization[]>([]);
  const [globalOrgsError, setGlobalOrgsError] = useState<string | null>(null);
  const [globalUsers, setGlobalUsers] = useState<AdminUser[]>([]);
  const [globalUsersError, setGlobalUsersError] = useState<string | null>(null);
  const [auditLogs, setAuditLogs] = useState<AdminAuditLog[]>([]);
  const [auditError, setAuditError] = useState<string | null>(null);
  const [platformEvents, setPlatformEvents] = useState<AdminAnalyticsEvent[]>([]);
  const [eventsError, setEventsError] = useState<string | null>(null);
  const [globalFlags, setGlobalFlags] = useState<AdminFeatureFlag[]>([]);
  const [globalFlagsError, setGlobalFlagsError] = useState<string | null>(null);

  const [me, setMe] = useState<ApiUser | null>(null);
  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
  const [myOrgs, setMyOrgs] = useState<Organization[]>([]);
  const [scopeError, setScopeError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [sessionsError, setSessionsError] = useState<string | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyOut[]>([]);
  const [apiKeysError, setApiKeysError] = useState<string | null>(null);
  const [tenantFlags, setTenantFlags] = useState<FeatureFlag[]>([]);
  const [tenantFlagsError, setTenantFlagsError] = useState<string | null>(null);
  const [zeroTrustPosture, setZeroTrustPosture] = useState<ZeroTrustPosture | null>(null);
  const [zeroTrustError, setZeroTrustError] = useState<string | null>(null);
  const [privilegedAccess, setPrivilegedAccess] = useState<PrivilegedAccessItem[]>([]);
  const [privilegedError, setPrivilegedError] = useState<string | null>(null);
  const [accessRequests, setAccessRequests] = useState<AccessRequestItem[]>([]);
  const [accessRequestsError, setAccessRequestsError] = useState<string | null>(null);
  const [reviews, setReviews] = useState<ZeroTrustReview[]>([]);
  const [reviewsError, setReviewsError] = useState<string | null>(null);
  const [governancePosture, setGovernancePosture] = useState<GovernancePosture | null>(null);
  const [governanceError, setGovernanceError] = useState<string | null>(null);
  const [secopsDashboard, setSecopsDashboard] = useState<SecOpsDashboard | null>(null);
  const [secopsError, setSecopsError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    { kind: "approve-request"; id: string; label: string } | { kind: "certify-review"; id: string; label: string } | null
  >(null);
  const [confirming, setConfirming] = useState(false);
  const [certifyChecked, setCertifyChecked] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const pushToast = useToastStore((s) => s.push);

  const clearAll = useCallback(() => {
    setGlobalForbidden(false);
    setOverview(null);
    setOverviewError(null);
    setGlobalOrgs([]);
    setGlobalOrgsError(null);
    setGlobalUsers([]);
    setGlobalUsersError(null);
    setAuditLogs([]);
    setAuditError(null);
    setPlatformEvents([]);
    setEventsError(null);
    setGlobalFlags([]);
    setGlobalFlagsError(null);
    setMe(null);
    setWhoami(null);
    setMyOrgs([]);
    setScopeError(null);
    setSessions([]);
    setSessionsError(null);
    setApiKeys([]);
    setApiKeysError(null);
    setTenantFlags([]);
    setTenantFlagsError(null);
    setZeroTrustPosture(null);
    setZeroTrustError(null);
    setPrivilegedAccess([]);
    setPrivilegedError(null);
    setAccessRequests([]);
    setAccessRequestsError(null);
    setReviews([]);
    setReviewsError(null);
    setGovernancePosture(null);
    setGovernanceError(null);
    setSecopsDashboard(null);
    setSecopsError(null);
  }, []);

  const loadAll = useCallback(async () => {
    const token = getToken();
    if (!token) {
      useAuthStore.getState().markExpired();
      window.location.href = "/auth/login";
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    clearAll();
    setLoading(true);

    async function settle<T>(
      load: () => Promise<T>,
      apply: (value: T) => void,
      fail: (message: string) => void,
      onForbidden?: () => void,
    ) {
      try {
        const value = await load();
        if (controller.signal.aborted || seq !== seqRef.current) return;
        apply(value);
      } catch (e) {
        if (controller.signal.aborted || seq !== seqRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          useAuthStore.getState().markExpired();
          window.location.href = "/auth/login";
          return;
        }
        if (e instanceof ApiError && e.kind === "forbidden") {
          if (onForbidden) {
            onForbidden();
            return;
          }
          fail("Access requires additional backend authorization");
          return;
        }
        fail(e instanceof Error ? e.message : "Unavailable");
      }
    }

    await Promise.all([
      settle(() => api.adminOverview(token), setOverview, setOverviewError, () => setGlobalForbidden(true)),
      settle(
        () => api.adminOrganizations(token, 50, 0),
        (value) => setGlobalOrgs(Array.isArray(value) ? value : []),
        setGlobalOrgsError,
        () => setGlobalForbidden(true),
      ),
      settle(
        () => api.adminUsers(token, 50, 0),
        (value) => setGlobalUsers(Array.isArray(value) ? value : []),
        setGlobalUsersError,
        () => setGlobalForbidden(true),
      ),
      settle(
        () => api.adminAuditLog(token, { limit: 100, offset: 0 }),
        (value) => setAuditLogs(Array.isArray(value) ? value : []),
        setAuditError,
        () => setGlobalForbidden(true),
      ),
      settle(
        () => api.adminAnalyticsEvents(token, { limit: 100, offset: 0 }),
        (value) => setPlatformEvents(Array.isArray(value) ? value : []),
        setEventsError,
        () => setGlobalForbidden(true),
      ),
      settle(
        () => api.adminFeatureFlags(token),
        (value) => setGlobalFlags(Array.isArray(value) ? value : []),
        setGlobalFlagsError,
        () => setGlobalForbidden(true),
      ),
      settle(() => api.me(token), setMe, setScopeError),
      settle(() => api.whoami(token), setWhoami, setScopeError),
      settle(
        () => api.listMyOrganizations(token),
        (value) => setMyOrgs(Array.isArray(value) ? value : []),
        setScopeError,
      ),
      settle(
        () => api.listSessions(token),
        (value) => setSessions(Array.isArray(value) ? value : []),
        setSessionsError,
      ),
      settle(
        () => api.listApiKeys(token),
        (value) => setApiKeys(Array.isArray(value) ? value : []),
        setApiKeysError,
      ),
      settle(
        () => api.featureFlags(token, organizationId ?? undefined),
        (value) => setTenantFlags(Array.isArray(value) ? value : []),
        setTenantFlagsError,
      ),
      settle(() => api.zeroTrustPosture(token), setZeroTrustPosture, setZeroTrustError),
      settle(
        () => api.zeroTrustPrivilegedAccess(token, { limit: 20 }),
        (value) => setPrivilegedAccess(Array.isArray(value?.items) ? value.items : []),
        setPrivilegedError,
      ),
      settle(
        () => api.zeroTrustAccessRequests(token, { limit: 20 }),
        (value) => setAccessRequests(Array.isArray(value?.items) ? value.items : []),
        setAccessRequestsError,
      ),
      settle(
        () => api.zeroTrustReviews(token, { limit: 20 }),
        (value) => setReviews(Array.isArray(value?.items) ? value.items : []),
        setReviewsError,
      ),
      settle(() => api.governancePosture(token, { scope_type: "tenant" }), setGovernancePosture, setGovernanceError),
      settle(() => api.secOpsDashboard(token), setSecopsDashboard, setSecopsError),
    ]);

    if (controller.signal.aborted || seq !== seqRef.current) return;
    setRefreshedAt(new Date().toLocaleString());
    setLoading(false);
  }, [clearAll, organizationId]);

  useEffect(() => {
    void loadAll();
    const handler = () => void loadAll();
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [loadAll]);

  const canZeroTrustWrite = hasPermission(whoami?.permissions ?? [], PERMISSIONS.zeroTrustWrite);

  function openApproveRequest(row: AccessRequestItem) {
    setActionError(null);
    setCertifyChecked(false);
    setPendingAction({ kind: "approve-request", id: row.id, label: `${row.identity ?? row.id} · ${row.action ?? "access"}` });
  }

  function openCertifyReview(row: ZeroTrustReview) {
    setActionError(null);
    setCertifyChecked(false);
    setPendingAction({ kind: "certify-review", id: row.id, label: `${row.review_type ?? "review"} · ${row.scope ?? "all"}` });
  }

  function sessionExpired() {
    useAuthStore.getState().markExpired();
    window.location.href = "/auth/login";
  }

  async function runPendingAction() {
    if (!pendingAction) return;
    if (pendingAction.kind === "certify-review" && !certifyChecked) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setConfirming(true);
    setActionError(null);
    try {
      if (pendingAction.kind === "approve-request") {
        await api.zeroTrustApproveAccessRequest(token, pendingAction.id);
        pushToast("success", "Access request approved and activated");
      } else {
        await api.zeroTrustCertifyReview(token, pendingAction.id);
        pushToast("success", "Access review certified");
      }
      setPendingAction(null);
      setCertifyChecked(false);
      await loadAll();
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setPendingAction(null);
        setCertifyChecked(false);
        pushToast("warning", "Target no longer exists — the list was refreshed from the backend.");
        await loadAll();
        return;
      }
      if (e instanceof ApiError && e.status === 409) {
        setPendingAction(null);
        setCertifyChecked(false);
        pushToast("warning", "Conflicting state — the list was refreshed from the backend.");
        await loadAll();
        return;
      }
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        setActionError("Backend denied this action: zero_trust:write authorization is required.");
        return;
      }
      setActionError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setConfirming(false);
    }
  }

  const timeline = [...auditLogs.map((log) => ({
    id: `audit-${log.id}`,
    at: log.created_at,
    title: log.action,
    detail: `${log.resource_type ?? "event"} ${log.resource_id ?? ""} · ${log.ip_address ?? "no IP"}`.trim(),
  })), ...platformEvents.map((event) => ({
    id: `event-${event.id}`,
    at: event.created_at,
    title: event.event_name ?? event.event_type ?? "platform event",
    detail: `type ${event.event_type ?? "—"}`,
  }))].sort((a, b) => Date.parse(b.at) - Date.parse(a.at)).slice(0, 50);

  const selectedOrg = myOrgs.find((org) => org.id === organizationId) ?? null;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4 border border-outline bg-surface-container px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant" aria-live="polite">
            <span className="h-2 w-2 bg-muted" aria-hidden="true" />
            Realtime: UNAVAILABLE
          </span>
          <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
            {refreshedAt ? `Refreshed ${refreshedAt}` : "Loading control plane…"}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" href="/ai">
            Ask AI about administration
          </BrutalButton>
        </div>
      </div>

      <BrutalTabs
        initialId="overview"
        tabs={[
          {
            id: "overview",
            label: "Overview",
            content: (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section
                  eyebrow="Control plane"
                  title="Global administration"
                  loading={loading}
                  error={overviewError}
                  forbidden={globalForbidden ? "Global administration requires backend superuser authorization." : null}
                  empty={!overview ? <BrutalEmptyState title="No overview" description="No global overview was returned." /> : null}
                >
                  {overview ? (
                    <dl className="grid grid-cols-2 gap-4 text-sm">
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Organizations</dt><dd className="font-mono text-xl text-on-surface">{overview.total_organizations}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Users</dt><dd className="font-mono text-xl text-on-surface">{overview.total_users}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Repositories</dt><dd className="font-mono text-xl text-on-surface">{overview.total_repositories}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Active subscriptions</dt><dd className="font-mono text-xl text-on-surface">{overview.active_subscriptions}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Agent runs</dt><dd className="font-mono text-xl text-on-surface">{overview.total_agent_runs}</dd></div>
                    </dl>
                  ) : null}
                  <p className="mt-4 text-xs text-on-surface-variant">MRR is not exposed by the backend and is omitted.</p>
                </Section>
                <Section
                  eyebrow="Scope"
                  title="Current control scope"
                  loading={loading}
                  error={scopeError}
                  empty={!me && myOrgs.length === 0 ? <BrutalEmptyState title="No scope" description="Select an organization in Settings." /> : null}
                >
                  <dl className="space-y-2 text-sm">
                    <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">User</dt><dd className="text-on-surface">{me?.email ?? whoami?.email ?? "—"}</dd></div>
                    <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">MFA</dt><dd><BrutalBadge tone={whoami?.mfa_enabled ? "yellow" : "muted"}>{whoami?.mfa_enabled ? "Enabled" : "Disabled"}</BrutalBadge></dd></div>
                    <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Organization tenant</dt><dd className="break-all font-mono text-xs text-on-surface">{selectedOrg ? `${selectedOrg.name} · ${selectedOrg.id}` : organizationId ?? "No organization selected"}</dd></div>
                    <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Workspace</dt><dd className="break-all font-mono text-xs text-on-surface">{workspaceId ?? "No workspace selected"}</dd></div>
                    <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Tenant architecture</dt><dd className="text-on-surface-variant">Tenant identity is the selected organization UUID. No independent tenant inventory endpoint exists.</dd></div>
                  </dl>
                  <div className="mt-4 flex flex-wrap gap-2">
                    <BrutalButton variant="ghost" size="sm" href="/settings/organization">Manage organization</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" href="/settings/members">Manage members</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" href="/settings/roles">View roles</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" href="/settings/workspaces">Manage workspaces</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" href="/settings/security">Security controls</BrutalButton>
                  </div>
                </Section>
              </div>
            ),
          },
          {
            id: "organizations",
            label: "Organizations",
            content: (
              <div className="grid gap-6">
                <Section
                  eyebrow="Global"
                  title="All organizations"
                  loading={loading}
                  error={globalOrgsError}
                  forbidden={globalForbidden ? "Global organization inventory requires backend superuser authorization." : null}
                  empty={globalOrgs.length === 0 ? <BrutalEmptyState title="No organizations" description="No global organizations were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Name", render: (r: AdminOrganization) => <span className="font-bold">{r.name}</span> },
                      { key: "slug", header: "Slug", render: (r: AdminOrganization) => r.slug },
                      { key: "plan", header: "Plan", render: (r: AdminOrganization) => <BrutalBadge>{r.plan}</BrutalBadge> },
                      { key: "status", header: "Status", render: (r: AdminOrganization) => <BrutalBadge tone={r.is_active ? "yellow" : "muted"}>{r.is_active ? "Active" : "Inactive"}</BrutalBadge> },
                      { key: "members", header: "Members", render: (r: AdminOrganization) => String(r.member_count) },
                      { key: "repos", header: "Repositories", render: (r: AdminOrganization) => String(r.repository_count) },
                      { key: "created", header: "Created", render: (r: AdminOrganization) => formatDateTime(r.created_at) },
                    ]}
                    rows={globalOrgs}
                    emptyMessage="No organizations"
                  />
                </Section>
                <Section
                  eyebrow="Tenant"
                  title="Your organizations"
                  loading={loading}
                  error={scopeError}
                  empty={myOrgs.length === 0 ? <BrutalEmptyState title="No organizations" description="No tenant organizations were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Name", render: (r: Organization) => <span className="font-bold">{r.name}</span> },
                      { key: "slug", header: "Slug", render: (r: Organization) => r.slug },
                      { key: "plan", header: "Plan", render: (r: Organization) => <BrutalBadge>{r.plan}</BrutalBadge> },
                      { key: "id", header: "Tenant ID", render: (r: Organization) => <span className="break-all font-mono text-xs">{r.id}</span> },
                    ]}
                    rows={myOrgs}
                    emptyMessage="No organizations"
                  />
                  <p className="mt-4 text-xs text-on-surface-variant">Tenant identity is the selected organization UUID. No independent tenant inventory endpoint exists.</p>
                </Section>
              </div>
            ),
          },
          {
            id: "users",
            label: "Users",
            content: (
              <Section
                eyebrow="Global"
                title="User inventory"
                loading={loading}
                error={globalUsersError}
                forbidden={globalForbidden ? "Global user inventory requires backend superuser authorization." : null}
                empty={globalUsers.length === 0 ? <BrutalEmptyState title="No users" description="No global users were returned." /> : null}
              >
                <BrutalTable
                  columns={[
                    { key: "email", header: "Email", render: (r: AdminUser) => <span className="font-mono text-xs">{r.email}</span> },
                    { key: "username", header: "Username", render: (r: AdminUser) => r.username },
                    { key: "active", header: "Active", render: (r: AdminUser) => <BrutalBadge tone={r.is_active ? "yellow" : "muted"}>{r.is_active ? "Yes" : "No"}</BrutalBadge> },
                    { key: "superuser", header: "Superuser", render: (r: AdminUser) => <BrutalBadge tone={r.is_superuser ? "yellow" : "muted"}>{r.is_superuser ? "Yes" : "No"}</BrutalBadge> },
                    { key: "created", header: "Created", render: (r: AdminUser) => formatDateTime(r.created_at) },
                    { key: "login", header: "Last login", render: (r: AdminUser) => formatDateTime(r.last_login_at) },
                  ]}
                  rows={globalUsers}
                  emptyMessage="No users"
                />
                <p className="mt-4 text-xs text-on-surface-variant">Global user detail, suspension, MFA reset, and bulk administration endpoints are unavailable. Account changes remain in Settings and Auth.</p>
              </Section>
            ),
          },
          {
            id: "audit",
            label: "Audit",
            content: (
              <div className="grid gap-6">
                <Section
                  eyebrow="Audit"
                  title="Administrative audit log"
                  loading={loading}
                  error={auditError}
                  forbidden={globalForbidden ? "Global audit access requires backend superuser authorization." : null}
                  empty={auditLogs.length === 0 ? <BrutalEmptyState title="No audit events" description="No audit events were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "action", header: "Event", render: (r: AdminAuditLog) => <span className="font-bold">{r.action}</span> },
                      { key: "actor", header: "Actor", render: (r: AdminAuditLog) => <span className="font-mono text-xs">{shortId(r.user_id)}</span> },
                      { key: "target", header: "Target", render: (r: AdminAuditLog) => <span className="font-mono text-xs">{`${r.resource_type ?? "—"} ${r.resource_id ?? ""}`.trim()}</span> },
                      { key: "created", header: "Timestamp", render: (r: AdminAuditLog) => formatDateTime(r.created_at) },
                    ]}
                    rows={auditLogs}
                    emptyMessage="No audit events"
                  />
                </Section>
                <Section
                  eyebrow="Timeline"
                  title="Control-plane activity"
                  loading={loading}
                  error={eventsError}
                  forbidden={globalForbidden ? "Global activity access requires backend superuser authorization." : null}
                  empty={timeline.length === 0 ? <BrutalEmptyState title="No activity" description="No backend administrative events were returned." /> : null}
                >
                  <ol className="space-y-2">
                    {timeline.map((item) => (
                      <li key={item.id} className="border border-outline bg-surface p-3">
                        <p className="text-sm font-bold text-on-surface">{item.title}</p>
                        <p className="mt-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{item.detail} · {formatDateTime(item.at)}</p>
                      </li>
                    ))}
                  </ol>
                </Section>
              </div>
            ),
          },
          {
            id: "access",
            label: "Access",
            content: (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section
                  eyebrow="Sessions"
                  title="Current-user sessions"
                  loading={loading}
                  error={sessionsError}
                  empty={sessions.length === 0 ? <BrutalEmptyState title="No sessions" description="No active sessions were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "id", header: "Session", render: (r: SessionOut) => <span className="font-mono text-xs">{shortId(r.id)} {r.is_current ? "(current)" : ""}</span> },
                      { key: "network", header: "Network", render: (r: SessionOut) => <span className="text-xs">{r.ip_address ?? "unknown IP"}</span> },
                      { key: "agent", header: "Agent", render: (r: SessionOut) => <span className="text-xs">{r.user_agent ?? "unknown agent"}</span> },
                      { key: "expires", header: "Expires", render: (r: SessionOut) => formatDateTime(r.expires_at) },
                    ]}
                    rows={sessions}
                    emptyMessage="No sessions"
                  />
                  <div className="mt-4"><BrutalButton variant="ghost" size="sm" href="/settings/security">Manage sessions</BrutalButton></div>
                </Section>
                <Section
                  eyebrow="Credentials"
                  title="Current-user API keys"
                  loading={loading}
                  error={apiKeysError}
                  empty={apiKeys.length === 0 ? <BrutalEmptyState title="No API keys" description="No API-key metadata was returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Name", render: (r: ApiKeyOut) => <span className="font-bold">{r.name}</span> },
                      { key: "prefix", header: "Prefix", render: (r: ApiKeyOut) => <span className="font-mono text-xs">{r.key_prefix}</span> },
                      { key: "status", header: "Status", render: (r: ApiKeyOut) => <BrutalBadge tone={r.is_active ? "yellow" : "muted"}>{r.is_active ? "Active" : "Inactive"}</BrutalBadge> },
                      { key: "used", header: "Last used", render: (r: ApiKeyOut) => formatDateTime(r.last_used_at) },
                      { key: "expires", header: "Expires", render: (r: ApiKeyOut) => formatDateTime(r.expires_at) },
                    ]}
                    rows={apiKeys}
                    emptyMessage="No API keys"
                  />
                  <p className="mt-4 text-xs text-on-surface-variant">Only key metadata is shown. Secret values are never shown, stored, logged, or linked.</p>
                  <div className="mt-2"><BrutalButton variant="ghost" size="sm" href="/settings/security">Manage API keys</BrutalButton></div>
                </Section>
                <Section
                  eyebrow="Zero Trust"
                  title="Posture summary"
                  loading={loading}
                  error={zeroTrustError}
                  empty={!zeroTrustPosture ? <BrutalEmptyState title="No posture" description="No Zero Trust posture was returned." /> : null}
                >
                  {zeroTrustPosture ? (
                    <dl className="space-y-2 text-sm">
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Identity posture fields</dt><dd className="text-on-surface">{objectFieldCount(zeroTrustPosture.identity) ?? "—"}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Access posture fields</dt><dd className="text-on-surface">{objectFieldCount(zeroTrustPosture.access) ?? "—"}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Machine posture fields</dt><dd className="text-on-surface">{objectFieldCount(zeroTrustPosture.machine) ?? "—"}</dd></div>
                    </dl>
                  ) : null}
                  <div className="mt-4"><BrutalButton variant="ghost" size="sm" href="/security">Open Security workspace</BrutalButton></div>
                </Section>
                <Section
                  eyebrow="Zero Trust"
                  title="Privileged access and requests"
                  loading={loading}
                  error={privilegedError ?? accessRequestsError ?? reviewsError}
                  empty={privilegedAccess.length === 0 && accessRequests.length === 0 ? <BrutalEmptyState title="No privileged activity" description="No privileged access or access requests were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "identity", header: "Identity", render: (r: PrivilegedAccessItem) => <span className="font-mono text-xs">{r.identity ?? "—"}</span> },
                      { key: "resource", header: "Resource", render: (r: PrivilegedAccessItem) => r.resource ?? "—" },
                      { key: "level", header: "Privilege", render: (r: PrivilegedAccessItem) => <BrutalBadge tone="yellow">{r.privilege_level ?? "—"}</BrutalBadge> },
                      { key: "status", header: "Status", render: (r: PrivilegedAccessItem) => r.status ?? "—" },
                    ]}
                    rows={privilegedAccess}
                    emptyMessage="No privileged access"
                  />
                  <div className="mt-4">
                    <BrutalTable
                      columns={[
                        { key: "identity", header: "Identity", render: (r: AccessRequestItem) => <span className="font-mono text-xs">{r.identity ?? "—"}</span> },
                        { key: "action", header: "Action", render: (r: AccessRequestItem) => r.action ?? "—" },
                        { key: "status", header: "Status", render: (r: AccessRequestItem) => <BrutalBadge>{r.status ?? "—"}</BrutalBadge> },
                        { key: "approve", header: "Approval", render: (r: AccessRequestItem) => (
                          <BrutalButton
                            variant="primary"
                            size="sm"
                            disabled={!canZeroTrustWrite || r.status !== "REQUESTED"}
                            onClick={() => openApproveRequest(r)}
                          >
                            Approve
                          </BrutalButton>
                        ) },
                      ]}
                      rows={accessRequests}
                      emptyMessage="No access requests"
                    />
                  </div>
                  <div className="mt-4">
                    <BrutalTable
                      columns={[
                        { key: "id", header: "Review", render: (r: ZeroTrustReview) => <span className="font-mono text-xs">{r.id}</span> },
                        { key: "type", header: "Type", render: (r: ZeroTrustReview) => r.review_type ?? "—" },
                        { key: "scope", header: "Scope", render: (r: ZeroTrustReview) => r.scope ?? "—" },
                        { key: "status", header: "Status", render: (r: ZeroTrustReview) => <BrutalBadge>{r.status ?? "—"}</BrutalBadge> },
                        { key: "certify", header: "Certification", render: (r: ZeroTrustReview) => (
                          <BrutalButton
                            variant="primary"
                            size="sm"
                            disabled={!canZeroTrustWrite || r.status !== "pending"}
                            onClick={() => openCertifyReview(r)}
                          >
                            Certify
                          </BrutalButton>
                        ) },
                      ]}
                      rows={reviews}
                      emptyMessage="No access reviews"
                    />
                  </div>
                  <p className="mt-4 text-xs text-on-surface-variant">
                    {canZeroTrustWrite
                      ? "Approving a request or certifying a review sends an explicit confirm to the backend. Authorization is enforced server-side via zero_trust:write."
                      : "zero_trust:write is required to approve requests or certify reviews. This view is read-only for your current role."}
                  </p>
                </Section>
              </div>
            ),
          },
          {
            id: "security",
            label: "Security",
            content: (
              <div className="grid gap-6 lg:grid-cols-2">
                <Section
                  eyebrow="Security"
                  title="Operations summary"
                  loading={loading}
                  error={secopsError}
                  empty={!secopsDashboard ? <BrutalEmptyState title="No summary" description="No security summary was returned." /> : null}
                >
                  {secopsDashboard ? (
                    <dl className="grid grid-cols-2 gap-4 text-sm">
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Alerts</dt><dd className="font-mono text-xl text-on-surface">{secopsDashboard.alerts.total}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Findings</dt><dd className="font-mono text-xl text-on-surface">{secopsDashboard.findings.total}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Cases</dt><dd className="font-mono text-xl text-on-surface">{secopsDashboard.cases.total}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Indicators</dt><dd className="font-mono text-xl text-on-surface">{secopsDashboard.indicators.total}</dd></div>
                    </dl>
                  ) : null}
                  <div className="mt-4"><BrutalButton variant="ghost" size="sm" href="/security">Open Security workspace</BrutalButton></div>
                </Section>
                <Section
                  eyebrow="Governance"
                  title="Posture summary"
                  loading={loading}
                  error={governanceError}
                  empty={!governancePosture ? <BrutalEmptyState title="No posture" description="No governance posture was returned." /> : null}
                >
                  {governancePosture ? (
                    <dl className="space-y-2 text-sm">
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Total policies</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.total_policies}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Active policies</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.active_policies}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Violations (24h)</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.violations_24h}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Open exceptions</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.open_exceptions}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Verified controls</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.verified_controls}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Failing controls</dt><dd className="font-mono text-xl text-on-surface">{governancePosture.failing_controls}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Computed</dt><dd className="text-on-surface">{formatDateTime(governancePosture.computed_at)}</dd></div>
                    </dl>
                  ) : null}
                  <p className="mt-4 text-xs text-on-surface-variant">Risk values are backend-reported only and are never reinterpreted here.</p>
                  <div className="mt-2"><BrutalButton variant="ghost" size="sm" href="/governance">Open Governance workspace</BrutalButton></div>
                </Section>
              </div>
            ),
          },
          {
            id: "flags",
            label: "Flags",
            content: (
              <div className="grid gap-6">
                <Section
                  eyebrow="Global"
                  title="Feature defaults"
                  loading={loading}
                  error={globalFlagsError}
                  forbidden={globalForbidden ? "Global feature-flag inventory requires backend superuser authorization." : null}
                  empty={globalFlags.length === 0 ? <BrutalEmptyState title="No flags" description="No global feature flags were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Flag", render: (r: AdminFeatureFlag) => <span className="font-mono text-xs">{r.name}</span> },
                      { key: "default", header: "Default", render: (r: AdminFeatureFlag) => String(r.default) },
                      { key: "overridden", header: "Overridden", render: (r: AdminFeatureFlag) => String(r.overridden) },
                      { key: "enabled", header: "Enabled", render: (r: AdminFeatureFlag) => <BrutalBadge tone={r.enabled ? "yellow" : "muted"}>{String(r.enabled)}</BrutalBadge> },
                    ]}
                    rows={globalFlags}
                    emptyMessage="No flags"
                  />
                </Section>
                <Section
                  eyebrow="Tenant"
                  title="Organization flags"
                  loading={loading}
                  error={tenantFlagsError}
                  empty={tenantFlags.length === 0 ? <BrutalEmptyState title="No flags" description="No organization feature flags were returned." /> : null}
                >
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Flag", render: (r: FeatureFlag) => <span className="font-mono text-xs">{r.name}</span> },
                      { key: "enabled", header: "Enabled", render: (r: FeatureFlag) => <BrutalBadge tone={r.enabled ? "yellow" : "muted"}>{String(r.enabled)}</BrutalBadge> },
                      { key: "scope", header: "Scope", render: (r: FeatureFlag) => <span className="font-mono text-xs">{r.organization_id ?? "global"}</span> },
                    ]}
                    rows={tenantFlags}
                    emptyMessage="No flags"
                  />
                  <p className="mt-4 text-xs text-on-surface-variant">Flag changes are unavailable in C1. This view is read-only.</p>
                </Section>
              </div>
            ),
          },
        ]}
      />
      <BrutalModal
        open={pendingAction !== null}
        title={pendingAction?.kind === "certify-review" ? "Certify access review" : "Approve access request"}
        onClose={() => {
          if (!confirming) {
            setPendingAction(null);
            setActionError(null);
          }
        }}
        actions={
          <>
            <BrutalButton variant="ghost" size="sm" onClick={() => setPendingAction(null)} disabled={confirming}>
              Cancel
            </BrutalButton>
            <BrutalButton
              variant="primary"
              size="sm"
              onClick={runPendingAction}
              disabled={confirming || (pendingAction?.kind === "certify-review" && !certifyChecked)}
            >
              {pendingAction?.kind === "certify-review" ? "Confirm certification" : "Confirm approval"}
            </BrutalButton>
          </>
        }
      >
        {pendingAction ? (
          <div className="space-y-4 text-sm">
            <p>
              {pendingAction.kind === "certify-review"
                ? "Certifying an access review applies the backend certification flow for access review"
                : "Approving activates the requested privileged access in the backend."}{" "}
              <span className="font-mono text-xs">{pendingAction.label}</span>
            </p>
            <p className="text-xs text-on-surface-variant">Authorization is enforced server-side using zero_trust:write.</p>
            {pendingAction.kind === "certify-review" ? (
              <label className="flex items-start gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={certifyChecked}
                  onChange={(e) => setCertifyChecked(e.target.checked)}
                  className="mt-1"
                />
                <span>I confirm this model access review, representing an explicit certify approval.</span>
              </label>
            ) : null}
            {actionError ? <p className="font-bold text-error">{actionError}</p> : null}
          </div>
        ) : null}
      </BrutalModal>
    </div>
  );
}
