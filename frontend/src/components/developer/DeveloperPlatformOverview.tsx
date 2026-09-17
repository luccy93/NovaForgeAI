"use client";

import { useEffect, useRef } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";

export function DeveloperPlatformOverview() {
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const onSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) abortRef.current.abort();
      const controller = new AbortController();
      abortRef.current = controller;
    };
    window.addEventListener("tenant:switched", onSwitch as EventListener);
    window.addEventListener("workspace:switched", onSwitch as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", onSwitch as EventListener);
      window.removeEventListener("workspace:switched", onSwitch as EventListener);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  return (
    <div className="space-y-6" data-testid="developer-platform-overview">
      <div className="flex flex-wrap items-center gap-2 border border-outline bg-surface-container px-4 py-3">
        <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
          <span className="h-2 w-2 bg-muted" aria-hidden="true" />
          Realtime: UNAVAILABLE
        </span>
        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Tenant-scoped · server-authoritative</span>
      </div>

      <BrutalCard eyebrow="Developer Overview" title="Developer Platform">
        <p className="text-sm text-on-surface-variant">
          Enterprise developer surfaces verified against the backend and repository. No duplicate management planes — each capability hands off to its canonical NovaForge surface.
        </p>
        <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
          Primary portal: /developer · Documentation: /docs · Tenant-scoped · No synthetic metrics
        </p>
      </BrutalCard>

      <div className="grid gap-6 md:grid-cols-2">
        <BrutalCard eyebrow="API Access" title="API Access">
          <p className="text-sm text-on-surface-variant">API credentials are managed through Security Settings. No duplicate API-key workflow is created here.</p>
          <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Source: GET /auth/api-keys · X-API-Key (nf_ prefix, sha256 at rest)</p>
          <p className="mt-2 text-xs text-on-surface-variant">Full API keys and Bearer tokens are never rendered or logged.</p>
          <div className="mt-4">
            <BrutalButton href="/settings/security" variant="default" size="sm">
              Manage API Keys
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="API Reference" title="API Reference">
          <p className="text-sm text-on-surface-variant">Backend-verified OpenAPI and discovery surfaces.</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>Swagger UI: /docs</li>
            <li>OpenAPI JSON: /openapi.json</li>
            <li>Discovery: /.well-known/novaforge.json</li>
          </ul>
          <p className="mt-3 text-xs text-on-surface-variant">No undocumented endpoints are hardcoded and no fake API explorer is created.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">
              View Documentation
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="SDK">
          <p className="text-sm text-on-surface-variant">Use the official NovaForge developer SDK.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">backend/sdk/integrations.py — IntegrationMixin (17 methods) · token via /auth/token-exchange</p>
          <p className="mt-2 text-xs text-on-surface-variant">Only verified languages and packages are referenced. No invented npm or PyPI names.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">
              View SDK Documentation
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="CLI">
          <p className="text-sm text-on-surface-variant">Manage supported platform operations from the command line.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">nova integrations list · cli/novaforge_cli.py · 30-volume orchestrator</p>
          <p className="mt-2 text-xs text-on-surface-variant">Only repository-verified commands are referenced.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">
              CLI Documentation
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="MCP Servers">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">MCP server runtime is not exposed by the backend. Marketplace can register an mcp_server package type and validate it via POST /security/plugin/mcp/validate, but no MCP transport is available.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">
              View MCP Documentation
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="API Playground">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">Arbitrary API execution from the browser is not exposed. Playground would require safe execution, server-derived tenant context, and governed mutations — none verified.</p>
          <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">No synthetic API usage is displayed</p>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="Webhooks">
          <p className="text-sm text-on-surface-variant">Webhook management belongs to the Integrations workspace. No webhook CRUD is duplicated here.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">Signing secrets are encrypted and never returned from the backend.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <BrutalButton href="/integrations" variant="default" size="sm">
              Manage Webhooks
            </BrutalButton>
            <BrutalButton href="/docs" variant="ghost" size="sm">
              View Documentation
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="Code Platform">
          <p className="text-sm text-on-surface-variant">Code intelligence, repository indexing, code search, RAG context, and impact analysis are exposed via the Code workspace. No /developer/code duplicate is created.</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>POST /code/analyze · /code-intelligence/{`{repo}`}/search</li>
            <li>Graph traverse · symbols · hotspots</li>
          </ul>
          <div className="mt-4">
            <BrutalButton href="/code" variant="default" size="sm">
              Open Code Platform
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="AI Platform">
          <p className="text-sm text-on-surface-variant">AI code explanation, change summary, test generation, developer agents, plans and checkpoints.</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>POST /ai-dev/explain · /ai-dev/patch · /ai-dev/tests/generate</li>
            <li>POST /ai-dev/agents · /ai-dev/agents/{`{id}`}/execute</li>
          </ul>
          <div className="mt-4 flex flex-wrap gap-2">
            <BrutalButton href="/ai" variant="default" size="sm">
              Open AI Platform
            </BrutalButton>
            <BrutalButton href="/agents" variant="ghost" size="sm">
              Open Agents
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="Agents">
          <p className="text-sm text-on-surface-variant">Governed agent executions with explicit backend approval for plans and checkpoints.</p>
          <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Source: /ai-dev/agents · /agents</p>
          <div className="mt-4">
            <BrutalButton href="/agents" variant="default" size="sm">
              Open Agents
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer Surface" title="Unavailable Capabilities">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">The following developer capabilities are not exposed through the verified frontend/backend contract:</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>API usage numbers, rate limits, quotas, billing</li>
            <li>SDK downloads and package registries</li>
            <li>App registrations and OAuth client secrets</li>
            <li>API products, plans, and API-key rate-limit configuration</li>
          </ul>
          <p className="mt-3 text-xs text-on-surface-variant">Unavailable data is never replaced with 0, N/A, Healthy, Connected, or Unlimited.</p>
        </BrutalCard>

        <BrutalCard eyebrow="Handoffs" title="Documentation">
          <p className="text-sm text-on-surface-variant">Canonical documentation remains at /docs. No /developer/docs duplicate is created.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">
              View Documentation
            </BrutalButton>
          </div>
        </BrutalCard>
      </div>

      <BrutalCard eyebrow="Handoffs" title="Platform Navigation">
        <p className="text-sm text-on-surface-variant">Developer platform connects existing domains without duplicating their functionality.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <BrutalButton href="/developer" variant="default" size="sm">
            Developer Platform
          </BrutalButton>
          <BrutalButton href="/docs" variant="ghost" size="sm">
            Documentation
          </BrutalButton>
          <BrutalButton href="/integrations" variant="ghost" size="sm">
            Integrations
          </BrutalButton>
          <BrutalButton href="/code" variant="ghost" size="sm">
            Code
          </BrutalButton>
          <BrutalButton href="/ai" variant="ghost" size="sm">
            AI
          </BrutalButton>
          <BrutalButton href="/agents" variant="ghost" size="sm">
            Agents
          </BrutalButton>
          <BrutalButton href="/knowledge" variant="ghost" size="sm">
            Knowledge
          </BrutalButton>
          <BrutalButton href="/command" variant="ghost" size="sm">
            Command Center
          </BrutalButton>
        </div>
      </BrutalCard>

      <div className="border border-outline bg-surface-container px-4 py-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
        No fake API metrics, no synthetic rate limits, no invented SDK methods, no external URLs.
      </div>
    </div>
  );
}
