"use client";

import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { cn } from "@/lib/utils";
import type { SearchOut, SymbolOut } from "@/types/code";

export function SearchResults({
  search,
  symbols,
  loading,
  error,
  activeFile,
  activeSymbol,
  onOpenResult,
  onSelectSymbol,
  onRetry,
}: {
  search: SearchOut | null;
  symbols: SymbolOut[] | null;
  loading: boolean;
  error: string | null;
  activeFile: string | null;
  activeSymbol: string | null;
  onOpenResult: (hit: SearchOut["results"][number]) => void;
  onSelectSymbol: (symbol: SymbolOut) => void;
  onRetry: () => void;
}) {
  if (error) {
    return (
      <div className="p-3">
        <BrutalErrorState title="Search unavailable" description={error} onRetry={onRetry} />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-2 p-3">
        <BrutalSkeleton className="h-10 w-full" label="Loading search results" />
        <BrutalSkeleton className="h-10 w-full" label="Loading search results" />
        <BrutalSkeleton className="h-10 w-full" label="Loading search results" />
      </div>
    );
  }

  const hits = search?.results ?? [];
  const symbolsList = symbols ?? [];

  if (!search && !symbols) {
    return (
      <div className="p-3">
        <BrutalEmptyState
          title="Search indexed code"
          description="Search snippets, symbols and references backed by the repository index. Select a repository first."
        />
      </div>
    );
  }

  if (hits.length === 0 && symbolsList.length === 0) {
    return (
      <div className="p-3">
        <BrutalEmptyState
          title="No matches"
          description="No results matched your query in the indexed code. Try different terms or a symbol search."
        />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {symbolsList.length > 0 ? (
        <section aria-label="Symbol results" className="border-b border-outline-variant p-3">
          <h3 className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            Symbols ({symbolsList.length})
          </h3>
          <ul className="space-y-1">
            {symbolsList.map((symbol) => (
              <li key={symbol.id}>
                <button
                  type="button"
                  onClick={() => onSelectSymbol(symbol)}
                  aria-current={activeSymbol === symbol.id ? "page" : undefined}
                  className={cn(
                    "w-full border px-3 py-2 text-left",
                    activeSymbol === symbol.id
                      ? "border-primary-container bg-primary-container/10"
                      : "border-outline bg-transparent hover:border-primary-container",
                  )}
                >
                  <span className="font-mono text-xs text-primary-container">{symbol.name}</span>
                  <span className="ml-2 font-mono text-[10px] uppercase text-on-surface-variant">
                    {symbol.symbol_type} · L{symbol.line_start}-{symbol.line_end}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section aria-label="Search results" className="p-3">
        <h3 className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          Results ({hits.length})
        </h3>
        <ul className="space-y-1">
          {hits.map((hit) => (
            <li key={hit.id || `${hit.file_path}-${hit.line}-${hit.name}`}>
              <button
                type="button"
                onClick={() => onOpenResult(hit)}
                aria-current={activeFile === hit.file_path && !activeSymbol ? "page" : undefined}
                className={cn(
                  "w-full border px-3 py-2 text-left",
                  activeFile === hit.file_path && !activeSymbol
                    ? "border-primary-container bg-primary-container/10"
                    : "border-outline bg-transparent hover:border-primary-container",
                )}
              >
                <span className="flex items-center gap-2">
                  <span className="truncate font-mono text-xs font-bold text-on-surface">{hit.name}</span>
                  <span className="shrink-0 font-mono text-[10px] uppercase text-on-surface-variant">
                    {hit.result_type}
                  </span>
                  <span className="ml-auto shrink-0 font-mono text-[10px] text-on-surface-variant">
                    {hit.score >= 0 ? hit.score.toFixed(2) : ""}
                  </span>
                </span>
                <span className="mt-1 block truncate font-mono text-[10px] text-on-surface-variant">
                  {hit.file_path ?? "unknown file"}
                  {hit.line != null ? ` · L${hit.line}` : ""}
                </span>
                {hit.snippet ? (
                  <span className="mt-1 block whitespace-pre-wrap break-words font-mono text-[11px] text-on-surface-variant">
                    {hit.snippet}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}