"use client";

import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { SymbolDetailOut } from "@/types/code";

export function SymbolDetailPanel({
  symbol,
  loading,
  error,
  onRetry,
  onDependencyClick,
}: {
  symbol: SymbolDetailOut | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onDependencyClick?: (symbolId: string) => void;
}) {
  if (loading) {
    return (
      <div className="p-3">
        <BrutalSkeleton className="h-40 w-full" label="Loading symbol detail" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-3">
        <BrutalErrorState title="Symbol detail unavailable" description={error} onRetry={onRetry} />
      </div>
    );
  }

  if (!symbol) {
    return (
      <div className="p-3">
        <BrutalEmptyState
          title="Symbol detail"
          description="Select a symbol to view its definition, callers, callees and references."
        />
      </div>
    );
  }

  const calls = (symbol.calls ?? []).map((c) => ({ caller_id: String(c.caller_id ?? ""), callee_id: String(c.callee_id ?? ""), call_type: String(c.call_type ?? ""), line: c.line }));
  const calledBy = (symbol.called_by ?? []).map((c) => ({ caller_id: String(c.caller_id ?? ""), callee_id: String(c.callee_id ?? ""), call_type: String(c.call_type ?? ""), line: c.line }));
  const references = (symbol.references ?? []).map((r) => ({ id: String(r.id ?? ""), reference_type: String(r.reference_type ?? ""), line: r.line }));

  return (
    <section className="border border-outline bg-surface-container p-3" aria-label="Symbol detail">
      <header className="mb-2 flex items-center gap-2">
        <h3 className="font-mono text-xs font-bold text-primary-container">{symbol.name}</h3>
        <BrutalBadge>{symbol.symbol_type}</BrutalBadge>
      </header>
      {symbol.qualified_name ? (
        <p className="break-all font-mono text-[11px] text-on-surface-variant">
          {symbol.qualified_name}
        </p>
      ) : null}
      <p className="mt-1 font-mono text-[11px] text-on-surface-variant">
        Lines {symbol.line_start}-{symbol.line_end} · Complexity {symbol.complexity}
      </p>
      {symbol.signature ? (
        <pre className="mt-2 overflow-x-auto whitespace-pre-wrap border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
          {symbol.signature}
        </pre>
      ) : null}
      {symbol.docstring ? (
        <p className="mt-2 text-sm text-on-surface-variant">{symbol.docstring}</p>
      ) : null}

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <RelationList title="Callees (calls)" rows={calls.map((c) => ({ key: c.callee_id, label: c.call_type + (c.line ? ` · L${c.line}` : "") }))} onRowClick={onDependencyClick ? (key) => onDependencyClick(key) : undefined} emptyText="No callees recorded" />
        <RelationList title="Callers (called by)" rows={calledBy.map((c) => ({ key: c.caller_id, label: c.call_type + (c.line ? ` · L${c.line}` : "") }))} onRowClick={onDependencyClick ? (key) => onDependencyClick(key) : undefined} emptyText="No callers recorded" />
      </div>
      <div className="mt-3">
        <RelationList title="References" rows={references.map((r) => ({ key: r.id, label: r.reference_type + (r.line ? ` · L${r.line}` : "") }))} emptyText="No references recorded" />
      </div>
    </section>
  );
}

function RelationList({
  title,
  rows,
  onRowClick,
  emptyText,
}: {
  title: string;
  rows: Array<{ key: string; label: string }>;
  onRowClick?: (key: string) => void;
  emptyText: string;
}) {
  return (
    <section>
      <h4 className="mb-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{title}</h4>
      {rows.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">{emptyText}</p>
      ) : (
        <ul className="max-h-32 space-y-0.5 overflow-y-auto">
          {rows.map((row) => (
            <li key={row.key}>
              {onRowClick ? (
                <button
                  type="button"
                  onClick={() => onRowClick(row.key)}
                  className="w-full truncate text-left font-mono text-[11px] text-on-surface-variant hover:text-primary-container"
                >
                  {row.key} {row.label}
                </button>
              ) : (
                <span className="block truncate font-mono text-[11px] text-on-surface-variant">
                  {row.key} {row.label}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}