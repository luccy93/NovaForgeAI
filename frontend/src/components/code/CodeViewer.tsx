"use client";

import { useMemo, type ReactNode } from "react";
import { CodePreview } from "@/components/code/CodePreview";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { FileContentOut, SearchResultItem } from "@/types/code";

export type PreviewState = "preview" | "no-data" | "unavailable";

export interface CodeViewerSelection {
  file: FileContentOut | null;
  fileLoading: boolean;
  fileError: string | null;
  /** Backend-provided snippet for the opened result (may be a code excerpt). */
  searchHit: SearchResultItem | null;
}

export function CodeViewer({
  selection,
  repositoryName,
  defaultBranch,
  onSymbolClick,
  onRetry,
}: {
  selection: CodeViewerSelection;
  repositoryName?: string | null;
  defaultBranch?: string | null;
  onSymbolClick?: (symbolId: string) => void;
  onRetry?: () => void;
}) {
  const { file, fileLoading, fileError, searchHit } = selection;

  const previewCode = useMemo(() => {
    if (searchHit?.snippet) return searchHit.snippet;
    return null;
  }, [searchHit]);

  const previewState: PreviewState = previewCode ? "preview" : fileLoading ? "unavailable" : "no-data";

  if (fileLoading) {
    return (
      <div className="p-4">
        <BrutalSkeleton className="h-40 w-full" label="Loading file intelligence" />
      </div>
    );
  }

  if (fileError) {
    return (
      <div className="p-4">
        <div className="border border-error bg-surface p-6 text-center" role="alert">
          <p className="font-bold text-error">File intelligence unavailable</p>
          <p className="mt-2 text-sm text-on-surface-variant">{fileError}</p>
          {onRetry ? (
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 border border-outline px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-surface hover:border-primary-container hover:text-primary-container"
            >
              Retry
            </button>
          ) : null}
        </div>
      </div>
    );
  }

  const fileMeta = file?.file;

  return (
    <div className="flex flex-col gap-4 p-4">
      {/* ── File header ─────────────────────────────────────────────────── */}
      <header className="border border-outline bg-surface-container p-4">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            {repositoryName ?? "Repository"}
          </p>
          {defaultBranch ? <BrutalBadge>{defaultBranch}</BrutalBadge> : null}
          {fileMeta?.language ? <BrutalBadge>{fileMeta.language}</BrutalBadge> : null}
          {fileMeta?.status ? <BrutalBadge tone="muted">{fileMeta.status}</BrutalBadge> : null}
        </div>
        <h2 className="mt-2 break-all font-mono text-sm font-bold text-on-surface">
          {fileMeta?.path ?? (searchHit?.file_path ?? "Unknown file")}
        </h2>
        {fileMeta ? (
          <p className="mt-1 font-mono text-[11px] text-on-surface-variant">
            {fileMeta.line_count.toLocaleString()} lines · {fileMeta.size_bytes.toLocaleString()} bytes ·{" "}
            {fileMeta.symbol_count} symbols
          </p>
        ) : searchHit?.line ? (
          <p className="mt-1 font-mono text-[11px] text-on-surface-variant">Line {searchHit.line}</p>
        ) : null}
      </header>

      {/* ── Source preview (backend-supplied only) ───────────────────────── */}
      <section aria-label="Source preview">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-primary-container">
            Source preview
          </h3>
          {previewState === "preview" ? <BrutalBadge tone="yellow">Preview available</BrutalBadge> : null}
        </div>
        {previewState === "preview" && previewCode ? (
          <>
            <CodePreview
              key={searchHit?.id ?? fileMeta?.id ?? "preview"}
              code={previewCode}
              filePath={fileMeta?.path ?? searchHit?.file_path}
              languageHint={fileMeta?.language}
              startLine={searchHit?.line && searchHit.line > 1 ? searchHit.line : 1}
            />
            <p className="mt-2 font-mono text-[11px] text-on-surface-variant">
              Showing indexed code snippets. Full file source is not currently exposed by the backend.
            </p>
          </>
        ) : previewState === "no-data" ? (
          <div className="border border-outline bg-surface p-6 text-center">
            <p className="font-bold text-on-surface">Code preview unavailable</p>
            <p className="mt-2 text-sm text-on-surface-variant">
              No indexed preview is available for this location. Structure, symbols, references and
              imports are still shown below.
            </p>
          </div>
        ) : (
          <BrutalSkeleton className="h-24 w-full" label="Loading preview" />
        )}
      </section>

      {/* ── Symbols / References / Imports ───────────────────────────────── */}
      {!file && !fileLoading ? (
        <BrutalEmptyState
          title="File intelligence unavailable"
          description="Select a search result or symbol to see its indexed structure."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-3">
          <FileSection title="Symbols" count={file?.symbols.length ?? 0} emptyText="No symbols indexed">
            {file?.symbols.length
              ? file.symbols.map((symbol) => (
                  <li key={symbol.id}>
                    <button
                      type="button"
                      onClick={() => onSymbolClick?.(symbol.id)}
                      className={`w-full text-left ${onSymbolClick ? "hover:border-primary-container" : "cursor-default"}`}
                    >
                      <span className="font-mono text-xs text-primary-container">{symbol.name}</span>
                      <span className="ml-2 font-mono text-[10px] uppercase text-on-surface-variant">
                        {symbol.symbol_type} · L{symbol.line_start}-{symbol.line_end}
                      </span>
                      {symbol.signature ? (
                        <span className="mt-1 block break-all font-mono text-[11px] text-on-surface-variant">
                          {symbol.signature}
                        </span>
                      ) : null}
                    </button>
                  </li>
                ))
              : null}
          </FileSection>
          <FileSection
            title="References"
            count={file?.references.length ?? 0}
            emptyText="No reference data indexed"
          >
            {file?.references.length
              ? file.references.map((ref) => (
                  <li key={ref.id} className="font-mono text-xs text-on-surface-variant">
                    {ref.reference_type ?? "reference"}
                    {ref.line != null ? ` · L${ref.line}` : ""}
                  </li>
                ))
              : null}
          </FileSection>
          <FileSection title="Imports" count={file?.imports.length ?? 0} emptyText="No imports indexed">
            {file?.imports.length
              ? file.imports.map((imp) => (
                  <li key={imp.id} className="font-mono text-xs text-on-surface-variant">
                    {imp.module_path}
                    {imp.line != null ? ` · L${imp.line}` : ""}
                  </li>
                ))
              : null}
          </FileSection>
        </div>
      )}
    </div>
  );
}

function FileSection({
  title,
  count,
  emptyText,
  children,
}: {
  title: string;
  count: number;
  emptyText: string;
  children?: ReactNode;
}) {
  return (
    <section className="border border-outline bg-surface-container p-3">
      <header className="mb-2 flex items-center justify-between">
        <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{title}</h3>
        <BrutalBadge tone="muted">{count}</BrutalBadge>
      </header>
      {count > 0 ? <ul className="max-h-64 space-y-1 overflow-y-auto">{children}</ul> : null}
      {count === 0 ? <p className="font-mono text-[11px] text-on-surface-variant">{emptyText}</p> : null}
    </section>
  );
}