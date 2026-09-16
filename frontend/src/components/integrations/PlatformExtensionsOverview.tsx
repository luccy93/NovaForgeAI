"use client";

/* eslint-disable react-hooks/set-state-in-effect -- overview load on mount and tenant switch */
import { useCallback, useEffect, useRef, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";

interface OverviewCounts {
  integrations: number | null;
  connections: number | null;
  webhooks: number | null;
  policies: number | null;
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-outline py-1.5 last:border-b-0">
      <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</span>
      <span className="truncate font-mono text-sm text-on-surface" title={value}>
        {value}
      </span>
    </div>
  );
}

export function PlatformExtensionsOverview() {
  const [counts, setCounts] = useState<OverviewCounts>({ integrations: null, connections: null, webhooks: null, policies: null });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      setLoading(false);
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);

    async function safe<T>(fn: () => Promise<T>): Promise<T | null> {
      try {
        const v = await fn();
        if (controller.signal.aborted || seq !== seqRef.current) return null;
        return v;
      } catch (e) {
        if (controller.signal.aborted || seq !== seqRef.current) return null;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          useAuthStore.getState().markExpired();
          window.location.href = "/auth/login";
          return null;
        }
        if (e instanceof ApiError && e.kind === "forbidden") {
          setError("Backend denied access: additional authorization is required for your role.");
          return null;
        }
        if (e instanceof ApiError && e.status === 404) {
          setError("Not found on the backend.");
          return null;
        }
        return null;
      }
    }

    const [reg, conns, whs, pols] = await Promise.all([
      safe(() => api.integrationsFiltered(token, { limit: 100 })),
      safe(() => api.integrationConnections(token, {})),
      safe(() => api.integrationWebhooks(token, {})),
      safe(() => api.integrationPolicies(token)),
    ]);

    if (controller.signal.aborted || seq !== seqRef.current) return;

    const next: OverviewCounts = {
      integrations: reg && typeof reg.total === "number" ? reg.total : reg && Array.isArray((reg as { items?: unknown }).items) ? (reg as { items: unknown[] }).items.length : null,
      connections: (() => {
        if (!conns) return null;
        if (Array.isArray(conns)) return conns.length;
        if (typeof conns === "object" && conns !== null && "total" in conns && typeof (conns as { total?: unknown }).total === "number") return (conns as { total: number }).total;
        if (typeof conns === "object" && conns !== null && "items" in conns && Array.isArray((conns as { items?: unknown }).items)) return (conns as { items: unknown[] }).items.length;
        return null;
      })(),
      webhooks: whs && typeof whs.total === "number" ? whs.total : whs && Array.isArray((whs as { items?: unknown }).items) ? (whs as { items: unknown[] }).items.length : null,
      policies: pols && typeof pols.total === "number" ? pols.total : pols && Array.isArray((pols as { items?: unknown }).items) ? (pols as { items: unknown[] }).items.length : null,
    };

    setCounts(next);
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
    const onSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) abortRef.current.abort();
      setCounts({ integrations: null, connections: null, webhooks: null, policies: null });
      void load();
    };
    window.addEventListener("tenant:switched", onSwitch as EventListener);
    window.addEventListener("workspace:switched", onSwitch as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", onSwitch as EventListener);
      window.removeEventListener("workspace:switched", onSwitch as EventListener);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [load]);

  if (loading) {
    return (
      <div className="grid gap-6 md:grid-cols-2">
        <BrutalSkeleton className="h-40" />
        <BrutalSkeleton className="h-40" />
        <BrutalSkeleton className="h-40" />
        <BrutalSkeleton className="h-40" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {error ? <BrutalErrorState title="Extension overview unavailable" description={error} onRetry={() => void load()} /> : null}

      <div className="flex flex-wrap items-center gap-2 border border-outline bg-surface-container px-4 py-3">
        <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
          <span className="h-2 w-2 bg-muted" aria-hidden="true" />
          Realtime: UNAVAILABLE
        </span>
        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Tenant-scoped · server-authoritative</span>
      </div>

      <div className="grid gap-6 md:grid-cols-2">
        <BrutalCard eyebrow="Registry" title="Integration Registry">
          <StatRow label="Registered integrations" value={counts.integrations !== null ? String(counts.integrations) : "NOT EXPOSED BY API"} />
          <StatRow label="Versioning" value="Immutable releases" />
          <StatRow label="Source" value="GET /integrations" />
          <p className="mt-3 text-xs text-on-surface-variant">Only backend-reported totals are shown. Missing values are not rendered as zero.</p>
          <div className="mt-4">
            <BrutalButton href="/integrations" variant="ghost" size="sm">
              View registry
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Connections" title="Connections">
          <StatRow label="Active connections" value={counts.connections !== null ? String(counts.connections) : "NOT EXPOSED BY API"} />
          <StatRow label="Credential handling" value="Write-only, server-encrypted" />
          <StatRow label="Source" value="GET /integrations/connections/all" />
          <p className="mt-3 text-xs text-on-surface-variant">Credential material is never displayed after save and never logged.</p>
        </BrutalCard>

        <BrutalCard eyebrow="Webhooks" title="Webhooks & Sync">
          <StatRow label="Webhooks" value={counts.webhooks !== null ? String(counts.webhooks) : "NOT EXPOSED BY API"} />
          <StatRow label="Sync" value="Bounded, idempotent by sync_key" />
          <StatRow label="Deliveries" value="Bounded retry with dead-letter" />
          <p className="mt-3 text-xs text-on-surface-variant">Signing secrets are stored encrypted and never returned.</p>
        </BrutalCard>

        <BrutalCard eyebrow="Policies" title="Integration Policies">
          <StatRow label="Policies" value={counts.policies !== null ? String(counts.policies) : "NOT EXPOSED BY API"} />
          <StatRow label="Enforcement" value="V71 Governance + V64 Zero Trust" />
          <StatRow label="Evaluation" value="POST /integrations/policies/evaluate-transfer (read-gated)" />
          <p className="mt-3 text-xs text-on-surface-variant">No policy engine is duplicated in the frontend.</p>
        </BrutalCard>

        <BrutalCard eyebrow="Health" title="Connector Health">
          <div className="mb-3">
            <BrutalBadge tone="muted">Backend verbatim</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">Health is reported by the backend per-connection and per-integration. No health is calculated in the browser and no uptime percentages are synthesized.</p>
          <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Window 1–90 days · GET /integrations/integrations/{`{id}`}/health-summary</p>
        </BrutalCard>

        <BrutalCard eyebrow="Extension Surface" title="Cross-Domain Bridges">
          <p className="text-sm text-on-surface-variant">Bridges reuse existing domain services without duplicating their databases.</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>FinOps usage via governed gateway</li>
            <li>Knowledge source linking (deduped)</li>
            <li>Workflow invoke (policy-checked)</li>
            <li>AI request-action (host allowlist)</li>
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <BrutalButton href="/workflows" variant="ghost" size="sm">Workflows</BrutalButton>
            <BrutalButton href="/knowledge" variant="ghost" size="sm">Knowledge</BrutalButton>
            <BrutalButton href="/ai" variant="ghost" size="sm">AI</BrutalButton>
            <BrutalButton href="/code" variant="ghost" size="sm">Code</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="SDK">
          <p className="text-sm text-on-surface-variant">Build against NovaForge programmatically via the verified Python SDK.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">backend/sdk/integrations.py — IntegrationMixin (17 methods) · token via /auth/token-exchange</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View SDK Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="CLI">
          <p className="text-sm text-on-surface-variant">Manage supported platform operations from the command line.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">nova integrations list · cli/novaforge_cli.py · 30-volume orchestrator</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">CLI Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="MCP Servers">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">MCP server runtime is not exposed by the backend. Marketplace can register an mcp_server package type and validate it via /plugin/mcp/validate, but no MCP transport is available.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View MCP Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Platform" title="Plugins">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">No plugin registry is exposed for integrations. The platform plugin system (app/plugins) exists for other domains and is not duplicated here.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View Documentation</BrutalButton>
          </div>
        </BrutalCard>
      </div>

      <BrutalCard eyebrow="Handoffs" title="Platform Navigation">
        <p className="text-sm text-on-surface-variant">Extensions connect existing domains without duplicating their functionality.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <BrutalButton href="/integrations" variant="default" size="sm">Integrations</BrutalButton>
          <BrutalButton href="/workflows" variant="ghost" size="sm">Workflows</BrutalButton>
          <BrutalButton href="/knowledge" variant="ghost" size="sm">Knowledge</BrutalButton>
          <BrutalButton href="/ai" variant="ghost" size="sm">AI</BrutalButton>
          <BrutalButton href="/code" variant="ghost" size="sm">Code</BrutalButton>
          <BrutalButton href="/data" variant="ghost" size="sm">Data</BrutalButton>
          <BrutalButton href="/security" variant="ghost" size="sm">Security</BrutalButton>
          <BrutalButton href="/governance" variant="ghost" size="sm">Governance</BrutalButton>
          <BrutalButton href="/admin" variant="ghost" size="sm">Admin</BrutalButton>
          <BrutalButton href="/command" variant="ghost" size="sm">Command Center</BrutalButton>
        </div>
      </BrutalCard>

      <div className="border border-outline bg-surface-container px-4 py-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
        No plugin marketplace, no fake health, no synthetic execution metrics, no external URLs.
      </div>
    </div>
  );
}
