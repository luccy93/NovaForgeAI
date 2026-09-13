"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { NAV_GROUPS, NAV_ITEMS, filterNavByPermission } from "@/lib/navigation";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import type { KnowledgeSearchItem } from "@/types/knowledge";
import type { CatalogHit } from "@/types/universal";

interface SearchState {
  query: string;
  knowledge: Array<KnowledgeSearchItem>;
  catalog: Array<CatalogHit>;
  searching: boolean;
  error: string | null;
}

const INITIAL_SEARCH: SearchState = {
  query: "",
  knowledge: [],
  catalog: [],
  searching: false,
  error: null,
};

export function CommandCenter() {
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [search, setSearch] = useState<SearchState>(INITIAL_SEARCH);
  const controllerRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);

  const sessionExpired = useCallback(() => {
    clearToken();
    window.location.href = "/auth/login";
  }, []);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    api
      .whoami(token)
      .then((who) => setPermissions(who.permissions ?? []))
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          window.location.href = "/auth/login";
        }
      });
  }, []);

  useEffect(() => {
    function onSwitch() {
      controllerRef.current?.abort();
      setSearch((prev) => ({ ...prev, knowledge: [], catalog: [], error: null, searching: false }));
    }
    window.addEventListener("tenant:switched", onSwitch);
    window.addEventListener("workspace:switched", onSwitch);
    return () => {
      window.removeEventListener("tenant:switched", onSwitch);
      window.removeEventListener("workspace:switched", onSwitch);
    };
  }, []);

  async function runSearch() {
    const token = getToken();
    const query = search.query.trim();
    if (!token) {
      window.location.href = "/auth/login";
      return;
    }
    if (query.length === 0) {
      setSearch((prev) => ({ ...prev, knowledge: [], catalog: [], error: null }));
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    const seq = ++seqRef.current;
    setSearch((prev) => ({ ...prev, searching: true, error: null }));
    try {
      const [knowledge, catalog] = await Promise.all([
        api.knowledgeSearch(token, query, { limit: 5, signal: controller.signal }),
        api.dataCatalogSearch(token, query, { limit: 5 }),
      ]);
      if (seq !== seqRef.current) return;
      setSearch((prev) => ({ ...prev, knowledge: knowledge.items ?? [], catalog: catalog.items ?? [] }));
    } catch (e) {
      if (seq !== seqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      const message =
        e instanceof ApiError && e.status === 403
          ? "Your session lacks permission for this search."
          : e instanceof Error
            ? e.message
            : "Search failed";
      setSearch((prev) => ({ ...prev, error: message }));
    } finally {
      if (seq === seqRef.current) setSearch((prev) => ({ ...prev, searching: false }));
    }
  }

  const visibleNavigation = filterNavByPermission(NAV_ITEMS, permissions);
  const groupedNavigation = NAV_GROUPS.map(({ id, label }) => ({
    id,
    label,
    items: visibleNavigation.filter((item) => item.group === id),
  })).filter((group) => group.items.length > 0);

  const orgLabel = organizationId ? `Org ${organizationId.slice(0, 8)}` : "No org";
  const wsLabel = workspaceId ? `WS ${workspaceId.slice(0, 8)}` : "No workspace";

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <BrutalCard eyebrow="Global search" title="Search the platform">
            <p className="mb-4 text-sm text-on-surface-variant">
              Searches the tenant-scoped knowledge base and data catalog. Global code, incident,
              security and workflow search are not exposed by a safe IAM-scoped contract.
            </p>
            <div className="mb-4 flex flex-col gap-4 sm:flex-row">
              <BrutalInput
                aria-label="Command center search query"
                placeholder="Search knowledge and data catalog…"
                value={search.query}
                onChange={(e) => setSearch((prev) => ({ ...prev, query: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void runSearch();
                }}
              />
              <BrutalButton variant="yellow" size="md" onClick={() => void runSearch()}>
                {search.searching ? "Searching…" : "Search"}
              </BrutalButton>
            </div>
            {search.error ? (
              <BrutalErrorState title="Search failed" description={search.error} onRetry={() => void runSearch()} />
            ) : search.searching ? (
              <p className="font-mono text-xs text-on-surface-variant">Searching…</p>
            ) : search.knowledge.length === 0 && search.catalog.length === 0 ? (
              <BrutalEmptyState title="Search the platform" description="Results appear here from the knowledge base and data catalog." />
            ) : (
              <div className="space-y-4">
                {search.knowledge.length > 0 ? (
                  <div>
                    <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Knowledge</p>
                    <ul className="space-y-2">
                      {search.knowledge.map((item) => (
                        <li key={String(item.document_id ?? item.chunk_id)} className="border border-outline p-3">
                          <p className="font-bold text-on-surface">{String(item.title ?? item.document_id ?? "Result")}</p>
                          <p className="text-sm text-on-surface-variant">{String(item.snippet ?? "")}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
                {search.catalog.length > 0 ? (
                  <div>
                    <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Data catalog</p>
                    <ul className="space-y-2">
                      {search.catalog.map((item) => (
                        <li key={item.id} className="border border-outline p-3">
                          <p className="font-bold text-on-surface">{String(item.name ?? item.id)}</p>
                          <p className="text-sm text-on-surface-variant">
                            {[item.description, item.owner, item.classification].filter(Boolean).join(" · ") || "Catalog entry"}
                          </p>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </div>
            )}
          </BrutalCard>
        </div>
        <div className="space-y-6">
          <BrutalCard eyebrow="Discover" title="Command workspaces">
            <ul className="space-y-2">
              <li>
                <Link href="/knowledge/universal" className="block border border-outline p-3 hover:border-primary-container">
                  <p className="font-bold text-on-surface">Global Search</p>
                  <p className="text-sm text-on-surface-variant">Universal search surface.</p>
                </Link>
              </li>
              <li>
                <Link href="/ai" className="block border border-outline p-3 hover:border-primary-container">
                  <p className="font-bold text-on-surface">Ask AI</p>
                  <p className="text-sm text-on-surface-variant">Open the AI workspace.</p>
                </Link>
              </li>
            </ul>
          </BrutalCard>
          <BrutalCard eyebrow="Platform" title="Status">
            <p className="text-sm text-on-surface-variant">{orgLabel} · {wsLabel}</p>
            <p className="mt-2 font-mono text-xs uppercase tracking-widest text-muted">Realtime: unavailable</p>
            <p className="mt-2 text-sm text-on-surface-variant">
              No global backend realtime subscription is exposed, so no live status is fabricated here.
            </p>
          </BrutalCard>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <BrutalCard eyebrow="Navigation" title="Workspaces">
            <div className="grid gap-4 md:grid-cols-2">
              {groupedNavigation.map((group) => (
                <div key={group.id}>
                  <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                    {group.label}
                  </p>
                  <ul className="space-y-1">
                    {group.items.map((item) => (
                      <li key={item.id}>
                        <Link href={item.href} className="block border-l-2 border-transparent px-3 py-2 text-sm text-on-surface-variant hover:border-primary-container hover:text-on-surface">
                          {item.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </BrutalCard>
        </div>
        <div className="space-y-6">
          <BrutalCard eyebrow="Recent" title="Recent activity">
            <BrutalEmptyState title="Not exposed by API" description="Recent activity has no safe IAM-scoped contract, so this surface stays honestly empty instead of fabricating cross-tenant data." />
          </BrutalCard>
          <BrutalButton variant="ghost" size="md" href="/dashboard">
            Return to Dashboard
          </BrutalButton>
        </div>
      </div>
    </div>
  );
}