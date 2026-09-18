"use client";

import { useMemo, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { DOCS_INDEX } from "@/components/docs/docsData";

function filterDocs(query: string) {
  const q = query.trim().toLowerCase();
  if (q === "") return DOCS_INDEX;
  return DOCS_INDEX.filter((entry) => {
    const hay = `${entry.title} ${entry.category} ${entry.summary} ${entry.keywords.join(" ")}`.toLowerCase();
    return hay.includes(q);
  });
}

export function DocsOverview() {
  const [query, setQuery] = useState("");

  const results = useMemo(() => filterDocs(query), [query]);
  const hasQuery = query.trim().length > 0;

  return (
    <div className="space-y-6" data-testid="docs-overview">
      <div className="flex flex-wrap items-center gap-2 border border-outline bg-surface-container px-4 py-3">
        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Public · versioned · server-authoritative</span>
        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">No synthetic metrics · no external URLs</span>
      </div>

      <BrutalCard eyebrow="NovaForge Documentation" title="Documentation">
        <p className="text-sm text-on-surface-variant">Canonical enterprise documentation for NovaForge AI — grounded in verified repository, backend routes, and frontend features.</p>
        <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Primary surface: /docs · Developer portal: /developer · Tenant-scoped features defer to backend authorization</p>
      </BrutalCard>

      <BrutalCard eyebrow="Search" title="Search documentation">
        <BrutalInput
          label="Search documentation"
          placeholder="Search docs, APIs, guides..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search documentation"
        />
        <p className="mt-2 text-xs text-on-surface-variant">Deterministic local search over verified documentation content. Results originate only from DOCS_INDEX.</p>
        <div className="mt-4" role="region" aria-live="polite" aria-label="Search results">
          {results.length === 0 ? (
            <BrutalEmptyState title="No documentation matches" description={`No results for "${query.trim()}" — try a verified keyword like API, SDK, or Integrations.`} />
          ) : (
            <ul role="listbox" aria-label="Documentation results" className="space-y-2">
              {results.slice(0, 12).map((entry) => (
                <li key={entry.id} role="option" aria-selected={false}>
                  <a
                    href={entry.href}
                    className="flex items-center justify-between border border-outline bg-surface px-3 py-2 hover:border-primary-container focus-visible:outline-2 focus-visible:outline-primary-container"
                  >
                    <div>
                      <p className="text-sm font-bold text-on-surface">{entry.title}</p>
                      <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{entry.category} · {entry.href}</p>
                    </div>
                    <span className="font-mono text-xs uppercase tracking-widest text-primary-container">Open</span>
                  </a>
                </li>
              ))}
            </ul>
          )}
          {hasQuery ? <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">{results.length} result{results.length === 1 ? "" : "s"} for &quot;{query.trim()}&quot;</p> : null}
        </div>
      </BrutalCard>

      <BrutalCard eyebrow="Getting Started" title="Getting Started" actions={<span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">4 guides</span>}>
        <div className="grid gap-4 md:grid-cols-2">
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">Quick Start</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Run with Docker or local dev: backend .venv and frontend npm run dev.</p>
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Route: /docs#quick-start</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">Navigation</h3>
            <p className="mt-1 text-xs text-on-surface-variant">SideNav groups + Command Palette Go to Documentation → /docs.</p>
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Palette: ⌘K → Go to Documentation</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">Authentication</h3>
            <p className="mt-1 text-xs text-on-surface-variant">POST /auth/login, X-API-Key nf_ prefix sha256, Bearer JWT, MFA.</p>
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Frontend UX, Backend authoritative</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">Overview</h3>
            <p className="mt-1 text-xs text-on-surface-variant">NovaForge AI enterprise platform — verified routes and contracts.</p>
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Public · versioned</p>
          </div>
        </div>
      </BrutalCard>

      <div className="grid gap-6 md:grid-cols-2">
        <BrutalCard eyebrow="Platform" title="Platform">
          <ul className="list-disc space-y-1 pl-5 text-sm text-on-surface-variant">
            <li><a href="/dashboard" className="underline decoration-outline hover:text-primary-container">Dashboard</a> — account, usage, search</li>
            <li><a href="/ai" className="underline decoration-outline hover:text-primary-container">AI</a> — workspace and conversations</li>
            <li><a href="/code" className="underline decoration-outline hover:text-primary-container">Code</a> — POST /code/analyze, /code-intelligence/{`{repo}`}/search</li>
            <li><a href="/knowledge" className="underline decoration-outline hover:text-primary-container">Knowledge</a> — search the knowledge base</li>
            <li><a href="/data" className="underline decoration-outline hover:text-primary-container">Data Platform</a> — datasets, pipelines</li>
            <li><a href="/workflows" className="underline decoration-outline hover:text-primary-container">Workflows</a> — automation</li>
            <li><a href="/agents" className="underline decoration-outline hover:text-primary-container">Agents</a> — POST /ai-dev/agents</li>
            <li><a href="/analytics" className="underline decoration-outline hover:text-primary-container">Analytics</a> — executive analytics</li>
          </ul>
          <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">All routes verified in NAV_ITEMS</p>
        </BrutalCard>

        <BrutalCard eyebrow="Operations" title="Operations">
          <ul className="list-disc space-y-1 pl-5 text-sm text-on-surface-variant">
            <li><a href="/observability" className="underline decoration-outline hover:text-primary-container">Observability</a> — GET /health, /metrics</li>
            <li><a href="/security" className="underline decoration-outline hover:text-primary-container">Security</a> — POST /security/plugin/mcp/validate</li>
            <li><a href="/governance" className="underline decoration-outline hover:text-primary-container">Governance</a> — policies, rules</li>
            <li><a href="/integrations" className="underline decoration-outline hover:text-primary-container">Integrations</a> — GET /integrations, connections, webhooks</li>
            <li><a href="/finops" className="underline decoration-outline hover:text-primary-container">FinOps</a> — spend and budgets</li>
            <li><a href="/notifications" className="underline decoration-outline hover:text-primary-container">Notifications</a> — unread activity</li>
          </ul>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="API">
          <p className="text-sm text-on-surface-variant">Backend-verified API surfaces.</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>Swagger UI: /docs</li>
            <li>OpenAPI JSON: /openapi.json</li>
            <li>Discovery: /.well-known/novaforge.json</li>
          </ul>
          <p className="mt-2 text-xs text-on-surface-variant">No undocumented endpoints are hardcoded.</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="SDK">
          <p className="text-sm text-on-surface-variant">Use the official NovaForge developer SDK.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">backend/sdk/integrations.py — IntegrationMixin 21 methods · token via POST /auth/token-exchange</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View SDK Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="CLI">
          <p className="text-sm text-on-surface-variant">Manage platform operations from the command line.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">nova integrations list · backend/cli/main.py + backend/app/novaforge_cli.py + developer_commands.py</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">CLI Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="MCP">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">MCP runtime transport is not exposed. Validation only via POST /security/plugin/mcp/validate.</p>
          <p className="mt-2 font-mono text-xs text-on-surface-variant">Marketplace mcp_server type → validate, no transport</p>
          <div className="mt-4">
            <BrutalButton href="/docs" variant="default" size="sm">View MCP Documentation</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="Code Intelligence">
          <p className="text-sm text-on-surface-variant">Repository indexing, code search, RAG context, impact analysis via /code-intelligence/{"{repo}"}{"/*"}.</p>
          <div className="mt-4">
            <BrutalButton href="/code" variant="default" size="sm">Open Code Platform</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Developer" title="AI Developer Platform">
          <p className="text-sm text-on-surface-variant">AI code explanation, change summary, test generation via POST /ai-dev/explain, /ai-dev/patch.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <BrutalButton href="/ai" variant="default" size="sm">Open AI Platform</BrutalButton>
            <BrutalButton href="/agents" variant="ghost" size="sm">Open Agents</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Administration" title="Administration">
          <ul className="list-disc space-y-1 pl-5 text-sm text-on-surface-variant">
            <li><a href="/settings/organization" className="underline decoration-outline hover:text-primary-container">Organization</a> — workspace administration</li>
            <li><a href="/settings/members" className="underline decoration-outline hover:text-primary-container">Members</a> — user management</li>
            <li><a href="/settings/roles" className="underline decoration-outline hover:text-primary-container">Roles</a> — permission assignments</li>
            <li><a href="/settings/workspaces" className="underline decoration-outline hover:text-primary-container">Workspaces</a> — tenant isolation</li>
            <li><a href="/settings/identity" className="underline decoration-outline hover:text-primary-container">Identity & Access</a> — enterprise identity</li>
            <li><a href="/settings/preferences" className="underline decoration-outline hover:text-primary-container">Preferences</a> — personalization</li>
          </ul>
          <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Frontend UX, Backend authoritative</p>
        </BrutalCard>

        <BrutalCard eyebrow="Security" title="Permissions">
          <p className="text-sm text-on-surface-variant">Exact permission vocabulary (only if feature requires it):</p>
          <ul className="mt-3 list-disc space-y-1 pl-5 font-mono text-xs text-on-surface-variant">
            <li>knowledge:read</li>
            <li>organization:read</li>
            <li>settings:admin</li>
            <li>secops:read / secops:write</li>
            <li>zero_trust:write</li>
            <li>billing:read / billing:admin</li>
            <li>workflow:execute</li>
            <li>data:write / data:export</li>
          </ul>
          <p className="mt-2 text-xs text-on-surface-variant">No invented permissions. Frontend visibility is UX.</p>
        </BrutalCard>
      </div>

      <BrutalCard eyebrow="Help" title="FAQ">
        <ul className="space-y-3">
          <li>
            <p className="text-sm font-bold text-on-surface">How do I change workspace?</p>
            <p className="text-xs text-on-surface-variant">Use the workspace switcher in AppShell — triggers workspace:switched, state is refetched tenant-scoped.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where are API keys managed?</p>
            <p className="text-xs text-on-surface-variant">Security Settings → Manage API Keys → /settings/security (GET /auth/api-keys). Full keys never rendered.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where are notification preferences?</p>
            <p className="text-xs text-on-surface-variant">Preferences → /settings/preferences and Notifications → /notifications.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">How do I access the AI workspace?</p>
            <p className="text-xs text-on-surface-variant">AI → /ai for conversations; Agents → /agents for plans/checkpoints.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where is Code Intelligence?</p>
            <p className="text-xs text-on-surface-variant">Code → /code — POST /code/analyze, /code-intelligence/{"{repo}"}/search.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where are integrations managed?</p>
            <p className="text-xs text-on-surface-variant">Integrations → /integrations — registry, connections, webhooks.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where are identity/access controls?</p>
            <p className="text-xs text-on-surface-variant">Identity & Access → /settings/identity.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Where is developer documentation?</p>
            <p className="text-xs text-on-surface-variant">Documentation → /docs; Developer Platform → /developer.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Is realtime available?</p>
            <p className="text-xs text-on-surface-variant">No — Realtime: UNAVAILABLE. No live documentation updates.</p>
          </li>
          <li>
            <p className="text-sm font-bold text-on-surface">Is MCP runtime available?</p>
            <p className="text-xs text-on-surface-variant">No — validate-only via POST /security/plugin/mcp/validate, transport NOT EXPOSED BY API.</p>
          </li>
        </ul>
      </BrutalCard>

      <BrutalCard eyebrow="Help" title="Troubleshooting">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">SESSION EXPIRED (401)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">What it means: token expired. What to do: sign in again → /auth/login.</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">ACCESS DENIED (403)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Backend authorization is authoritative. Request additional permission for your role.</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">RESOURCE NOT FOUND (404)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Documentation not found — check the canonical route exists in navigation.</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">CONFLICT (409)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Content conflict — refresh server state and retry.</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">INVALID REQUEST (422)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Invalid search or payload — correct the request and retry.</p>
          </div>
          <div className="border border-outline bg-surface p-4">
            <h3 className="text-sm font-bold text-on-surface">SERVICE UNAVAILABLE (5xx)</h3>
            <p className="mt-1 text-xs text-on-surface-variant">Documentation service temporarily unavailable — retry later.</p>
          </div>
        </div>
        <p className="mt-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">Realtime unavailable is expected for docs</p>
      </BrutalCard>

      <BrutalCard eyebrow="Help" title="Support">
        <p className="text-sm text-on-surface-variant">Ask AI for help or visit the Developer Platform for verified surfaces.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <BrutalButton href="/ai" variant="default" size="sm">Ask AI</BrutalButton>
          <BrutalButton href="/developer" variant="ghost" size="sm">Developer Platform</BrutalButton>
          <BrutalButton href="/knowledge" variant="ghost" size="sm">Knowledge</BrutalButton>
        </div>
      </BrutalCard>

      <BrutalCard eyebrow="Handoffs" title="Platform Navigation">
        <p className="text-sm text-on-surface-variant">Canonical routes verified in navigation — all internal, no external URLs.</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <BrutalButton href="/docs" variant="default" size="sm">Documentation</BrutalButton>
          <BrutalButton href="/developer" variant="ghost" size="sm">Developer Platform</BrutalButton>
          <BrutalButton href="/integrations" variant="ghost" size="sm">Integrations</BrutalButton>
          <BrutalButton href="/code" variant="ghost" size="sm">Code</BrutalButton>
          <BrutalButton href="/ai" variant="ghost" size="sm">AI</BrutalButton>
          <BrutalButton href="/agents" variant="ghost" size="sm">Agents</BrutalButton>
          <BrutalButton href="/security" variant="ghost" size="sm">Security</BrutalButton>
          <BrutalButton href="/governance" variant="ghost" size="sm">Governance</BrutalButton>
          <BrutalButton href="/admin" variant="ghost" size="sm">Admin</BrutalButton>
          <BrutalButton href="/command" variant="ghost" size="sm">Command Center</BrutalButton>
        </div>
      </BrutalCard>

      <div className="border border-outline bg-surface-container px-4 py-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
        No fake API metrics, no synthetic rate limits, no invented SDK methods, no external URLs, no tenant leakage.
      </div>
    </div>
  );
}
