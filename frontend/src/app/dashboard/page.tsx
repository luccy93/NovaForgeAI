"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { CommandPalette } from "@/components/navigation/CommandPalette";
import { api, clearToken, getToken } from "@/lib/api";
import type { ApiUser, FinOpsSummary, KnowledgeHit } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";

export default function DashboardPage() {
  const [user, setUser] = useState<ApiUser | null>(null);
  const [summary, setSummary] = useState<FinOpsSummary | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<KnowledgeHit>>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const pushToast = useToastStore((state) => state.push);

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

  useEffect(() => {
    const token = getToken();
    if (!token) {
      window.location.href = "/auth/login";
      return;
    }
    (async () => {
      try {
        const [me, finops] = await Promise.all([api.me(token), api.finopsSummary(token)]);
        setUser(me);
        setSummary(finops);
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
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <AppShell
      email={email}
      workspaceLabel={email ? "Workspace" : null}
      onLogout={logout}
      onOpenPalette={() => setPaletteOpen(true)}
      onOpenSearch={() => setPaletteOpen(true)}
    >
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <PageFrame
        eyebrow="Console"
        title="Dashboard"
        description="Account, spend and knowledge — live from the NovaForge API."
        crumbs={[{ label: "Home", href: "/" }, { label: "Dashboard" }]}
      >
        {error ? (
          <div className="mb-6">
            <BrutalErrorState title="Request failed" description={error} onRetry={() => window.location.reload()} />
          </div>
        ) : null}
        <div className="grid gap-6 md:grid-cols-2">
          <BrutalCard eyebrow="Account" title={email ? String(user?.username ?? "Account") : "Account"}>
            {loading ? (
              <BrutalSkeleton className="h-16" />
            ) : user ? (
              <div className="space-y-1 text-body-md">
                <p>
                  <span className="text-on-surface-variant">Email: </span>
                  {String(user.email ?? "—")}
                </p>
                <p>
                  <span className="text-on-surface-variant">Username: </span>
                  {String(user.username ?? "—")}
                </p>
              </div>
            ) : (
              <BrutalEmptyState title="Not signed in" description="Sign in to load your account." />
            )}
          </BrutalCard>
          <BrutalCard eyebrow="FinOps" title="Usage">
            {loading ? (
              <BrutalSkeleton className="h-16" />
            ) : summary ? (
              <div className="space-y-1 text-body-md">
                <p>
                  <span className="text-on-surface-variant">Spend (cents): </span>
                  {String(summary.spend_cents ?? 0)}
                </p>
                <p>
                  <span className="text-on-surface-variant">Cost records: </span>
                  {String(summary.cost_records ?? 0)}
                </p>
                <p>
                  <span className="text-on-surface-variant">Total tokens: </span>
                  {String(summary.total_tokens ?? 0)}
                </p>
              </div>
            ) : (
              <BrutalEmptyState title="No usage yet" description="Usage appears here once recorded." />
            )}
          </BrutalCard>
        </div>
        <div className="mt-6">
          <BrutalCard eyebrow="Knowledge" title="Search">
            <div className="mb-4 flex flex-col gap-4 sm:flex-row">
              <div className="flex-1">
                <BrutalInput
                  aria-label="Search the knowledge base"
                  placeholder="Search the knowledge base…"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void onSearch();
                  }}
                />
              </div>
              <BrutalButton variant="yellow" size="md" onClick={() => void onSearch()}>
                {searching ? "Searching…" : "Search"}
              </BrutalButton>
            </div>
            {searching ? (
              <BrutalSkeleton className="h-24" label="Searching" />
            ) : results.length > 0 ? (
              <ul className="space-y-3">
                {results.map((r, i) => (
                  <li key={String(r.document_id ?? r.chunk_id ?? i)} className="border border-outline p-4">
                    <p className="font-bold text-on-surface">
                      {String(r.title ?? r.document_id ?? "Result")}
                    </p>
                    <p className="text-sm text-on-surface-variant">{String(r.snippet ?? r.citation ?? "")}</p>
                    <p className="mt-1 font-mono text-xs text-on-surface-variant">
                      score: {String(r.score ?? "—")}
                    </p>
                  </li>
                ))}
              </ul>
            ) : (
              <BrutalEmptyState title="No results yet" description="Try a search above." />
            )}
          </BrutalCard>
        </div>
      </PageFrame>
    </AppShell>
  );
}
