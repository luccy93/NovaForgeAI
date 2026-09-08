"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { KnowledgeSearchItem } from "@/types/knowledge";
import type { CatalogHit, UniversalDomain, UniversalDomainId } from "@/types/universal";

type SearchableDomain = Extract<UniversalDomainId, "knowledge" | "dataCatalog">;

type DomainOutcome =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ok"; count: number };

type UniversalResults = {
  knowledge: { hits: KnowledgeSearchItem[] };
  dataCatalog: { hits: CatalogHit[] };
};

const SEARCHABLE: Record<SearchableDomain, { label: string }> = {
  knowledge: { label: "Knowledge" },
  dataCatalog: { label: "Data catalog" },
};

const NOT_SEARCHABLE: Array<UniversalDomain> = [
  { id: "code", label: "Code", reason: "No global code search — code intelligence is scoped per repository." },
  { id: "incidents", label: "Incidents", reason: "The incidents API exposes lists, not a text search contract." },
  { id: "security", label: "Security", reason: "No IAM-scoped security search contract is exposed." },
  { id: "workflows", label: "Workflows", reason: "The workflows API exposes lists, not a text search contract." },
  { id: "integrations", label: "Integrations", reason: "The integrations API exposes connections, not search." },
];

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

export function UniversalSearch() {
  const [query, setQuery] = useState("");
  const [outcomes, setOutcomes] = useState<Record<SearchableDomain, DomainOutcome>>({
    knowledge: { status: "idle" },
    dataCatalog: { status: "idle" },
  });
  const [results, setResults] = useState<UniversalResults | null>(null);
  const [ranOnce, setRanOnce] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const runSearch = useCallback(async (q: string) => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const trimmed = q.trim();
    if (!trimmed) return;
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setOutcomes({
      knowledge: { status: "loading" },
      dataCatalog: { status: "loading" },
    });
    setResults(null);
    setRanOnce(true);

    const finish = (
      key: SearchableDomain,
      outcome: DomainOutcome,
    ) => {
      if (seq !== seqRef.current) return;
      setOutcomes((prev) => ({ ...prev, [key]: outcome }));
    };

    void (async () => {
      try {
        const res = await api.knowledgeSearch(token, trimmed, {
          limit: 5,
          signal: controller.signal,
        });
        if (seq !== seqRef.current) return;
        setResults((prev) => ({
          knowledge: { hits: res.items },
          dataCatalog: prev?.dataCatalog ?? { hits: [] },
        }));
        finish("knowledge", { status: "ok", count: res.items.length });
      } catch (e) {
        if (seq !== seqRef.current || controller.signal.aborted) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setResults((prev) => (prev ? { ...prev, knowledge: { hits: [] } } : prev));
        finish("knowledge", {
          status: "error",
          message: e instanceof Error ? e.message : "Search failed",
        });
      }
    })();

    void (async () => {
      try {
        const res = await api.dataCatalogSearch(token, trimmed, { limit: 5 });
        if (seq !== seqRef.current) return;
        setResults((prev) => ({
          knowledge: prev?.knowledge ?? { hits: [] },
          dataCatalog: { hits: res.items },
        }));
        finish("dataCatalog", { status: "ok", count: res.items.length });
      } catch (e) {
        if (seq !== seqRef.current || controller.signal.aborted) return;
        if (e instanceof ApiError && e.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setResults((prev) => (prev ? { ...prev, dataCatalog: { hits: [] } } : prev));
        finish("dataCatalog", {
          status: "error",
          message: e instanceof Error ? e.message : "Search failed",
        });
      }
    })();
  }, []);

  useEffect(() => {
    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setOutcomes({
        knowledge: { status: "idle" },
        dataCatalog: { status: "idle" },
      });
      setResults(null);
      setRanOnce(false);
      setQuery("");
    };
    window.addEventListener("tenant:switched", resetForContextSwitch);
    window.addEventListener("workspace:switched", resetForContextSwitch);
    return () => {
      window.removeEventListener("tenant:switched", resetForContextSwitch);
      window.removeEventListener("workspace:switched", resetForContextSwitch);
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []);

  const anyLoading = outcomes.knowledge.status === "loading" || outcomes.dataCatalog.status === "loading";
  const anyCount = (outcomes.knowledge.status === "ok" ? outcomes.knowledge.count : 0)
    + (outcomes.dataCatalog.status === "ok" ? outcomes.dataCatalog.count : 0);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="border-b border-outline p-4">
        <div className="flex items-end gap-2">
          <div className="min-w-0 flex-1">
            <BrutalInput
              label="Universal search"
              aria-label="Universal search"
              placeholder="One query across every domain that exposes a real search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") runSearch(query);
              }}
            />
          </div>
          <BrutalButton variant="yellow" size="sm" onClick={() => runSearch(query)} disabled={anyLoading || !query.trim()}>
            {anyLoading ? "Searching…" : "Search"}
          </BrutalButton>
        </div>
        <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
          Globally scoped to the authenticated session and tenant. Domains without a real search
          contract are shown as unavailable — nothing is synthesized client-side.
        </p>
        <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
          REALTIME: UNAVAILABLE — no SSE contract is exposed for knowledge events; each domain
          reports only once its own API returns.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {!ranOnce ? (
          <div className="p-4">
            <BrutalEmptyState
              title="Search across real domains"
              description="Run a query once. Results come straight from each domain's own API with its native provenance — no client-side retrieval or fabrication."
            />
          </div>
        ) : anyLoading ? (
          <div className="space-y-3 p-4" role="status" aria-label="Running universal search">
            {Object.values(SEARCHABLE).map((d) => (
              <div key={d.label} className="border border-outline bg-surface p-4">
                <p className="font-mono text-xs uppercase tracking-widest text-primary-container">{d.label}</p>
                <BrutalSkeleton className="mt-3 h-16" />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4 p-4">
            <div className="flex items-center justify-between gap-3 border border-outline bg-surface px-4 py-2">
              <p className="font-mono text-xs text-on-surface-variant">
                {anyCount} total hits across {Object.values(SEARCHABLE).length} searchable domains
              </p>
              {results ? (
                <BrutalButton variant="ghost" size="sm" href="/ai">
                  Ask AI about these results
                </BrutalButton>
              ) : null}
            </div>

            {(Object.keys(SEARCHABLE) as SearchableDomain[]).map((domainId) => {
              const outcome = outcomes[domainId];
              const label = SEARCHABLE[domainId].label;
              return (
                <section key={domainId} className="border border-outline bg-surface" aria-label={`${label} results`}>
                  <header className="flex items-center justify-between gap-3 border-b border-outline px-4 py-2">
                    <p className="font-mono text-xs uppercase tracking-widest text-primary-container">{label}</p>
                    <OutcomeBadge outcome={outcome} />
                  </header>
                  <div className="p-4">
                    {outcome.status === "ok" ? (
                      outcome.count > 0 && results ? (
                        <DomainHits domainId={domainId} hits={results[domainId].hits} />
                      ) : (
                        <p className="text-sm text-on-surface-variant">No matches returned by the {label.toLowerCase()} API.</p>
                      )
                    ) : outcome.status === "error" ? (
                      <p className="text-sm text-error" role="alert">{outcome.message}</p>
                    ) : (
                      <BrutalSkeleton className="h-12" />
                    )}
                  </div>
                </section>
              );
            })}

            <section className="border border-outline bg-surface" aria-label="Unavailable domains">
              <header className="border-b border-outline px-4 py-2">
                <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
                  No search contract
                </p>
              </header>
              <ul className="divide-y divide-outline">
                {NOT_SEARCHABLE.map((domain) => (
                  <li key={domain.id} className="flex items-baseline justify-between gap-3 px-4 py-3">
                    <span className="text-sm font-bold text-on-surface">{domain.label}</span>
                    <span className="text-right text-xs text-on-surface-variant">{domain.reason}</span>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}

function OutcomeBadge({ outcome }: { outcome: DomainOutcome }) {
  if (outcome.status === "ok") {
    return (
      <BrutalBadge tone="yellow">
        {outcome.count} hit{outcome.count === 1 ? "" : "s"}
      </BrutalBadge>
    );
  }
  if (outcome.status === "error") return <BrutalBadge tone="error">failed</BrutalBadge>;
  if (outcome.status === "loading") return <BrutalBadge tone="default">searching</BrutalBadge>;
  return <BrutalBadge tone="muted">idle</BrutalBadge>;
}

function DomainHits({
  domainId,
  hits,
}: {
  domainId: SearchableDomain;
  hits: KnowledgeSearchItem[] | CatalogHit[];
}) {
  if (domainId === "knowledge") {
    return (
      <ul className="space-y-2" aria-label="Knowledge domain hits">
        {(hits as KnowledgeSearchItem[]).map((hit) => (
          <li key={String(hit.document_id ?? hit.chunk_id)}>
            <a
              href={`/knowledge/document/${encodeURIComponent(String(hit.document_id))}`}
              className="block border border-outline p-3 hover:border-primary-container"
            >
              <p className="text-sm font-bold text-on-surface">{String(hit.title ?? "Untitled result")}</p>
              {hit.snippet ? <p className="mt-1 text-sm text-on-surface-variant">{hit.snippet}</p> : null}
              <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                {hit.source_type ?? "knowledge"} · {String(hit.score ?? "—")}
              </p>
            </a>
          </li>
        ))}
      </ul>
    );
  }
  return (
    <ul className="space-y-2" aria-label="Data catalog domain hits">
      {(hits as CatalogHit[]).map((hit) => (
        <li key={String(hit.id)} className="border border-outline p-3">
          <p className="text-sm font-bold text-on-surface">{String(hit.name ?? "Untitled dataset")}</p>
          {hit.description ? <p className="mt-1 text-sm text-on-surface-variant">{hit.description}</p> : null}
          <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
            {hit.owner ?? "no owner"} · {hit.classification ?? "INTERNAL"} · {hit.source ?? "api"}
          </p>
        </li>
      ))}
    </ul>
  );
}