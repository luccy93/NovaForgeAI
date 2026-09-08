"use client";

import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { KnowledgeDocument, KnowledgeSearchItem } from "@/types/knowledge";

function safeExternalUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

export function KnowledgeResultDetail({
  hit,
  document,
  loading,
  error,
  onBack,
  onRetry,
}: {
  hit: KnowledgeSearchItem;
  document: KnowledgeDocument | null;
  loading: boolean;
  error: string | null;
  onBack: () => void;
  onRetry: () => void;
}) {
  const title = document?.title ?? hit.title ?? "Untitled result";
  const citations = Array.isArray(hit.citations) ? hit.citations : [];

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto" aria-label="Result detail">
      <div className="flex items-center justify-between gap-3 border-b border-outline px-4 py-2">
        <p className="font-mono text-xs uppercase tracking-widest text-primary-container">
          Document detail
        </p>
        <div className="flex items-center gap-2">
          <BrutalButton variant="ghost" size="sm" href="/ai">
            Ask AI about this result
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" onClick={onBack}>
            Back to results
          </BrutalButton>
        </div>
      </div>

      <div className="space-y-4 p-4">
        <header>
          <h2 className="text-lg font-bold text-on-surface">{title}</h2>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            {document?.doc_type ? <BrutalBadge tone="default">{document.doc_type}</BrutalBadge> : null}
            {document?.classification ? (
              <BrutalBadge tone={document.classification === "PUBLIC" ? "yellow" : "muted"}>
                {document.classification}
              </BrutalBadge>
            ) : null}
            {document?.status ? <BrutalBadge tone="muted">{document.status}</BrutalBadge> : null}
            {document?.version ? (
              <span className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                v{document.version}
              </span>
            ) : null}
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-on-surface-variant sm:grid-cols-3">
            {document?.source_id ? (
              <div>
                <dt className="font-mono uppercase tracking-wider">Source</dt>
                <dd className="font-mono">{document.source_id}</dd>
              </div>
            ) : null}
            {document?.updated_at ? (
              <div>
                <dt className="font-mono uppercase tracking-wider">Updated</dt>
                <dd>{new Date(document.updated_at).toLocaleString()}</dd>
              </div>
            ) : null}
            {document?.language ? (
              <div>
                <dt className="font-mono uppercase tracking-wider">Language</dt>
                <dd>{document.language}</dd>
              </div>
            ) : null}
            {hit.score !== undefined ? (
              <div>
                <dt className="font-mono uppercase tracking-wider">Relevance</dt>
                <dd>{String(hit.score)}</dd>
              </div>
            ) : null}
            {document?.freshness_score !== null && document?.freshness_score !== undefined ? (
              <div>
                <dt className="font-mono uppercase tracking-wider">Freshness</dt>
                <dd>{String(document.freshness_score)}</dd>
              </div>
            ) : null}
          </dl>
        </header>

        {loading ? (
          <div className="space-y-3" role="status" aria-label="Loading document">
            <BrutalSkeleton className="h-64" />
          </div>
        ) : error ? (
          <BrutalErrorState
            title="Document unavailable"
            description={error}
            onRetry={onRetry}
          />
        ) : document ? (
          <div className="space-y-4">
            {document.summary ? (
              <section className="border border-outline bg-surface-container p-4">
                <h3 className="text-xs font-mono uppercase tracking-widest text-on-surface-variant">
                  Summary
                </h3>
                <p className="mt-2 text-sm text-on-surface">{document.summary}</p>
              </section>
            ) : null}

            <section className="border border-outline bg-surface p-4">
              <h3 className="text-xs font-mono uppercase tracking-widest text-on-surface-variant">
                Indexed content
              </h3>
              {document.content ? (
                <pre className="mt-2 whitespace-pre-wrap break-words font-sans text-sm text-on-surface">
                  {document.content}
                </pre>
              ) : (
                <BrutalEmptyState
                  title="Content not available"
                  description="This document is indexed, but the full source content is not available through the current Knowledge API. Only the metadata returned by the backend is shown."
                />
              )}
            </section>

            {Array.isArray(document.tags) && document.tags.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {document.tags.map((tag) => (
                  <BrutalBadge key={String(tag)} tone="muted">
                    {String(tag)}
                  </BrutalBadge>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
      </div>

      <section className="border-t border-outline p-4" aria-label="Citations">
        <h3 className="text-xs font-mono uppercase tracking-widest text-on-surface-variant">
          Citations / provenance
        </h3>
        {citations.length > 0 ? (
          <ul className="mt-2 space-y-2">
            {citations.map((citation, index) => {
              const target = safeExternalUrl(citation.url);
              return (
                <li
                  key={`${hit.document_id ?? hit.chunk_id}-citation-${index}`}
                  className="border border-outline-variant p-3 text-sm"
                >
                  <p className="text-on-surface">
                    {target ? (
                      <a
                        href={target}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="underline hover:text-primary-container"
                      >
                        {String(citation.source_name ?? "source")}
                      </a>
                    ) : (
                      String(citation.source_name ?? "unknown source")
                    )}
                  </p>
                  <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
                    {(citation.doc_type ?? "document").toLowerCase()}
                    {citation.version ? ` · v${citation.version}` : ""}
                    {!target && !citation.url ? " · source unavailable in Knowledge API" : ""}
                  </p>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-on-surface-variant">
            No citation metadata was returned by the backend for this result.
          </p>
        )}
      </section>
    </div>
  );
}