"use client";

import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { KnowledgeSearchItem, KnowledgeSearchResponse } from "@/types/knowledge";

function freshnessLabel(score: number | null | undefined): string {
  if (score === null || score === undefined) return "freshness n/a";
  if (score >= 0.7) return `fresh ${Math.round(score * 100)}`;
  if (score >= 0.3) return `aging ${Math.round(score * 100)}`;
  return `stale ${Math.round(score * 100)}`;
}

function filterLabel(value: string | null | undefined): string {
  return value ?? "none";
}

export function KnowledgeResults({
  results,
  loading,
  error,
  query,
  selectedItem,
  page,
  pageSize,
  onOpen,
  onRetry,
  onPageChange,
}: {
  results: KnowledgeSearchResponse | null;
  loading: boolean;
  error: string | null;
  query: string;
  selectedItem: string | null;
  page: number;
  pageSize: number;
  onOpen: (item: KnowledgeSearchItem) => void;
  onRetry: () => void;
  onPageChange: (page: number) => void;
}) {
  if (loading) {
    return (
      <div className="space-y-3 p-4" role="status" aria-label="Searching knowledge">
        <BrutalSkeleton className="h-20" />
        <BrutalSkeleton className="h-20" />
        <BrutalSkeleton className="h-20" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-4">
        <BrutalErrorState title="Search failed" description={error} onRetry={onRetry} />
      </div>
    );
  }

  if (!results) {
    return (
      <div className="p-4">
        <BrutalEmptyState
          title="Search the knowledge base"
          description="Enter a query above. Results are retrieved by the backend with real citations and provenance — never synthesized on the client."
        />
      </div>
    );
  }

  if (results.items.length === 0) {
    return (
      <div className="p-4">
        <BrutalEmptyState
          title={`No results for "${query}"`}
          description="Try different terms or clear the filters above."
        />
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(results.total / pageSize));
  const filtersApplied = results.filters_applied ?? {};

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-outline-variant px-4 py-2">
        <p className="font-mono text-xs text-on-surface-variant">
          {results.total} result{results.total === 1 ? "" : "s"} · {results.latency_ms} ms
        </p>
        <p className="font-mono text-xs text-on-surface-variant">
          page {page} of {totalPages}
        </p>
      </div>

      <details className="border-b border-outline-variant px-4 py-2" aria-label="Retrieval trace">
        <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
          Retrieval trace / explanation
        </summary>
        <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-on-surface-variant sm:grid-cols-3">
          <div>
            <dt className="font-mono uppercase tracking-wider">query_id</dt>
            <dd className="font-mono">{results.query_id}</dd>
          </div>
          <div>
            <dt className="font-mono uppercase tracking-wider">latency</dt>
            <dd className="font-mono">{results.latency_ms} ms</dd>
          </div>
          <div>
            <dt className="font-mono uppercase tracking-wider">filters_applied</dt>
            <dd className="font-mono">
              {[
                filtersApplied.source_type ? `source:${filterLabel(filtersApplied.source_type)}` : null,
                filtersApplied.doc_type ? `doc:${filterLabel(filtersApplied.doc_type)}` : null,
                filtersApplied.classification ? `class:${filterLabel(filtersApplied.classification)}` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "none"}
            </dd>
          </div>
        </dl>
        <p className="mt-2 text-xs text-on-surface-variant">
          Each result below reports the backend&apos;s retrieval method, freshness score, score and
          citation provenance exactly as returned by <code className="font-mono">/knowledge/search</code>.
        </p>
      </details>

      <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4" aria-label="Knowledge results">
        {results.items.map((item, index) => {
          const id = String(item.document_id ?? item.chunk_id ?? `${query}-${page}-${index}`);
          const active = selectedItem !== null && item.document_id === selectedItem;
          const citationCount = Array.isArray(item.citations) ? item.citations.length : 0;
          return (
            <li key={id}>
              <button
                type="button"
                onClick={() => onOpen(item)}
                aria-pressed={active}
                className={`block w-full border border-outline p-4 text-left transition-colors ${
                  active
                    ? "border-primary-container bg-surface-container-high"
                    : "bg-surface hover:border-primary-container"
                }`}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-bold text-on-surface">
                    {String(item.title ?? "Untitled result")}
                  </p>
                  {item.source_type ? <BrutalBadge tone="default">{item.source_type}</BrutalBadge> : null}
                  <BrutalBadge tone={item.classification === "PUBLIC" ? "yellow" : "muted"}>
                    {item.classification ?? "INTERNAL"}
                  </BrutalBadge>
                </div>
                {item.snippet ? (
                  <p className="mt-2 text-sm text-on-surface-variant">{item.snippet}</p>
                ) : null}
                <div className="mt-2 flex flex-wrap items-center gap-3 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                  <span>score {String(item.score ?? "—")}</span>
                  <span>{freshnessLabel(item.freshness_score)}</span>
                  <span>retrieval: {item.retrieval_method ?? "hybrid"}</span>
                  <span>
                    {citationCount} citation{citationCount === 1 ? "" : "s"}
                  </span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>

      <div className="flex items-center justify-between gap-3 border-t border-outline px-4 py-2">
        <BrutalButton
          variant="ghost"
          size="sm"
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          Previous
        </BrutalButton>
        <BrutalButton
          variant="ghost"
          size="sm"
          disabled={page >= totalPages}
          onClick={() => onPageChange(page + 1)}
        >
          Next
        </BrutalButton>
      </div>
    </div>
  );
}