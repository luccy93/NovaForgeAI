"use client";

import { useEffect, useState } from "react";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { api, clearToken, getToken } from "@/lib/api";

const cardCls = "border border-outline bg-surface-container p-6 text-left";
const inputCls =
  "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none focus:border-primary-container transition-colors";

export default function DashboardPage() {
  const [user, setUser] = useState<Record<string, unknown> | null>(null);
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);

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
        setError(e instanceof Error ? e.message : "Failed to load dashboard");
      }
    })();
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
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  function logout() {
    clearToken();
    window.location.href = "/";
  }

  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />
      <section className="pt-32 pb-24">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <div className="flex items-center justify-between mb-8">
            <h1 className="text-4xl font-bold text-on-surface">Dashboard</h1>
            <BrutalButton variant="ghost" size="sm" onClick={logout}>Log out</BrutalButton>
          </div>
          {error ? <p className="text-sm text-red-500 mb-6">{error}</p> : null}
          <div className="grid gap-6 md:grid-cols-2 mb-6">
            <div className={cardCls}>
              <h2 className="text-sm uppercase tracking-widest text-on-surface-variant mb-4">Account</h2>
              {user ? (
                <div className="text-body-md text-on-surface space-y-1">
                  <p><span className="text-on-surface-variant">Email: </span>{String(user.email ?? "—")}</p>
                  <p><span className="text-on-surface-variant">Username: </span>{String(user.username ?? "—")}</p>
                </div>
              ) : (
                <p className="text-on-surface-variant">Loading…</p>
              )}
            </div>
            <div className={cardCls}>
              <h2 className="text-sm uppercase tracking-widest text-on-surface-variant mb-4">FinOps usage</h2>
              {summary ? (
                <div className="text-body-md text-on-surface space-y-1">
                  <p><span className="text-on-surface-variant">Spend (cents): </span>{String(summary.spend_cents ?? 0)}</p>
                  <p><span className="text-on-surface-variant">Cost records: </span>{String(summary.cost_records ?? 0)}</p>
                  <p><span className="text-on-surface-variant">Total tokens: </span>{String(summary.total_tokens ?? 0)}</p>
                </div>
              ) : (
                <p className="text-on-surface-variant">Loading…</p>
              )}
            </div>
          </div>
          <div className={cardCls}>
            <h2 className="text-sm uppercase tracking-widest text-on-surface-variant mb-4">Knowledge search</h2>
            <div className="flex gap-4 mb-4">
              <input
                placeholder="Search the knowledge base…"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") void onSearch(); }}
                className={inputCls}
              />
              <BrutalButton variant="yellow" size="md" onClick={() => void onSearch()}>
                {searching ? "Searching…" : "Search"}
              </BrutalButton>
            </div>
            {results.length > 0 ? (
              <ul className="space-y-3">
                {results.map((r, i) => (
                  <li key={i} className="border border-outline p-4">
                    <p className="font-bold text-on-surface">{String(r.title ?? r.document_id ?? "Result")}</p>
                    <p className="text-sm text-on-surface-variant">{String(r.snippet ?? r.citation ?? "")}</p>
                    <p className="text-xs text-on-surface-variant mt-1">score: {String(r.score ?? "—")}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-on-surface-variant text-sm">No results yet — try a search above.</p>
            )}
          </div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
