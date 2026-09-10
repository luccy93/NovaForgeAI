"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace data synchronously on switch */

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { hasPermission } from "@/lib/permissions";
import { PERMISSIONS } from "@/types/auth";
import { useToastStore } from "@/stores/toast";
import type {
  ConnectorDefinition,
  ConnectorSyncRecord,
  HealthSummary,
  InboundEvent,
  Integration,
  IntegrationConnection,
  IntegrationCredentialMeta,
  IntegrationPolicy,
  IntegrationVersion,
  IntegrationWebhook,
  OAuthConnection,
  TransferEvaluation,
  WebhookDelivery,
} from "@/types/integrations";
import { CAPABILITIES_BY_TYPE, INTEGRATION_STATUSES, INTEGRATION_TYPES, POLICY_ACTIONS } from "@/types/integrations";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function statusTone(status: string | undefined): "yellow" | "muted" | "error" | "default" {
  if (status === "ACTIVE" || status === "HEALTHY") return "yellow";
  if (status === "DEGRADED" || status === "NEEDS_REAUTH") return "error";
  if (status === "DISABLED" || status === "REVOKED" || status === "QUARANTINED" || status === "UNHEALTHY") return "muted";
  return "default";
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={value}>{value}</span>
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

function parseJsonObject(raw: string, field: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  try {
    const parsed: unknown = JSON.parse(trimmed);
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    throw new Error(`${field} must be a JSON object`);
  } catch (e) {
    if (e instanceof Error && e.message.includes("must be a JSON object")) throw e;
    throw new Error(`${field} is not valid JSON`);
  }
}

type TabId = "registry" | "connectors" | "connections" | "oauth" | "webhooks" | "policies" | "health" | "advanced";

type PendingModal =
  | { kind: "integration-create" }
  | { kind: "integration-status"; integration: Integration }
  | { kind: "version-create"; integration: Integration }
  | { kind: "connector-register"; connectorKey: string }
  | { kind: "connector-connect"; integration: Integration }
  | { kind: "connection-create" }
  | { kind: "connection-status"; connection: IntegrationConnection }
  | { kind: "credential-create"; connection: IntegrationConnection }
  | { kind: "credential-rotate"; credential: IntegrationCredentialMeta }
  | { kind: "oauth-start" }
  | { kind: "oauth-callback" }
  | { kind: "oauth-refresh"; oauth: OAuthConnection }
  | { kind: "oauth-revoke"; oauth: OAuthConnection }
  | { kind: "webhook-create" }
  | { kind: "webhook-status"; webhook: IntegrationWebhook }
  | { kind: "webhook-deliver"; webhook: IntegrationWebhook }
  | { kind: "webhook-inbound"; webhook: IntegrationWebhook }
  | { kind: "subscription-create" }
  | { kind: "policy-create" }
  | { kind: "policy-update"; policy: IntegrationPolicy }
  | null;

function connectionItems(value: unknown): IntegrationConnection[] {
  if (Array.isArray(value)) return value as IntegrationConnection[];
  if (value && typeof value === "object" && Array.isArray((value as { items?: unknown }).items)) {
    return (value as { items: IntegrationConnection[] }).items;
  }
  return [];
}

function oauthItems(value: unknown): OAuthConnection[] {
  if (Array.isArray(value)) return value as OAuthConnection[];
  if (value && typeof value === "object" && Array.isArray((value as { items?: unknown }).items)) {
    return (value as { items: OAuthConnection[] }).items;
  }
  return [];
}

export function IntegrationsWorkspace() {
  const pushToast = useToastStore((s) => s.push);
  const [active, setActive] = useState<TabId>("registry");
  const [permissions, setPermissions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);

  const [integrations, setIntegrations] = useState<Integration[] | null>(null);
  const [integrationsError, setIntegrationsError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("ALL");
  const [providerFilter, setProviderFilter] = useState("");
  const [selectedIntegrationId, setSelectedIntegrationId] = useState<string | null>(null);

  const [versions, setVersions] = useState<IntegrationVersion[] | null>(null);
  const [versionsError, setVersionsError] = useState<string | null>(null);
  const [versionsLoading, setVersionsLoading] = useState(false);

  const [catalog, setCatalog] = useState<ConnectorDefinition[] | null>(null);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [connections, setConnections] = useState<IntegrationConnection[] | null>(null);
  const [connectionsError, setConnectionsError] = useState<string | null>(null);
  const [selectedConnectionId, setSelectedConnectionId] = useState<string | null>(null);

  const [oauthList, setOauthList] = useState<OAuthConnection[] | null>(null);
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [oauthStatusFilter, setOauthStatusFilter] = useState("ALL");
  const [oauthStartResult, setOauthStartResult] = useState<{ authorize_url: string; id: string } | null>(null);
  const [selectedOAuthId, setSelectedOAuthId] = useState<string | null>(null);

  const [webhooks, setWebhooks] = useState<IntegrationWebhook[] | null>(null);
  const [webhooksError, setWebhooksError] = useState<string | null>(null);
  const [webhookStatusFilter, setWebhookStatusFilter] = useState("ALL");
  const [selectedWebhookId, setSelectedWebhookId] = useState<string | null>(null);
  const [deliveries, setDeliveries] = useState<WebhookDelivery[] | null>(null);
  const [deliveriesError, setDeliveriesError] = useState<string | null>(null);
  const [deliveriesLoading, setDeliveriesLoading] = useState(false);
  const [inboundEvents, setInboundEvents] = useState<InboundEvent[] | null>(null);
  const [inboundError, setInboundError] = useState<string | null>(null);
  const [inboundLoading, setInboundLoading] = useState(false);
  const [lastSubscription, setLastSubscription] = useState<{ id: string; status: string; target_url: string } | null>(null);

  const [policies, setPolicies] = useState<IntegrationPolicy[] | null>(null);
  const [policiesError, setPoliciesError] = useState<string | null>(null);
  const [selectedPolicyId, setSelectedPolicyId] = useState<string | null>(null);
  const [evalResult, setEvalResult] = useState<TransferEvaluation | null>(null);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalDraft, setEvalDraft] = useState({
    workspace: "",
    project: "",
    provider: "",
    operation: "",
    classification: "",
    region: "",
    fields: "",
    estimated_cents: "",
  });

  const [syncs, setSyncs] = useState<ConnectorSyncRecord[] | null>(null);
  const [syncsError, setSyncsError] = useState<string | null>(null);
  const [syncsLoading, setSyncsLoading] = useState(false);
  const [syncResult, setSyncResult] = useState<Record<string, unknown> | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncDraft, setSyncDraft] = useState({ sync_key: "", paths: "" });

  const [healthSummary, setHealthSummary] = useState<HealthSummary | null>(null);
  const [healthSummaryError, setHealthSummaryError] = useState<string | null>(null);
  const [healthSummaryLoading, setHealthSummaryLoading] = useState(false);
  const [summaryDays, setSummaryDays] = useState("7");

  const [bridgeResult, setBridgeResult] = useState<Record<string, unknown> | null>(null);
  const [bridgeError, setBridgeError] = useState<string | null>(null);
  const [bridgeRunning, setBridgeRunning] = useState(false);
  const [bridgeDraft, setBridgeDraft] = useState({
    operation: "",
    requests: "1",
    bytes_out: "0",
    estimated_cents: "0",
    provider: "",
    source_type: "external",
    name: "",
    target_url: "",
    method: "GET",
    model: "",
  });

  const [healthResult, setHealthResult] = useState<Record<string, unknown> | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [healthRunning, setHealthRunning] = useState(false);
  const [connectorHealthResult, setConnectorHealthResult] = useState<Record<string, unknown> | null>(null);
  const [connectorHealthError, setConnectorHealthError] = useState<string | null>(null);
  const [connectorHealthRunning, setConnectorHealthRunning] = useState(false);

  const [executeResult, setExecuteResult] = useState<Record<string, unknown> | null>(null);
  const [executeError, setExecuteError] = useState<string | null>(null);
  const [executing, setExecuting] = useState(false);
  const [executeDraft, setExecuteDraft] = useState({ operation: "", method: "GET", path: "", params: "", idempotency_key: "" });

  const [lastCredential, setLastCredential] = useState<IntegrationCredentialMeta | null>(null);

  const [modal, setModal] = useState<PendingModal>(null);
  const [submitting, setSubmitting] = useState(false);
  const [draft, setDraft] = useState({
    name: "",
    type: "api",
    provider: "",
    version: "1.0.0",
    workspace: "",
    environment: "",
    region: "",
    capabilities: "",
    config: "",
    owner: "",
    status: "ACTIVE",
    base_url: "",
    endpoint_ref: "",
    scopes: "",
    kind: "api_key",
    material: "",
    credential_id: "",
    expires_at: "",
    client_id: "",
    scopesOAuth: "",
    redirect_uri: "",
    authorization_endpoint: "",
    contract: "",
    compatibility: "compatible",
    migration_notes: "",
    webhook_name: "",
    webhook_url: "",
    webhook_events: "",
    signing_secret: "",
    state: "",
    code: "",
    token_endpoint: "",
    event_type: "",
    payload: "",
    delivery_id: "",
    headers: "",
    target_url: "",
    event_filter: "",
    policy_name: "",
    policy_workspace: "",
    policy_project: "",
    policy_provider: "",
    policy_operation: "",
    policy_action: "alert",
    allowed_classifications: "",
    allowed_regions: "",
    allowed_fields: "",
    max_estimated_cents: "",
    policy_owner: "",
    policy_enabled: "true",
  });

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

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
    setIntegrationsError(null);
    setCatalogError(null);
    setConnectionsError(null);
    setOauthError(null);
    setWebhooksError(null);
    setPoliciesError(null);

    async function settle<T>(load: () => Promise<T>, set: (value: T | null) => void, onError: (message: string) => void) {
      try {
        const value = await load();
        if (controller.signal.aborted || seq !== seqRef.current) return;
        set(value);
      } catch (e) {
        if (controller.signal.aborted || seq !== seqRef.current) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        onError(e instanceof Error ? e.message : "Unavailable");
      }
    }

    await Promise.all([
      settle(
        () =>
          api.integrationsFiltered(token, {
            status: statusFilter !== "ALL" ? statusFilter : undefined,
            provider: providerFilter.trim() ? providerFilter.trim() : undefined,
            limit: 100,
          }),
        (value) => setIntegrations(value?.items ?? []),
        setIntegrationsError,
      ),
      settle(
        () => api.integrationConnectorsAvailable(token),
        (value) => setCatalog(value?.items ?? []),
        setCatalogError,
      ),
      settle(
        () => api.integrationConnections(token, {}),
        (value) => setConnections(connectionItems(value)),
        setConnectionsError,
      ),
      settle(
        () => api.integrationOAuthList(token, { status: oauthStatusFilter !== "ALL" ? oauthStatusFilter : undefined }),
        (value) => setOauthList(oauthItems(value)),
        setOauthError,
      ),
      settle(
        () => api.integrationWebhooks(token, { status: webhookStatusFilter !== "ALL" ? webhookStatusFilter : undefined }),
        (value) => setWebhooks(value?.items ?? []),
        setWebhooksError,
      ),
      settle(
        () => api.integrationPolicies(token),
        (value) => setPolicies(value?.items ?? []),
        setPoliciesError,
      ),
    ]);

    if (!controller.signal.aborted && seq === seqRef.current) {
      setUpdatedAt(new Date().toLocaleTimeString());
      setLoading(false);
    }
  }, [statusFilter, providerFilter, oauthStatusFilter, webhookStatusFilter]);

  const loadVersions = useCallback(
    async (integrationId: string) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      setVersionsLoading(true);
      setVersionsError(null);
      try {
        const res = await api.integrationVersions(token, integrationId);
        setVersions(res.items ?? []);
      } catch (e) {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setVersionsError(e instanceof Error ? e.message : "Versions unavailable");
      } finally {
        setVersionsLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let activeFlag = true;
    api
      .whoami(token)
      .then((whoami) => {
        if (activeFlag) setPermissions(whoami.permissions ?? []);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
        }
      });
    return () => {
      activeFlag = false;
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
      setIntegrations(null);
      setVersions(null);
      setCatalog(null);
      setConnections(null);
      setOauthList(null);
      setWebhooks(null);
      setPolicies(null);
      setDeliveries(null);
      setInboundEvents(null);
      setSyncs(null);
      setHealthSummary(null);
      setEvalResult(null);
      setBridgeResult(null);
      setLastSubscription(null);
      setSelectedWebhookId(null);
      setSelectedPolicyId(null);
      setSelectedOAuthId(null);
      setHealthResult(null);
      setConnectorHealthResult(null);
      setExecuteResult(null);
      setLastCredential(null);
      setOauthStartResult(null);
      setSelectedIntegrationId(null);
      setSelectedConnectionId(null);
      setIntegrationsError(null);
      setCatalogError(null);
      setConnectionsError(null);
      setOauthError(null);
      setWebhooksError(null);
      setPoliciesError(null);
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

  useEffect(() => {
    if (selectedIntegrationId) {
      void loadVersions(selectedIntegrationId);
    } else {
      setVersions(null);
    }
  }, [selectedIntegrationId, loadVersions]);

  const canAdmin = hasPermission(permissions, PERMISSIONS.admin);
  const canRead = hasPermission(permissions, PERMISSIONS.orgRead) || canAdmin;
  const selectedIntegration = integrations?.find((i) => i.id === selectedIntegrationId) ?? null;
  const selectedConnection = connections?.find((c) => c.id === selectedConnectionId) ?? null;

  function openModal(next: PendingModal) {
    setDraft({
      name: "",
      type: "api",
      provider: "",
      version: "1.0.0",
      workspace: "",
      environment: "",
      region: "",
      capabilities: "",
      config: "",
      owner: "",
      status: "ACTIVE",
      base_url: "",
      endpoint_ref: "",
      scopes: "",
      kind: "api_key",
      material: "",
      credential_id: "",
      expires_at: "",
      client_id: "",
      scopesOAuth: "",
      redirect_uri: "",
      authorization_endpoint: "",
      contract: "",
      compatibility: "compatible",
      migration_notes: "",
      webhook_name: "",
      webhook_url: "",
      webhook_events: "",
      signing_secret: "",
      state: "",
      code: "",
      token_endpoint: "",
      event_type: "",
      payload: "",
      delivery_id: "",
      headers: "",
      target_url: "",
      event_filter: "",
      policy_name: "",
      policy_workspace: "",
      policy_project: "",
      policy_provider: "",
      policy_operation: "",
      policy_action: "alert",
      allowed_classifications: "",
      allowed_regions: "",
      allowed_fields: "",
      max_estimated_cents: "",
      policy_owner: "",
      policy_enabled: "true",
    });
    setModal(next);
  }

  async function handleIntegrationCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.name.trim()) {
      pushToast("warning", "Name is required");
      return;
    }
    setSubmitting(true);
    try {
      const capabilities = draft.capabilities.split(",").map((s) => s.trim()).filter(Boolean);
      const config = parseJsonObject(draft.config, "Config");
      await api.integrationCreate(token, {
        name: draft.name.trim(),
        type: draft.type,
        provider: draft.provider.trim(),
        version: draft.version.trim() || "1.0.0",
        workspace: draft.workspace.trim(),
        environment: draft.environment.trim(),
        region: draft.region.trim(),
        capabilities,
        config,
        owner: draft.owner.trim(),
      });
      setModal(null);
      pushToast("success", "Integration registered");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register integration", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleIntegrationStatus() {
    if (!modal || modal.kind !== "integration-status") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationSetStatus(token, modal.integration.id, draft.status);
      setModal(null);
      pushToast("success", `Integration status set to ${draft.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update integration status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleVersionCreate() {
    if (!modal || modal.kind !== "version-create") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.version.trim()) {
      pushToast("warning", "Version is required");
      return;
    }
    setSubmitting(true);
    try {
      const contract = parseJsonObject(draft.contract, "Contract");
      await api.integrationCreateVersion(token, modal.integration.id, {
        version: draft.version.trim(),
        contract,
        compatibility: draft.compatibility,
        deprecated: false,
        migration_notes: draft.migration_notes,
      });
      setModal(null);
      pushToast("success", "Version recorded");
      void loadVersions(modal.integration.id);
    } catch (e) {
      notifyError(e, "Failed to record version", () => void loadVersions(modal.integration.id));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConnectorRegister() {
    if (!modal || modal.kind !== "connector-register") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.name.trim()) {
      pushToast("warning", "Name is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationConnectorRegister(token, {
        connector_key: modal.connectorKey,
        name: draft.name.trim(),
        base_url: draft.base_url.trim(),
        workspace: draft.workspace.trim(),
        environment: draft.environment.trim(),
        owner: draft.owner.trim(),
      });
      setModal(null);
      pushToast("success", "Connector registered");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register connector", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConnectorConnect() {
    if (!modal || modal.kind !== "connector-connect") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.material) {
      pushToast("warning", "Credential material is required");
      return;
    }
    setSubmitting(true);
    try {
      const authConfig = parseJsonObject(draft.config, "Auth config");
      const result = await api.integrationConnectorConnect(token, {
        integration_id: modal.integration.id,
        material: draft.material,
        workspace: draft.workspace.trim(),
        environment: draft.environment.trim(),
        endpoint_ref: draft.endpoint_ref.trim(),
        auth_config: authConfig,
      });
      const credential = (result as unknown as { credential?: IntegrationCredentialMeta }).credential ?? null;
      setLastCredential(credential);
      setModal(null);
      pushToast("success", "Connector connected — material accepted once and never shown again");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to connect connector", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConnectionCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!selectedIntegrationId) {
      pushToast("warning", "Select an integration first");
      return;
    }
    setSubmitting(true);
    try {
      if (draft.endpoint_ref.trim()) {
        const scheme = draft.endpoint_ref.trim().split(":")[0]?.toLowerCase();
        if (scheme !== "http" && scheme !== "https") {
          pushToast("warning", "Endpoint must use http or https");
          setSubmitting(false);
          return;
        }
      }
      await api.integrationConnectionCreate(token, {
        integration_id: selectedIntegrationId,
        workspace: draft.workspace.trim(),
        environment: draft.environment.trim(),
        endpoint_ref: draft.endpoint_ref.trim(),
        scopes: draft.scopes.split(",").map((s) => s.trim()).filter(Boolean),
      });
      setModal(null);
      pushToast("success", "Connection created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create connection", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleConnectionStatus() {
    if (!modal || modal.kind !== "connection-status") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationConnectionSetStatus(token, modal.connection.id, draft.status);
      setModal(null);
      pushToast("success", `Connection status set to ${draft.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update connection status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCredentialCreate() {
    if (!modal || modal.kind !== "credential-create") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.material) {
      pushToast("warning", "Credential material is required");
      return;
    }
    setSubmitting(true);
    try {
      const authConfig = parseJsonObject(draft.config, "Auth config");
      const result = await api.integrationCredentialCreate(token, {
        kind: draft.kind,
        material: draft.material,
        connection_id: modal.connection.id,
        scopes: draft.scopes.split(",").map((s) => s.trim()).filter(Boolean),
        expires_at: draft.expires_at.trim() || undefined,
        auth_config: authConfig,
      });
      setLastCredential(result);
      setModal(null);
      pushToast("success", "Credential stored — material accepted once and never shown again");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to store credential", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleCredentialRotate() {
    if (!modal || modal.kind !== "credential-rotate") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.material) {
      pushToast("warning", "New credential material is required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.integrationCredentialRotate(token, modal.credential.id, draft.material);
      setLastCredential(result);
      setModal(null);
      pushToast("success", "Credential rotated — old credential revoked, new material never shown again");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to rotate credential", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOAuthStart() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!selectedIntegrationId || !draft.client_id.trim() || !draft.redirect_uri.trim() || !draft.authorization_endpoint.trim()) {
      pushToast("warning", "Integration, client ID, redirect URI and authorization endpoint are required");
      return;
    }
    setSubmitting(true);
    try {
      const result = await api.integrationOAuthStart(token, {
        integration_id: selectedIntegrationId,
        provider: draft.provider.trim(),
        client_id: draft.client_id.trim(),
        scopes: draft.scopesOAuth.split(",").map((s) => s.trim()).filter(Boolean),
        redirect_uri: draft.redirect_uri.trim(),
        authorization_endpoint: draft.authorization_endpoint.trim(),
      });
      setOauthStartResult({ authorize_url: result.authorize_url, id: result.id });
      setModal(null);
      pushToast("success", "OAuth flow started — complete authorization in the provider, then use the callback step");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to start OAuth flow", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function runConnectionHealth() {
    if (!selectedConnectionId) {
      pushToast("warning", "Select a connection first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setHealthRunning(true);
    setHealthError(null);
    try {
      const result = await api.integrationConnectionHealth(token, selectedConnectionId);
      setHealthResult(result);
      pushToast("success", "Health check recorded");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setHealthError(e instanceof Error ? e.message : "Health check failed");
    } finally {
      setHealthRunning(false);
    }
  }

  async function runConnectorHealth() {
    if (!selectedConnectionId) {
      pushToast("warning", "Select a connection first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setConnectorHealthRunning(true);
    setConnectorHealthError(null);
    try {
      const result = await api.integrationConnectorHealth(token, selectedConnectionId);
      setConnectorHealthResult(result);
      pushToast("success", "Connector health recorded");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setConnectorHealthError(e instanceof Error ? e.message : "Connector health check failed");
    } finally {
      setConnectorHealthRunning(false);
    }
  }

  async function handleExecute() {
    if (!selectedConnectionId) {
      pushToast("warning", "Select a connection first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setExecuting(true);
    setExecuteError(null);
    try {
      const params = parseJsonObject(executeDraft.params, "Params");
      const result = await api.integrationExecute(token, selectedConnectionId, {
        operation: executeDraft.operation.trim(),
        method: executeDraft.method,
        path: executeDraft.path.trim(),
        params,
        idempotency_key: executeDraft.idempotency_key.trim(),
      });
      setExecuteResult(result as unknown as Record<string, unknown>);
      pushToast("success", "Operation executed");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      setExecuteError(e instanceof Error ? e.message : "Execution failed");
    } finally {
      setExecuting(false);
    }
  }

  const loadDeliveries = useCallback(async (webhookId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setDeliveriesLoading(true);
    setDeliveriesError(null);
    try {
      const res = await api.integrationWebhookDeliveries(token, webhookId);
      setDeliveries(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setDeliveriesError(e instanceof Error ? e.message : "Deliveries unavailable");
    } finally {
      setDeliveriesLoading(false);
    }
  }, []);

  const loadInbound = useCallback(async (webhookId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setInboundLoading(true);
    setInboundError(null);
    try {
      const res = await api.integrationWebhookInboundList(token, webhookId);
      setInboundEvents(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setInboundError(e instanceof Error ? e.message : "Inbound events unavailable");
    } finally {
      setInboundLoading(false);
    }
  }, []);

  const loadSyncs = useCallback(async (connectionId: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSyncsLoading(true);
    setSyncsError(null);
    try {
      const res = await api.integrationConnectorSyncs(token, connectionId);
      setSyncs(res.items ?? []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setSyncsError(e instanceof Error ? e.message : "Sync history unavailable");
    } finally {
      setSyncsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedWebhookId) {
      void loadDeliveries(selectedWebhookId);
      void loadInbound(selectedWebhookId);
    } else {
      setDeliveries(null);
      setInboundEvents(null);
    }
  }, [selectedWebhookId, loadDeliveries, loadInbound]);

  useEffect(() => {
    if (selectedConnectionId && active === "connections") {
      void loadSyncs(selectedConnectionId);
    }
  }, [selectedConnectionId, active, loadSyncs]);

  async function handleOAuthCallback() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.state.trim() || !draft.code.trim() || !draft.token_endpoint.trim()) {
      pushToast("warning", "State, code and token endpoint are required");
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationOAuthCallback(token, {
        state: draft.state.trim(),
        code: draft.code.trim(),
        token_endpoint: draft.token_endpoint.trim(),
      });
      setModal(null);
      pushToast("success", "OAuth callback exchanged — tokens stored server-side, never displayed");
      void loadAll();
    } catch (e) {
      notifyError(e, "OAuth callback failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOAuthRefresh() {
    if (!modal || modal.kind !== "oauth-refresh") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.token_endpoint.trim()) {
      pushToast("warning", "Token endpoint is required");
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationOAuthRefresh(token, modal.oauth.id, draft.token_endpoint.trim());
      setModal(null);
      pushToast("success", "OAuth token refreshed");
      void loadAll();
    } catch (e) {
      notifyError(e, "OAuth refresh failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleOAuthRevoke() {
    if (!modal || modal.kind !== "oauth-revoke") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationOAuthRevoke(token, modal.oauth.id);
      setModal(null);
      pushToast("success", "OAuth connection revoked");
      void loadAll();
    } catch (e) {
      notifyError(e, "OAuth revocation failed", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleWebhookCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.webhook_name.trim() || !draft.webhook_url.trim()) {
      pushToast("warning", "Name and URL are required");
      return;
    }
    const scheme = draft.webhook_url.trim().split(":")[0]?.toLowerCase();
    if (scheme !== "http" && scheme !== "https") {
      pushToast("warning", "Webhook URL must use http or https");
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationWebhookCreate(token, {
        name: draft.webhook_name.trim(),
        url: draft.webhook_url.trim(),
        integration_id: selectedIntegrationId ?? undefined,
        events: draft.webhook_events.split(",").map((s) => s.trim()).filter(Boolean),
        signing_secret: draft.signing_secret,
      });
      setModal(null);
      pushToast("success", "Webhook registered — signing secret stored encrypted, never shown");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to register webhook", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleWebhookStatus() {
    if (!modal || modal.kind !== "webhook-status") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      await api.integrationWebhookSetStatus(token, modal.webhook.id, draft.status);
      setModal(null);
      pushToast("success", `Webhook status set to ${draft.status}`);
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update webhook status", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleWebhookDeliver() {
    if (!modal || modal.kind !== "webhook-deliver") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.event_type.trim()) {
      pushToast("warning", "Event type is required");
      return;
    }
    setSubmitting(true);
    try {
      const payload = parseJsonObject(draft.payload, "Payload");
      await api.integrationWebhookDeliver(token, modal.webhook.id, {
        event_type: draft.event_type.trim(),
        payload,
        delivery_id: draft.delivery_id.trim() || undefined,
      });
      setModal(null);
      pushToast("success", "Delivery enqueued — retries are bounded with dead-letter on exhaustion");
      void loadDeliveries(modal.webhook.id);
    } catch (e) {
      notifyError(e, "Failed to enqueue delivery", () => selectedWebhookId && void loadDeliveries(selectedWebhookId));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleWebhookInboundTest() {
    if (!modal || modal.kind !== "webhook-inbound") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const body = parseJsonObject(draft.payload, "Body");
      const headers = parseJsonObject(draft.headers, "Headers") as Record<string, string>;
      const result = await api.integrationWebhookInboundReceive(token, modal.webhook.id, {
        headers,
        body,
        event_type: draft.event_type.trim(),
        delivery_id: draft.delivery_id.trim(),
      });
      setModal(null);
      pushToast(
        "success",
        (result as { deduplicated?: boolean }).deduplicated
          ? "Inbound deduplicated — delivery already recorded"
          : `Inbound recorded with status ${(result as { status?: string }).status ?? "RECEIVED"}`,
      );
      void loadInbound(modal.webhook.id);
    } catch (e) {
      notifyError(e, "Inbound test failed", () => selectedWebhookId && void loadInbound(selectedWebhookId));
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSubscriptionCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!selectedConnectionId || !draft.target_url.trim()) {
      pushToast("warning", "Select a connection and provide a target URL");
      return;
    }
    const scheme = draft.target_url.trim().split(":")[0]?.toLowerCase();
    if (scheme !== "http" && scheme !== "https") {
      pushToast("warning", "Target URL must use http or https");
      return;
    }
    setSubmitting(true);
    try {
      const eventFilter = parseJsonObject(draft.event_filter, "Event filter");
      const result = await api.integrationSubscriptionCreate(token, {
        connection_id: selectedConnectionId,
        event_filter: eventFilter,
        target_url: draft.target_url.trim(),
      });
      setLastSubscription({ id: result.id, status: result.status, target_url: result.target_url });
      setModal(null);
      pushToast("success", "Subscription created");
    } catch (e) {
      notifyError(e, "Failed to create subscription");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleSyncRun() {
    if (!selectedConnectionId) {
      pushToast("warning", "Select a connection first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSyncing(true);
    try {
      const paths = syncDraft.paths.split(",").map((s) => s.trim()).filter(Boolean);
      const result = await api.integrationConnectorSync(token, selectedConnectionId, {
        sync_key: syncDraft.sync_key.trim() || undefined,
        paths: paths.length > 0 ? paths : undefined,
      });
      setSyncResult(result);
      pushToast(
        "success",
        (result as { deduplicated?: boolean }).deduplicated
          ? "Sync deduplicated — this sync key already ran"
          : `Sync ${String((result as { status?: unknown }).status ?? "finished")}: ${String((result as { records?: unknown }).records ?? 0)} records`,
      );
      void loadSyncs(selectedConnectionId);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      pushToast("error", e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  }

  async function handlePolicyCreate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (!draft.policy_name.trim()) {
      pushToast("warning", "Policy name is required");
      return;
    }
    setSubmitting(true);
    try {
      const maxCents = draft.max_estimated_cents.trim() ? Number(draft.max_estimated_cents.trim()) : undefined;
      await api.integrationPolicyCreate(token, {
        name: draft.policy_name.trim(),
        workspace: draft.policy_workspace.trim(),
        project: draft.policy_project.trim(),
        provider: draft.policy_provider.trim(),
        operation: draft.policy_operation.trim(),
        action: draft.policy_action,
        allowed_classifications: draft.allowed_classifications.split(",").map((s) => s.trim()).filter(Boolean),
        allowed_regions: draft.allowed_regions.split(",").map((s) => s.trim()).filter(Boolean),
        allowed_fields: draft.allowed_fields.split(",").map((s) => s.trim()).filter(Boolean),
        max_estimated_cents: maxCents,
        owner: draft.policy_owner.trim(),
      });
      setModal(null);
      pushToast("success", "Policy created");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to create policy", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handlePolicyUpdate() {
    if (!modal || modal.kind !== "policy-update") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        action: draft.policy_action,
        enabled: draft.policy_enabled === "true",
      };
      if (draft.policy_workspace.trim()) body.workspace = draft.policy_workspace.trim();
      if (draft.policy_project.trim()) body.project = draft.policy_project.trim();
      if (draft.policy_provider.trim()) body.provider = draft.policy_provider.trim();
      if (draft.policy_operation.trim()) body.operation = draft.policy_operation.trim();
      if (draft.policy_owner.trim()) body.owner = draft.policy_owner.trim();
      if (draft.allowed_classifications.trim()) body.allowed_classifications = draft.allowed_classifications.split(",").map((s) => s.trim()).filter(Boolean);
      if (draft.allowed_regions.trim()) body.allowed_regions = draft.allowed_regions.split(",").map((s) => s.trim()).filter(Boolean);
      if (draft.allowed_fields.trim()) body.allowed_fields = draft.allowed_fields.split(",").map((s) => s.trim()).filter(Boolean);
      if (draft.max_estimated_cents.trim()) body.max_estimated_cents = Number(draft.max_estimated_cents.trim());
      await api.integrationPolicyUpdate(token, modal.policy.id, body);
      setModal(null);
      pushToast("success", "Policy updated");
      void loadAll();
    } catch (e) {
      notifyError(e, "Failed to update policy", () => void loadAll());
    } finally {
      setSubmitting(false);
    }
  }

  async function handleEvaluate() {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setEvaluating(true);
    setEvalError(null);
    try {
      const result = await api.integrationPolicyEvaluate(token, {
        workspace: evalDraft.workspace.trim(),
        project: evalDraft.project.trim(),
        provider: evalDraft.provider.trim(),
        operation: evalDraft.operation.trim(),
        classification: evalDraft.classification.trim(),
        region: evalDraft.region.trim(),
        fields: evalDraft.fields.split(",").map((s) => s.trim()).filter(Boolean),
        estimated_cents: evalDraft.estimated_cents.trim() ? Number(evalDraft.estimated_cents.trim()) : 0,
      });
      setEvalResult(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setEvalError(e instanceof Error ? e.message : "Evaluation failed");
    } finally {
      setEvaluating(false);
    }
  }

  async function loadHealthSummary() {
    if (!selectedIntegrationId) {
      pushToast("warning", "Select an integration in the Registry tab first");
      return;
    }
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const days = Math.min(Math.max(Number(summaryDays) || 7, 1), 90);
    setHealthSummaryLoading(true);
    setHealthSummaryError(null);
    try {
      const result = await api.integrationHealthSummary(token, selectedIntegrationId, days);
      setHealthSummary(result);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setHealthSummaryError(e instanceof Error ? e.message : "Health summary unavailable");
    } finally {
      setHealthSummaryLoading(false);
    }
  }

  async function runBridge(kind: "finops" | "knowledge" | "workflow" | "ai") {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    setBridgeRunning(true);
    setBridgeError(null);
    try {
      let result: Record<string, unknown>;
      if (kind === "finops") {
        if (!selectedConnectionId) {
          pushToast("warning", "Select a connection in the Connections tab first");
          setBridgeRunning(false);
          return;
        }
        result = await api.integrationFinopsUsage(token, selectedConnectionId, {
          operation: bridgeDraft.operation.trim(),
          requests: Number(bridgeDraft.requests) || 1,
          bytes_out: Number(bridgeDraft.bytes_out) || 0,
          estimated_cents: Number(bridgeDraft.estimated_cents) || 0,
          provider: bridgeDraft.provider.trim(),
        });
      } else if (kind === "knowledge") {
        if (!selectedIntegrationId) {
          pushToast("warning", "Select an integration in the Registry tab first");
          setBridgeRunning(false);
          return;
        }
        result = await api.integrationKnowledgeSource(token, selectedIntegrationId, {
          source_type: bridgeDraft.source_type,
          name: bridgeDraft.name.trim(),
        });
      } else if (kind === "workflow") {
        if (!selectedConnectionId) {
          pushToast("warning", "Select a connection in the Connections tab first");
          setBridgeRunning(false);
          return;
        }
        result = await api.integrationWorkflowInvoke(token, selectedConnectionId, {
          operation: bridgeDraft.operation.trim(),
        });
      } else {
        if (!bridgeDraft.target_url.trim()) {
          pushToast("warning", "Target URL is required for AI actions");
          setBridgeRunning(false);
          return;
        }
        result = await api.integrationAiRequestAction(token, {
          operation: bridgeDraft.operation.trim(),
          target_url: bridgeDraft.target_url.trim(),
          method: bridgeDraft.method,
          model: bridgeDraft.model.trim(),
          provider: bridgeDraft.provider.trim(),
        });
      }
      setBridgeResult(result);
      pushToast("success", "Bridge operation completed");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.kind === "forbidden") {
        pushToast("warning", "You don't have permission to perform this action");
        return;
      }
      setBridgeError(e instanceof Error ? e.message : "Bridge operation failed");
    } finally {
      setBridgeRunning(false);
    }
  }

  const tabs: Array<{ id: TabId; label: string }> = [
    { id: "registry", label: "Registry" },
    { id: "connectors", label: "Connectors" },
    { id: "connections", label: "Connections" },
    { id: "oauth", label: "OAuth" },
    { id: "webhooks", label: "Webhooks" },
    { id: "policies", label: "Policies" },
    { id: "health", label: "Health" },
    { id: "advanced", label: "Advanced" },
  ];

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
          {!canRead && !canAdmin ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Read-only view · no integration permissions
            </span>
          ) : null}
          {canAdmin ? (
            <span className="border border-outline bg-surface px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Admin actions enabled
            </span>
          ) : null}
          <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </BrutalButton>
        </div>
      </div>

      <div role="tablist" aria-label="Integrations sections" className="flex flex-wrap gap-2">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={tab.id === active}
            onClick={() => setActive(tab.id)}
            className={
              tab.id === active
                ? "border border-primary-container bg-primary-container px-4 py-2 font-mono text-xs uppercase tracking-widest text-black"
                : "border border-outline bg-transparent px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant hover:border-on-surface hover:text-on-surface"
            }
          >
            {tab.label}
          </button>
        ))}
      </div>

      {active === "registry" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Registry" title="Integrations">
            <div className="mb-3 flex flex-wrap gap-2">
              <div className="min-w-32 flex-1">
                <BrutalSelect
                  label="Status"
                  value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value)}
                  options={[{ value: "ALL", label: "All statuses" }, ...INTEGRATION_STATUSES.map((s) => ({ value: s, label: s }))]}
                />
              </div>
              <div className="min-w-32 flex-1">
                <BrutalInput label="Provider" value={providerFilter} onChange={(e) => setProviderFilter(e.target.value)} placeholder="github" />
              </div>
            </div>
            <div className="mb-3 flex gap-2">
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply filters</BrutalButton>
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "integration-create" })}>Register</BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={integrationsError} onRetry={() => void loadAll()} emptyTitle="No integrations" emptyDescription="Register an integration to connect an external system.">
              {integrations && integrations.length > 0 ? (
                <ul className="space-y-2">
                  {integrations.map((item) => (
                    <li key={item.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedIntegrationId(item.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${item.id === selectedIntegrationId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{item.name}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{item.provider || item.type} · v{item.version}</span>
                        </span>
                        <BrutalBadge tone={statusTone(item.status)}>{item.health ?? item.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Detail" title="Selected integration">
            <PanelBody loading={loading} error={integrationsError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select an integration from the registry list.">
              {selectedIntegration ? (
                <div className="space-y-3">
                  <StatRow label="Name" value={selectedIntegration.name} />
                  <StatRow label="Type" value={selectedIntegration.type} />
                  <StatRow label="Provider" value={selectedIntegration.provider || "—"} />
                  <StatRow label="Version" value={selectedIntegration.version} />
                  <StatRow label="Status" value={selectedIntegration.status} />
                  <StatRow label="Health" value={selectedIntegration.health} />
                  <StatRow label="Workspace" value={selectedIntegration.workspace || "—"} />
                  <StatRow label="Environment" value={selectedIntegration.environment || "—"} />
                  <StatRow label="Region" value={selectedIntegration.region || "—"} />
                  <StatRow label="Capabilities" value={(selectedIntegration.capabilities ?? []).join(", ") || "—"} />
                  <StatRow label="Owner" value={selectedIntegration.owner || "—"} />
                  {canAdmin ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton variant="ghost" size="sm" onClick={() => { setDraft((d) => ({ ...d, status: selectedIntegration.status })); setModal({ kind: "integration-status", integration: selectedIntegration }); }}>Set status</BrutalButton>
                      <BrutalButton variant="ghost" size="sm" onClick={() => setModal({ kind: "version-create", integration: selectedIntegration })}>Record version</BrutalButton>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Versions" title="Version history">
            <PanelBody loading={versionsLoading} error={versionsError} onRetry={() => selectedIntegrationId && void loadVersions(selectedIntegrationId)} emptyTitle="No versions" emptyDescription="Version rows are immutable history recorded per integration.">
              {versions && versions.length > 0 ? (
                <ul className="space-y-2">
                  {versions.map((v) => (
                    <li key={v.id} className="border border-outline-variant bg-surface px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-mono text-sm text-on-surface">v{v.version}</span>
                        <BrutalBadge tone={v.deprecated ? "muted" : "default"}>{v.compatibility}</BrutalBadge>
                      </div>
                      {v.migration_notes ? <p className="mt-1 text-xs text-on-surface-variant">{v.migration_notes}</p> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "connectors" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Catalog" title="Available connectors">
            <PanelBody loading={loading} error={catalogError} onRetry={() => void loadAll()} emptyTitle="No connectors" emptyDescription="The backend publishes a fixed connector catalog.">
              {catalog && catalog.length > 0 ? (
                <ul className="space-y-2">
                  {catalog.map((c) => (
                    <li key={c.key} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-3 py-2">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-bold text-on-surface">{c.key}</span>
                        <span className="block truncate font-mono text-xs text-on-surface-variant">{c.provider} · {c.auth_kind} · {(c.capabilities ?? []).join(", ")}</span>
                      </span>
                      {canAdmin ? (
                        <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "connector-register", connectorKey: c.key })}>Register</BrutalButton>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Connect" title="Register then connect">
            <PanelBody loading={loading} error={integrationsError} onRetry={() => void loadAll()} emptyTitle="No connector integrations" emptyDescription="Register a connector above, select it in the Registry tab, then connect it here with a one-time secret.">
              {integrations && integrations.filter((i) => i.type === "connector").length > 0 ? (
                <ul className="space-y-2">
                  {integrations.filter((i) => i.type === "connector").map((item) => (
                    <li key={item.id} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-3 py-2">
                      <span className="min-w-0">
                        <span className="block truncate text-sm font-bold text-on-surface">{item.name}</span>
                        <span className="block truncate font-mono text-xs text-on-surface-variant">{item.provider} · {item.status}</span>
                      </span>
                      {canAdmin ? (
                        <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "connector-connect", integration: item })}>Connect</BrutalButton>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
            {lastCredential ? (
              <div className="mt-3 border border-outline bg-surface px-3 py-2">
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Last credential reference (metadata only)</p>
                <StatRow label="ID" value={lastCredential.id} />
                <StatRow label="Kind" value={lastCredential.kind} />
                <StatRow label="Secret ref" value={lastCredential.secret_ref} />
                <StatRow label="Hint" value={lastCredential.material_hint || "—"} />
                <StatRow label="Status" value={lastCredential.status} />
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {active === "connections" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Connections" title="Managed connections">
            <div className="mb-3 flex gap-2">
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "connection-create" })} disabled={!selectedIntegrationId}>
                  New connection
                </BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={connectionsError} onRetry={() => void loadAll()} emptyTitle="No connections" emptyDescription="Connections bind an integration to an environment with a credential reference.">
              {connections && connections.length > 0 ? (
                <ul className="space-y-2">
                  {connections.map((conn) => (
                    <li key={conn.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedConnectionId(conn.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${conn.id === selectedConnectionId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-xs text-on-surface">{conn.id.slice(0, 8)}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{conn.environment || conn.workspace || "default"} · {conn.endpoint_ref || "no endpoint"}</span>
                        </span>
                        <BrutalBadge tone={statusTone(conn.health !== "UNKNOWN" ? conn.health : conn.status)}>{conn.health !== "UNKNOWN" ? conn.health : conn.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Detail" title="Selected connection">
            <PanelBody loading={loading} error={connectionsError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a connection to inspect it and manage its credential.">
              {selectedConnection ? (
                <div className="space-y-3">
                  <StatRow label="ID" value={selectedConnection.id} />
                  <StatRow label="Integration" value={selectedConnection.integration_id} />
                  <StatRow label="Status" value={selectedConnection.status} />
                  <StatRow label="Health" value={selectedConnection.health} />
                  <StatRow label="Endpoint" value={selectedConnection.endpoint_ref || "—"} />
                  <StatRow label="Credential" value={selectedConnection.credential_id ?? "none linked"} />
                  <StatRow label="Scopes" value={(selectedConnection.scopes ?? []).join(", ") || "—"} />
                  <StatRow label="Last success" value={formatDateTime(selectedConnection.last_success_at)} />
                  <StatRow label="Last failure" value={formatDateTime(selectedConnection.last_failure_at)} />
                  <StatRow label="Failures" value={String(selectedConnection.consecutive_failures ?? 0)} />
                  {canAdmin ? (
                    <div className="flex flex-wrap gap-2 pt-2">
                      <BrutalButton variant="ghost" size="sm" onClick={() => { setDraft((d) => ({ ...d, status: selectedConnection.status })); setModal({ kind: "connection-status", connection: selectedConnection }); }}>Set status</BrutalButton>
                      <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "credential-create", connection: selectedConnection })}>Store credential</BrutalButton>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </PanelBody>
            {canAdmin && lastCredential ? (
              <div className="mt-3 flex flex-wrap items-center gap-2 border border-outline bg-surface px-3 py-2">
                <span className="font-mono text-xs text-on-surface-variant">Credential {lastCredential.id.slice(0, 8)} · {lastCredential.status}</span>
                <BrutalButton variant="ghost" size="sm" onClick={() => setModal({ kind: "credential-rotate", credential: lastCredential })}>Rotate</BrutalButton>
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Execute" title="Bounded operation test">
            <p className="mb-3 text-xs text-on-surface-variant">Runs through the managed credential only. Destructive methods require a per-connection allowlist; caller auth headers are never trusted.</p>
            <div className="space-y-3">
              <BrutalInput label="Operation" value={executeDraft.operation} onChange={(e) => setExecuteDraft((d) => ({ ...d, operation: e.target.value }))} placeholder="list_repos" />
              <div className="grid grid-cols-2 gap-2">
                <BrutalSelect label="Method" value={executeDraft.method} onChange={(e) => setExecuteDraft((d) => ({ ...d, method: e.target.value }))} options={["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((m) => ({ value: m, label: m }))} />
                <BrutalInput label="Path" value={executeDraft.path} onChange={(e) => setExecuteDraft((d) => ({ ...d, path: e.target.value }))} placeholder="/user/repos" />
              </div>
              <BrutalInput label="Params (JSON)" value={executeDraft.params} onChange={(e) => setExecuteDraft((d) => ({ ...d, params: e.target.value }))} placeholder='{"per_page": 10}' />
              <BrutalInput label="Idempotency key" value={executeDraft.idempotency_key} onChange={(e) => setExecuteDraft((d) => ({ ...d, idempotency_key: e.target.value }))} placeholder="optional" />
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => void handleExecute()} disabled={executing || !selectedConnectionId}>
                  {executing ? "Executing…" : "Execute"}
                </BrutalButton>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Execution requires admin</p>
              )}
            </div>
            {executeError ? <p className="mt-3 text-xs text-error">{executeError}</p> : null}
            {executeResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <PrimitiveRows data={executeResult} />
              </div>
            ) : null}
            <div className="mt-4 border-t border-outline pt-3">
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Connector sync (bounded, idempotent by key)</p>
              <div className="space-y-2">
                <BrutalInput label="Sync key (optional)" value={syncDraft.sync_key} onChange={(e) => setSyncDraft((d) => ({ ...d, sync_key: e.target.value }))} placeholder="auto-generated per hour if empty" />
                <BrutalInput label="Paths (comma-separated, optional)" value={syncDraft.paths} onChange={(e) => setSyncDraft((d) => ({ ...d, paths: e.target.value }))} placeholder="defaults to connector sync_paths" />
                {canAdmin ? (
                  <BrutalButton variant="ghost" size="sm" onClick={() => void handleSyncRun()} disabled={syncing || !selectedConnectionId}>
                    {syncing ? "Syncing…" : "Run sync"}
                  </BrutalButton>
                ) : (
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Sync requires admin</p>
                )}
              </div>
              {syncResult ? (
                <div className="mt-2 border-t border-outline pt-2">
                  <PrimitiveRows data={syncResult} />
                </div>
              ) : null}
              <div className="mt-2">
                <div className="mb-1 flex items-center justify-between">
                  <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Sync history</p>
                  <BrutalButton variant="ghost" size="sm" onClick={() => selectedConnectionId && void loadSyncs(selectedConnectionId)} disabled={!selectedConnectionId}>Reload</BrutalButton>
                </div>
                {syncsLoading ? (
                  <LoadingPanel rows={2} />
                ) : syncsError ? (
                  <p className="text-xs text-error">{syncsError}</p>
                ) : syncs && syncs.length > 0 ? (
                  <ul className="space-y-1">
                    {syncs.slice(0, 5).map((s) => (
                      <li key={s.sync_key} className="flex items-center justify-between gap-2 border border-outline-variant bg-surface px-2 py-1">
                        <span className="truncate font-mono text-xs text-on-surface">{s.sync_key.slice(0, 16)}… · {s.records} records · {s.pages} pages</span>
                        <BrutalBadge tone={s.status === "COMPLETED" ? "yellow" : s.status === "FAILED" ? "error" : "default"}>{s.status}</BrutalBadge>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="font-mono text-xs text-on-surface-variant">No syncs recorded.</p>
                )}
              </div>
            </div>
            <div className="mt-4 border-t border-outline pt-3">
              <p className="mb-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Event subscription</p>
              <p className="mb-2 text-xs text-on-surface-variant">Delivers connection events to an allowlisted https target. There is no browser realtime feed — realtime stays UNAVAILABLE.</p>
              {canAdmin ? (
                <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "subscription-create" })} disabled={!selectedConnectionId}>Subscribe</BrutalButton>
              ) : (
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Subscriptions require admin</p>
              )}
              {lastSubscription ? (
                <div className="mt-2">
                  <StatRow label="Subscription" value={lastSubscription.id} />
                  <StatRow label="Target" value={lastSubscription.target_url} />
                </div>
              ) : null}
            </div>
          </BrutalCard>
        </div>
      ) : null}

      {active === "oauth" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="OAuth" title="OAuth connections">
            <div className="mb-3 flex flex-wrap gap-2">
              <div className="min-w-32 flex-1">
                <BrutalSelect label="Status" value={oauthStatusFilter} onChange={(e) => setOauthStatusFilter(e.target.value)} options={["ALL", "PENDING", "ACTIVE", "NEEDS_REAUTH", "REVOKED"].map((s) => ({ value: s, label: s }))} />
              </div>
              <div className="flex items-end gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
                {canAdmin ? (
                  <>
                    <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "oauth-start" })} disabled={!selectedIntegrationId}>Start flow</BrutalButton>
                    <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "oauth-callback" })}>Finish callback</BrutalButton>
                  </>
                ) : null}
              </div>
            </div>
            {!selectedIntegrationId ? (
              <p className="mb-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Select an integration in the Registry tab to start OAuth for it.</p>
            ) : null}
            <PanelBody loading={loading} error={oauthError} onRetry={() => void loadAll()} emptyTitle="No OAuth connections" emptyDescription="Start an OAuth flow to authorize a provider with PKCE. Tokens are never displayed.">
              {oauthList && oauthList.length > 0 ? (
                <ul className="space-y-2">
                  {oauthList.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedOAuthId(row.id)}
                        className={`block w-full border px-3 py-2 text-left ${row.id === selectedOAuthId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate text-sm font-bold text-on-surface">{row.provider || "oauth"}</span>
                          <BrutalBadge tone={statusTone(row.status)}>{row.status}</BrutalBadge>
                        </div>
                        <StatRow label="Client" value={row.client_id || "—"} />
                        <StatRow label="Token ref" value={row.token_ref || "—"} />
                        <StatRow label="Expires" value={formatDateTime(row.expires_at)} />
                      </button>
                      {canAdmin && row.id === selectedOAuthId ? (
                        <div className="flex flex-wrap gap-2 border border-t-0 border-outline-variant bg-surface px-3 py-2">
                          <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "oauth-refresh", oauth: row })}>Refresh</BrutalButton>
                          <BrutalButton variant="ghost" size="sm" onClick={() => openModal({ kind: "oauth-revoke", oauth: row })}>Revoke</BrutalButton>
                        </div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Flow" title="Authorization handoff">
            <p className="mb-3 text-xs text-on-surface-variant">Start returns an authorize URL. Complete it in the provider, then paste the returned state + code with Finish callback. Refresh renews tokens; revoke disables the connection. No token is ever rendered here — only references and expiry metadata.</p>
            {oauthStartResult ? (
              <div className="space-y-2 border border-outline bg-surface px-3 py-2">
                <StatRow label="OAuth ID" value={oauthStartResult.id} />
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Authorize URL</p>
                <p className="break-all font-mono text-xs text-on-surface">{oauthStartResult.authorize_url}</p>
                <a href={oauthStartResult.authorize_url} target="_blank" rel="noreferrer" className="inline-block border border-outline px-3 py-1 font-mono text-xs uppercase tracking-widest hover:border-primary-container">Open provider authorization</a>
              </div>
            ) : (
              <BrutalEmptyState title="No flow started" description="Use Start flow to generate a provider authorization URL." />
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "health" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Health" title="Connection health">
            <p className="mb-3 text-xs text-on-surface-variant">Runs a bounded health check through the governed outbound client and records the result. Select the connection in the Connections tab first.</p>
            <BrutalButton variant="primary" size="sm" onClick={() => void runConnectionHealth()} disabled={healthRunning || !selectedConnectionId}>
              {healthRunning ? "Checking…" : "Run health check"}
            </BrutalButton>
            {healthError ? <p className="mt-3 text-xs text-error">{healthError}</p> : null}
            {healthResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <PrimitiveRows data={healthResult} />
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Health" title="Connector health">
            <p className="mb-3 text-xs text-on-surface-variant">Connector-level check against the connector&apos;s declared health endpoint.</p>
            <BrutalButton variant="ghost" size="sm" onClick={() => void runConnectorHealth()} disabled={connectorHealthRunning || !selectedConnectionId}>
              {connectorHealthRunning ? "Checking…" : "Run connector check"}
            </BrutalButton>
            {connectorHealthError ? <p className="mt-3 text-xs text-error">{connectorHealthError}</p> : null}
            {connectorHealthResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <PrimitiveRows data={connectorHealthResult} />
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {active === "health" && selectedIntegrationId ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Summary" title="Health summary">
            <p className="mb-3 text-xs text-on-surface-variant">Aggregates health checks and execution outcomes for the selected integration. Window is bounded to 1–90 days.</p>
            <div className="mb-3 flex flex-wrap items-end gap-2">
              <div className="w-32">
                <BrutalInput label="Days" value={summaryDays} onChange={(e) => setSummaryDays(e.target.value)} placeholder="7" />
              </div>
              <BrutalButton variant="ghost" size="sm" onClick={() => void loadHealthSummary()} disabled={healthSummaryLoading}>
                {healthSummaryLoading ? "Loading…" : "Load summary"}
              </BrutalButton>
            </div>
            {healthSummaryLoading ? (
              <LoadingPanel />
            ) : healthSummaryError ? (
              <BrutalErrorState title="Unavailable" description={healthSummaryError} onRetry={() => void loadHealthSummary()} />
            ) : healthSummary ? (
              <div className="space-y-3">
                <StatRow label="Current health" value={healthSummary.current_health} />
                <StatRow label="Current status" value={healthSummary.current_status} />
                <StatRow label="Window" value={`${healthSummary.window_days} days`} />
                <StatRow label="Checks" value={String(healthSummary.checks)} />
                <StatRow label="Last check" value={formatDateTime(healthSummary.last_check)} />
                <StatRow label="Avg latency" value={healthSummary.avg_latency_ms !== null ? `${healthSummary.avg_latency_ms} ms` : "—"} />
                <StatRow label="Executions" value={String(healthSummary.executions)} />
                <StatRow label="Error rate" value={String(healthSummary.error_rate)} />
                <StatRow label="Auth failures" value={String(healthSummary.authentication_failures)} />
                <StatRow label="Rate-limit hits" value={String(healthSummary.rate_limit_hits)} />
              </div>
            ) : (
              <BrutalEmptyState title="No summary loaded" description="Load a summary for the selected integration." />
            )}
          </BrutalCard>
        </div>
      ) : null}

      {active === "webhooks" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Outbound" title="Webhooks">
            <div className="mb-3 flex flex-wrap gap-2">
              <div className="min-w-32 flex-1">
                <BrutalSelect label="Status" value={webhookStatusFilter} onChange={(e) => setWebhookStatusFilter(e.target.value)} options={[{ value: "ALL", label: "All statuses" }, ...INTEGRATION_STATUSES.map((s) => ({ value: s, label: s }))]} />
              </div>
              <div className="flex items-end gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => void loadAll()}>Apply</BrutalButton>
                {canAdmin ? (
                  <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "webhook-create" })}>Register</BrutalButton>
                ) : null}
              </div>
            </div>
            <PanelBody loading={loading} error={webhooksError} onRetry={() => void loadAll()} emptyTitle="No webhooks" emptyDescription="Register an outbound webhook with an http(s) URL. Secrets live encrypted server-side.">
              {webhooks && webhooks.length > 0 ? (
                <ul className="space-y-2">
                  {webhooks.map((wh) => (
                    <li key={wh.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedWebhookId(wh.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${wh.id === selectedWebhookId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{wh.name}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{wh.url} · {(wh.events ?? []).join(", ") || "all events"}</span>
                        </span>
                        <BrutalBadge tone={statusTone(wh.status)}>{wh.status}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
            {canAdmin && selectedWebhookId ? (
              <div className="mt-3 flex flex-wrap gap-2">
                <BrutalButton variant="ghost" size="sm" onClick={() => { const wh = webhooks?.find((w) => w.id === selectedWebhookId); if (wh) { setDraft((d) => ({ ...d, status: wh.status })); setModal({ kind: "webhook-status", webhook: wh }); } }}>Set status</BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => { const wh = webhooks?.find((w) => w.id === selectedWebhookId); if (wh) setModal({ kind: "webhook-deliver", webhook: wh }); }}>Send test delivery</BrutalButton>
                <BrutalButton variant="ghost" size="sm" onClick={() => { const wh = webhooks?.find((w) => w.id === selectedWebhookId); if (wh) setModal({ kind: "webhook-inbound", webhook: wh }); }}>Simulate inbound</BrutalButton>
              </div>
            ) : null}
          </BrutalCard>

          <BrutalCard eyebrow="Deliveries" title="Delivery history">
            <PanelBody loading={deliveriesLoading} error={deliveriesError} onRetry={() => selectedWebhookId && void loadDeliveries(selectedWebhookId)} emptyTitle="No deliveries" emptyDescription="Outbound deliveries with bounded retries and dead-letter state appear here.">
              {deliveries && deliveries.length > 0 ? (
                <ul className="space-y-2">
                  {deliveries.map((d) => (
                    <li key={d.id} className="border border-outline-variant bg-surface px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-xs text-on-surface">{d.event_type} · {d.attempts} attempts</span>
                        <BrutalBadge tone={d.status === "DELIVERED" ? "yellow" : d.status === "DEAD_LETTER" ? "error" : "default"}>{d.status}</BrutalBadge>
                      </div>
                      <StatRow label="Delivery ID" value={d.delivery_id} />
                      <StatRow label="Response" value={d.response_code !== null ? String(d.response_code) : "—"} />
                      {d.error ? <StatRow label="Error" value={d.error} /> : null}
                      <StatRow label="Next retry" value={formatDateTime(d.next_retry_at)} />
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Inbound" title="Received events">
            <PanelBody loading={inboundLoading} error={inboundError} onRetry={() => selectedWebhookId && void loadInbound(selectedWebhookId)} emptyTitle="No inbound events" emptyDescription="Verified inbound calls are deduplicated by delivery ID. Privileged operations become approval requests, never direct execution.">
              {inboundEvents && inboundEvents.length > 0 ? (
                <ul className="space-y-2">
                  {inboundEvents.map((ev) => (
                    <li key={ev.id} className="border border-outline-variant bg-surface px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate font-mono text-xs text-on-surface">{ev.event_type || "event"}</span>
                        <BrutalBadge tone={ev.status === "PENDING_APPROVAL" ? "error" : "default"}>{ev.status}</BrutalBadge>
                      </div>
                      <StatRow label="Delivery ID" value={ev.delivery_id} />
                      {ev.approval_id ? <StatRow label="Approval" value={ev.approval_id} /> : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>
        </div>
      ) : null}

      {active === "policies" ? (
        <div className="grid gap-6 lg:grid-cols-3">
          <BrutalCard eyebrow="Governance" title="Transfer policies">
            <div className="mb-3 flex gap-2">
              {canAdmin ? (
                <BrutalButton variant="primary" size="sm" onClick={() => openModal({ kind: "policy-create" })}>New policy</BrutalButton>
              ) : null}
            </div>
            <PanelBody loading={loading} error={policiesError} onRetry={() => void loadAll()} emptyTitle="No policies" emptyDescription="Policies govern outbound transfers. Matching BLOCK wins; secrets and tenant mismatch always block.">
              {policies && policies.length > 0 ? (
                <ul className="space-y-2">
                  {policies.map((p) => (
                    <li key={p.id}>
                      <button
                        type="button"
                        onClick={() => setSelectedPolicyId(p.id)}
                        className={`flex w-full items-center justify-between gap-2 border px-3 py-2 text-left ${p.id === selectedPolicyId ? "border-primary-container bg-surface" : "border-outline-variant bg-surface hover:border-outline"}`}
                      >
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-bold text-on-surface">{p.name}</span>
                          <span className="block truncate font-mono text-xs text-on-surface-variant">{p.provider || "*"} · {p.operation || "*"} · {p.action}</span>
                        </span>
                        <BrutalBadge tone={p.enabled ? (p.action === "block" ? "error" : "yellow") : "muted"}>{p.enabled ? p.action : "disabled"}</BrutalBadge>
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Detail" title="Selected policy">
            <PanelBody loading={loading} error={policiesError} onRetry={() => void loadAll()} emptyTitle="Nothing selected" emptyDescription="Select a policy to inspect its allowlists and limits.">
              {(() => {
                const policy = policies?.find((p) => p.id === selectedPolicyId) ?? null;
                if (!policy) return null;
                return (
                  <div className="space-y-3">
                    <StatRow label="Name" value={policy.name} />
                    <StatRow label="Action" value={policy.action} />
                    <StatRow label="Workspace" value={policy.workspace || "—"} />
                    <StatRow label="Project" value={policy.project || "—"} />
                    <StatRow label="Classifications" value={(policy.allowed_classifications ?? []).join(", ") || "—"} />
                    <StatRow label="Regions" value={(policy.allowed_regions ?? []).join(", ") || "—"} />
                    <StatRow label="Fields" value={(policy.allowed_fields ?? []).join(", ") || "—"} />
                    <StatRow label="Max cents" value={policy.max_estimated_cents !== null ? String(policy.max_estimated_cents) : "—"} />
                    <StatRow label="Owner" value={policy.owner || "—"} />
                    {canAdmin ? (
                      <div className="pt-2">
                        <BrutalButton variant="ghost" size="sm" onClick={() => {
                          setDraft((d) => ({
                            ...d,
                            policy_workspace: policy.workspace,
                            policy_project: policy.project,
                            policy_provider: policy.provider,
                            policy_operation: policy.operation,
                            policy_action: policy.action,
                            allowed_classifications: (policy.allowed_classifications ?? []).join(", "),
                            allowed_regions: (policy.allowed_regions ?? []).join(", "),
                            allowed_fields: (policy.allowed_fields ?? []).join(", "),
                            max_estimated_cents: policy.max_estimated_cents !== null ? String(policy.max_estimated_cents) : "",
                            policy_owner: policy.owner,
                            policy_enabled: policy.enabled ? "true" : "false",
                          }));
                          setModal({ kind: "policy-update", policy });
                        }}>Edit policy</BrutalButton>
                      </div>
                    ) : null}
                  </div>
                );
              })()}
            </PanelBody>
          </BrutalCard>

          <BrutalCard eyebrow="Evaluate" title="Transfer evaluation">
            <p className="mb-3 text-xs text-on-surface-variant">Dry-run a transfer against enabled policies. No data moves — the backend returns a decision with reasons.</p>
            <div className="space-y-2">
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Provider" value={evalDraft.provider} onChange={(e) => setEvalDraft((d) => ({ ...d, provider: e.target.value }))} placeholder="github" />
                <BrutalInput label="Operation" value={evalDraft.operation} onChange={(e) => setEvalDraft((d) => ({ ...d, operation: e.target.value }))} placeholder="sync" />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <BrutalInput label="Classification" value={evalDraft.classification} onChange={(e) => setEvalDraft((d) => ({ ...d, classification: e.target.value }))} placeholder="internal" />
                <BrutalInput label="Region" value={evalDraft.region} onChange={(e) => setEvalDraft((d) => ({ ...d, region: e.target.value }))} placeholder="eu-west" />
              </div>
              <BrutalInput label="Fields (comma-separated)" value={evalDraft.fields} onChange={(e) => setEvalDraft((d) => ({ ...d, fields: e.target.value }))} placeholder="id, name" />
              <BrutalInput label="Estimated cents" value={evalDraft.estimated_cents} onChange={(e) => setEvalDraft((d) => ({ ...d, estimated_cents: e.target.value }))} placeholder="0" />
              <BrutalButton variant="ghost" size="sm" onClick={() => void handleEvaluate()} disabled={evaluating}>
                {evaluating ? "Evaluating…" : "Evaluate"}
              </BrutalButton>
            </div>
            {evalError ? <p className="mt-3 text-xs text-error">{evalError}</p> : null}
            {evalResult ? (
              <div className="mt-3 border-t border-outline pt-2">
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Decision</span>
                  <BrutalBadge tone={evalResult.allowed ? "yellow" : "error"}>{evalResult.decision}</BrutalBadge>
                </div>
                {(evalResult.reasons ?? []).map((reason) => (
                  <p key={reason} className="text-xs text-on-surface-variant">· {reason}</p>
                ))}
              </div>
            ) : null}
          </BrutalCard>
        </div>
      ) : null}

      {active === "advanced" ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <BrutalCard eyebrow="Bridges" title="Cross-domain operations">
            <p className="mb-3 text-xs text-on-surface-variant">Thin adapters into FinOps, Knowledge, Workflow and AI governance. Each reuses the domain&apos;s authoritative service — no duplicated accounting or engines. Admin only.</p>
            {!canAdmin ? (
              <BrutalEmptyState title="Admin only" description="Bridge operations require settings:admin. The backend remains authoritative." />
            ) : (
              <div className="space-y-3">
                <BrutalInput label="Operation" value={bridgeDraft.operation} onChange={(e) => setBridgeDraft((d) => ({ ...d, operation: e.target.value }))} placeholder="integration.call" />
                <div className="grid grid-cols-3 gap-2">
                  <BrutalInput label="Requests" value={bridgeDraft.requests} onChange={(e) => setBridgeDraft((d) => ({ ...d, requests: e.target.value }))} />
                  <BrutalInput label="Bytes out" value={bridgeDraft.bytes_out} onChange={(e) => setBridgeDraft((d) => ({ ...d, bytes_out: e.target.value }))} />
                  <BrutalInput label="Est. cents" value={bridgeDraft.estimated_cents} onChange={(e) => setBridgeDraft((d) => ({ ...d, estimated_cents: e.target.value }))} />
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <BrutalInput label="Provider" value={bridgeDraft.provider} onChange={(e) => setBridgeDraft((d) => ({ ...d, provider: e.target.value }))} placeholder="integration" />
                  <BrutalInput label="Source name (knowledge)" value={bridgeDraft.name} onChange={(e) => setBridgeDraft((d) => ({ ...d, name: e.target.value }))} placeholder="vendor docs" />
                </div>
                <BrutalInput label="Target URL (AI action, https)" value={bridgeDraft.target_url} onChange={(e) => setBridgeDraft((d) => ({ ...d, target_url: e.target.value }))} placeholder="https://…" />
                <div className="grid grid-cols-2 gap-2">
                  <BrutalSelect label="Method (AI action)" value={bridgeDraft.method} onChange={(e) => setBridgeDraft((d) => ({ ...d, method: e.target.value }))} options={["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"].map((m) => ({ value: m, label: m }))} />
                  <BrutalInput label="Model (AI action)" value={bridgeDraft.model} onChange={(e) => setBridgeDraft((d) => ({ ...d, model: e.target.value }))} placeholder="policy model" />
                </div>
                <div className="flex flex-wrap gap-2">
                  <BrutalButton variant="ghost" size="sm" onClick={() => void runBridge("finops")} disabled={bridgeRunning || !selectedConnectionId}>Record usage</BrutalButton>
                  <BrutalButton variant="ghost" size="sm" onClick={() => void runBridge("knowledge")} disabled={bridgeRunning || !selectedIntegrationId}>Link knowledge</BrutalButton>
                  <BrutalButton variant="ghost" size="sm" onClick={() => void runBridge("workflow")} disabled={bridgeRunning || !selectedConnectionId}>Invoke workflow</BrutalButton>
                  <BrutalButton variant="ghost" size="sm" onClick={() => void runBridge("ai")} disabled={bridgeRunning}>AI action</BrutalButton>
                </div>
                <p className="font-mono text-xs text-on-surface-variant">FinOps/workflow need a selected connection; knowledge needs a selected integration.</p>
              </div>
            )}
          </BrutalCard>

          <BrutalCard eyebrow="Result" title="Bridge response">
            {bridgeRunning ? (
              <LoadingPanel />
            ) : bridgeError ? (
              <BrutalErrorState title="Bridge failed" description={bridgeError} onRetry={() => void runBridge("finops")} />
            ) : bridgeResult ? (
              <PrimitiveRows data={bridgeResult} />
            ) : (
              <BrutalEmptyState title="No bridge run" description="Run a bridge operation to see the authoritative domain response." />
            )}
          </BrutalCard>
        </div>
      ) : null}

      <BrutalModal open={modal?.kind === "integration-create"} title="Register integration" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleIntegrationCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} placeholder="github-prod" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Type" value={draft.type} onChange={(e) => setDraft((d) => ({ ...d, type: e.target.value }))} options={INTEGRATION_TYPES.map((t) => ({ value: t, label: t }))} />
            <BrutalInput label="Provider" value={draft.provider} onChange={(e) => setDraft((d) => ({ ...d, provider: e.target.value }))} placeholder="github" />
          </div>
          <p className="font-mono text-xs text-on-surface-variant">Allowed capabilities for {draft.type}: {(CAPABILITIES_BY_TYPE[draft.type as keyof typeof CAPABILITIES_BY_TYPE] ?? []).join(", ")}</p>
          <BrutalInput label="Capabilities (comma-separated)" value={draft.capabilities} onChange={(e) => setDraft((d) => ({ ...d, capabilities: e.target.value }))} placeholder="execute, sync, health" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft((d) => ({ ...d, workspace: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.environment} onChange={(e) => setDraft((d) => ({ ...d, environment: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Region" value={draft.region} onChange={(e) => setDraft((d) => ({ ...d, region: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
          </div>
          <BrutalInput label="Config (JSON object)" value={draft.config} onChange={(e) => setDraft((d) => ({ ...d, config: e.target.value }))} placeholder='{"base_url": "https://api.github.com"}' />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "integration-status"} title="Set integration status?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleIntegrationStatus()} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={INTEGRATION_STATUSES.map((s) => ({ value: s, label: s }))} />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "version-create"} title="Record version" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleVersionCreate()} disabled={submitting}>{submitting ? "Recording…" : "Record"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Version" value={draft.version} onChange={(e) => setDraft((d) => ({ ...d, version: e.target.value }))} placeholder="1.1.0" />
          <BrutalSelect label="Compatibility" value={draft.compatibility} onChange={(e) => setDraft((d) => ({ ...d, compatibility: e.target.value }))} options={["compatible", "deprecated", "breaking"].map((c) => ({ value: c, label: c }))} />
          <BrutalInput label="Contract (JSON object)" value={draft.contract} onChange={(e) => setDraft((d) => ({ ...d, contract: e.target.value }))} placeholder='{"capabilities": ["execute"]}' />
          <BrutalInput label="Migration notes" value={draft.migration_notes} onChange={(e) => setDraft((d) => ({ ...d, migration_notes: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "connector-register"} title="Register connector" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleConnectorRegister()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          {modal?.kind === "connector-register" ? <StatRow label="Connector" value={modal.connectorKey} /> : null}
          <BrutalInput label="Name" value={draft.name} onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))} placeholder="github-connector" />
          <BrutalInput label="Base URL (required for jira / generic_rest)" value={draft.base_url} onChange={(e) => setDraft((d) => ({ ...d, base_url: e.target.value }))} placeholder="https://…" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft((d) => ({ ...d, workspace: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.environment} onChange={(e) => setDraft((d) => ({ ...d, environment: e.target.value }))} />
          </div>
          <BrutalInput label="Owner" value={draft.owner} onChange={(e) => setDraft((d) => ({ ...d, owner: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "connector-connect"} title="Connect connector" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleConnectorConnect()} disabled={submitting}>{submitting ? "Connecting…" : "Connect"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">One-time secret: paste the credential material once. It is sent to the backend, encrypted at rest, and <span className="font-bold text-on-surface">never shown again</span> — only metadata references are returned.</p>
          <BrutalInput label="Credential material (one-time)" type="password" autoComplete="new-password" value={draft.material} onChange={(e) => setDraft((d) => ({ ...d, material: e.target.value }))} placeholder="••••••••" />
          <BrutalInput label="Endpoint ref (http/https only)" value={draft.endpoint_ref} onChange={(e) => setDraft((d) => ({ ...d, endpoint_ref: e.target.value }))} placeholder="https://api.github.com" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft((d) => ({ ...d, workspace: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.environment} onChange={(e) => setDraft((d) => ({ ...d, environment: e.target.value }))} />
          </div>
          <BrutalInput label="Auth config (JSON object)" value={draft.config} onChange={(e) => setDraft((d) => ({ ...d, config: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "connection-create"} title="New connection" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleConnectionCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Integration" value={selectedIntegrationId ?? "—"} />
          <BrutalInput label="Endpoint ref (http/https only)" value={draft.endpoint_ref} onChange={(e) => setDraft((d) => ({ ...d, endpoint_ref: e.target.value }))} placeholder="https://…" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.workspace} onChange={(e) => setDraft((d) => ({ ...d, workspace: e.target.value }))} />
            <BrutalInput label="Environment" value={draft.environment} onChange={(e) => setDraft((d) => ({ ...d, environment: e.target.value }))} />
          </div>
          <BrutalInput label="Scopes (comma-separated)" value={draft.scopes} onChange={(e) => setDraft((d) => ({ ...d, scopes: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "connection-status"} title="Set connection status?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleConnectionStatus()} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={INTEGRATION_STATUSES.map((s) => ({ value: s, label: s }))} />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "credential-create"} title="Store credential" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleCredentialCreate()} disabled={submitting}>{submitting ? "Storing…" : "Store once"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">One-time secret: the material is encrypted server-side and <span className="font-bold text-on-surface">never shown again</span>. Only a secret reference and hint are returned.</p>
          <BrutalSelect label="Kind" value={draft.kind} onChange={(e) => setDraft((d) => ({ ...d, kind: e.target.value }))} options={["api_key", "bearer", "basic", "oauth", "webhook_secret"].map((k) => ({ value: k, label: k }))} />
          <BrutalInput label="Material (one-time)" type="password" autoComplete="new-password" value={draft.material} onChange={(e) => setDraft((d) => ({ ...d, material: e.target.value }))} placeholder="••••••••" />
          <BrutalInput label="Scopes (comma-separated)" value={draft.scopes} onChange={(e) => setDraft((d) => ({ ...d, scopes: e.target.value }))} />
          <BrutalInput label="Expires at (ISO, optional)" value={draft.expires_at} onChange={(e) => setDraft((d) => ({ ...d, expires_at: e.target.value }))} placeholder="2027-01-01T00:00:00Z" />
          <BrutalInput label="Auth config (JSON object)" value={draft.config} onChange={(e) => setDraft((d) => ({ ...d, config: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "credential-rotate"} title="Rotate credential?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleCredentialRotate()} disabled={submitting}>{submitting ? "Rotating…" : "Rotate"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">Rotation creates a new credential row and revokes the old one. The new material is <span className="font-bold text-on-surface">never shown again</span>.</p>
          <BrutalInput label="New material (one-time)" type="password" autoComplete="new-password" value={draft.material} onChange={(e) => setDraft((d) => ({ ...d, material: e.target.value }))} placeholder="••••••••" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "oauth-start"} title="Start OAuth flow" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleOAuthStart()} disabled={submitting}>{submitting ? "Starting…" : "Start"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Integration" value={selectedIntegrationId ?? "—"} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.provider} onChange={(e) => setDraft((d) => ({ ...d, provider: e.target.value }))} placeholder="github" />
            <BrutalInput label="Client ID" value={draft.client_id} onChange={(e) => setDraft((d) => ({ ...d, client_id: e.target.value }))} />
          </div>
          <BrutalInput label="Scopes (comma-separated)" value={draft.scopesOAuth} onChange={(e) => setDraft((d) => ({ ...d, scopesOAuth: e.target.value }))} placeholder="read:user, repo" />
          <BrutalInput label="Redirect URI (https)" value={draft.redirect_uri} onChange={(e) => setDraft((d) => ({ ...d, redirect_uri: e.target.value }))} placeholder="https://app.example.com/oauth/callback" />
          <BrutalInput label="Authorization endpoint (https)" value={draft.authorization_endpoint} onChange={(e) => setDraft((d) => ({ ...d, authorization_endpoint: e.target.value }))} placeholder="https://github.com/login/oauth/authorize" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "oauth-callback"} title="Finish OAuth callback" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleOAuthCallback()} disabled={submitting}>{submitting ? "Exchanging…" : "Exchange code"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">Paste the state and code returned by the provider. The code is exchanged server-side; tokens are encrypted at rest and <span className="font-bold text-on-surface">never displayed</span>.</p>
          <BrutalInput label="State" value={draft.state} onChange={(e) => setDraft((d) => ({ ...d, state: e.target.value }))} />
          <BrutalInput label="Code (one-time)" type="password" autoComplete="off" value={draft.code} onChange={(e) => setDraft((d) => ({ ...d, code: e.target.value }))} />
          <BrutalInput label="Token endpoint (https)" value={draft.token_endpoint} onChange={(e) => setDraft((d) => ({ ...d, token_endpoint: e.target.value }))} placeholder="https://github.com/login/oauth/access_token" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "oauth-refresh"} title="Refresh OAuth token?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleOAuthRefresh()} disabled={submitting}>{submitting ? "Refreshing…" : "Refresh"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          {modal?.kind === "oauth-refresh" ? <StatRow label="OAuth ID" value={modal.oauth.id} /> : null}
          <BrutalInput label="Token endpoint (https)" value={draft.token_endpoint} onChange={(e) => setDraft((d) => ({ ...d, token_endpoint: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "oauth-revoke"} title="Revoke OAuth connection?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleOAuthRevoke()} disabled={submitting}>{submitting ? "Revoking…" : "Revoke"}</BrutalButton>
        </>
      }>
        <p className="text-sm text-on-surface-variant">The stored tokens are revoked and the connection can no longer authorize calls. This cannot be undone from here.</p>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "webhook-create"} title="Register webhook" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleWebhookCreate()} disabled={submitting}>{submitting ? "Registering…" : "Register"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.webhook_name} onChange={(e) => setDraft((d) => ({ ...d, webhook_name: e.target.value }))} placeholder="deploy-events" />
          <BrutalInput label="URL (http/https only)" value={draft.webhook_url} onChange={(e) => setDraft((d) => ({ ...d, webhook_url: e.target.value }))} placeholder="https://…" />
          <BrutalInput label="Events (comma-separated)" value={draft.webhook_events} onChange={(e) => setDraft((d) => ({ ...d, webhook_events: e.target.value }))} placeholder="push, deploy" />
          <BrutalInput label="Signing secret (one-time, optional)" type="password" autoComplete="new-password" value={draft.signing_secret} onChange={(e) => setDraft((d) => ({ ...d, signing_secret: e.target.value }))} placeholder="••••••••" />
          <p className="text-xs text-on-surface-variant">Linked to the selected integration{selectedIntegrationId ? "" : " (none selected — global webhook)"}.</p>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "webhook-status"} title="Set webhook status?" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleWebhookStatus()} disabled={submitting}>{submitting ? "Saving…" : "Confirm"}</BrutalButton>
        </>
      }>
        <BrutalSelect label="Status" value={draft.status} onChange={(e) => setDraft((d) => ({ ...d, status: e.target.value }))} options={INTEGRATION_STATUSES.map((s) => ({ value: s, label: s }))} />
      </BrutalModal>

      <BrutalModal open={modal?.kind === "webhook-deliver"} title="Send test delivery" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleWebhookDeliver()} disabled={submitting}>{submitting ? "Enqueuing…" : "Enqueue"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Event type" value={draft.event_type} onChange={(e) => setDraft((d) => ({ ...d, event_type: e.target.value }))} placeholder="deploy.finished" />
          <BrutalInput label="Payload (JSON object)" value={draft.payload} onChange={(e) => setDraft((d) => ({ ...d, payload: e.target.value }))} placeholder='{"ref": "main"}' />
          <BrutalInput label="Delivery ID (optional, idempotent)" value={draft.delivery_id} onChange={(e) => setDraft((d) => ({ ...d, delivery_id: e.target.value }))} />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "webhook-inbound"} title="Simulate inbound event" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleWebhookInboundTest()} disabled={submitting}>{submitting ? "Sending…" : "Simulate"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <p className="border border-outline bg-surface px-3 py-2 text-xs text-on-surface-variant">Runs the real inbound pipeline: signature verification, delivery-ID deduplication and normalization. Privileged operations become approval requests.</p>
          <BrutalInput label="Headers (JSON object)" value={draft.headers} onChange={(e) => setDraft((d) => ({ ...d, headers: e.target.value }))} placeholder='{"X-Webhook-Signature": "…"}' />
          <BrutalInput label="Body (JSON object)" value={draft.payload} onChange={(e) => setDraft((d) => ({ ...d, payload: e.target.value }))} placeholder='{"event": "push"}' />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Event type" value={draft.event_type} onChange={(e) => setDraft((d) => ({ ...d, event_type: e.target.value }))} />
            <BrutalInput label="Delivery ID" value={draft.delivery_id} onChange={(e) => setDraft((d) => ({ ...d, delivery_id: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "subscription-create"} title="Create subscription" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handleSubscriptionCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <StatRow label="Connection" value={selectedConnectionId ?? "—"} />
          <BrutalInput label="Target URL (http/https only)" value={draft.target_url} onChange={(e) => setDraft((d) => ({ ...d, target_url: e.target.value }))} placeholder="https://…" />
          <BrutalInput label="Event filter (JSON object)" value={draft.event_filter} onChange={(e) => setDraft((d) => ({ ...d, event_filter: e.target.value }))} placeholder="{}" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "policy-create"} title="New transfer policy" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePolicyCreate()} disabled={submitting}>{submitting ? "Creating…" : "Create"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <BrutalInput label="Name" value={draft.policy_name} onChange={(e) => setDraft((d) => ({ ...d, policy_name: e.target.value }))} placeholder="eu-pii-guard" />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.policy_workspace} onChange={(e) => setDraft((d) => ({ ...d, policy_workspace: e.target.value }))} />
            <BrutalInput label="Project" value={draft.policy_project} onChange={(e) => setDraft((d) => ({ ...d, policy_project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.policy_provider} onChange={(e) => setDraft((d) => ({ ...d, policy_provider: e.target.value }))} />
            <BrutalInput label="Operation" value={draft.policy_operation} onChange={(e) => setDraft((d) => ({ ...d, policy_operation: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Action" value={draft.policy_action} onChange={(e) => setDraft((d) => ({ ...d, policy_action: e.target.value }))} options={POLICY_ACTIONS.map((a) => ({ value: a, label: a }))} />
            <BrutalInput label="Owner" value={draft.policy_owner} onChange={(e) => setDraft((d) => ({ ...d, policy_owner: e.target.value }))} />
          </div>
          <BrutalInput label="Allowed classifications (comma-separated)" value={draft.allowed_classifications} onChange={(e) => setDraft((d) => ({ ...d, allowed_classifications: e.target.value }))} />
          <BrutalInput label="Allowed regions (comma-separated)" value={draft.allowed_regions} onChange={(e) => setDraft((d) => ({ ...d, allowed_regions: e.target.value }))} />
          <BrutalInput label="Allowed fields (comma-separated)" value={draft.allowed_fields} onChange={(e) => setDraft((d) => ({ ...d, allowed_fields: e.target.value }))} />
          <BrutalInput label="Max estimated cents" value={draft.max_estimated_cents} onChange={(e) => setDraft((d) => ({ ...d, max_estimated_cents: e.target.value }))} placeholder="1000" />
        </div>
      </BrutalModal>

      <BrutalModal open={modal?.kind === "policy-update"} title="Edit policy" onClose={() => setModal(null)} actions={
        <>
          <BrutalButton variant="ghost" size="sm" onClick={() => setModal(null)}>Cancel</BrutalButton>
          <BrutalButton variant="primary" size="sm" onClick={() => void handlePolicyUpdate()} disabled={submitting}>{submitting ? "Saving…" : "Save"}</BrutalButton>
        </>
      }>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <BrutalSelect label="Action" value={draft.policy_action} onChange={(e) => setDraft((d) => ({ ...d, policy_action: e.target.value }))} options={POLICY_ACTIONS.map((a) => ({ value: a, label: a }))} />
            <BrutalSelect label="Enabled" value={draft.policy_enabled} onChange={(e) => setDraft((d) => ({ ...d, policy_enabled: e.target.value }))} options={[{ value: "true", label: "enabled" }, { value: "false", label: "disabled" }]} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Workspace" value={draft.policy_workspace} onChange={(e) => setDraft((d) => ({ ...d, policy_workspace: e.target.value }))} />
            <BrutalInput label="Project" value={draft.policy_project} onChange={(e) => setDraft((d) => ({ ...d, policy_project: e.target.value }))} />
          </div>
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Provider" value={draft.policy_provider} onChange={(e) => setDraft((d) => ({ ...d, policy_provider: e.target.value }))} />
            <BrutalInput label="Operation" value={draft.policy_operation} onChange={(e) => setDraft((d) => ({ ...d, policy_operation: e.target.value }))} />
          </div>
          <BrutalInput label="Allowed classifications (comma-separated)" value={draft.allowed_classifications} onChange={(e) => setDraft((d) => ({ ...d, allowed_classifications: e.target.value }))} />
          <BrutalInput label="Allowed regions (comma-separated)" value={draft.allowed_regions} onChange={(e) => setDraft((d) => ({ ...d, allowed_regions: e.target.value }))} />
          <BrutalInput label="Allowed fields (comma-separated)" value={draft.allowed_fields} onChange={(e) => setDraft((d) => ({ ...d, allowed_fields: e.target.value }))} />
          <div className="grid grid-cols-2 gap-2">
            <BrutalInput label="Max estimated cents" value={draft.max_estimated_cents} onChange={(e) => setDraft((d) => ({ ...d, max_estimated_cents: e.target.value }))} />
            <BrutalInput label="Owner" value={draft.policy_owner} onChange={(e) => setDraft((d) => ({ ...d, policy_owner: e.target.value }))} />
          </div>
        </div>
      </BrutalModal>
    </div>
  );
}
