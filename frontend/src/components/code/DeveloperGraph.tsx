"use client";

import { useEffect, useState } from "react";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { GraphOut } from "@/types/code";
import { devErrorMessage } from "./dev-utils";

const GRAPH_LIMIT = 100;

export function DeveloperGraph({ repoId }: { repoId: string }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GraphOut | null>(null);

  const load = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      // Bounded explicitly — the backend also defaults to 200.
      const data = await api.ciGraph(token, repoId, GRAPH_LIMIT);
      setResult(data);
    } catch (e) {
      const msg = devErrorMessage(e, "dependency graph");
      if (msg) setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // The panel remounts per repository (parent keys it), so this runs once per repo.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  if (loading) return <BrutalSkeleton className="h-32 w-full" label="Loading dependency graph" />;
  if (error) return <BrutalErrorState title="Graph unavailable" description={error} onRetry={() => void load()} />;
  if (!result) {
    return (
      <BrutalErrorState
        title="Dependency graph"
        description="Open this tab to load the dependency graph from the backend."
        onRetry={() => void load()}
      />
    );
  }

  const nodes = Array.isArray(result.nodes) ? result.nodes : [];
  const edges = Array.isArray(result.edges) ? result.edges : [];
  const shownEdges = edges.slice(0, GRAPH_LIMIT);

  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-2">
        <div className="border border-outline bg-surface p-2">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Nodes</dt>
          <dd className="mt-0.5 font-mono text-lg font-bold text-on-surface">{nodes.length}</dd>
        </div>
        <div className="border border-outline bg-surface p-2">
          <dt className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">Edges</dt>
          <dd className="mt-0.5 font-mono text-lg font-bold text-on-surface">{edges.length}</dd>
        </div>
      </dl>
      <p className="font-mono text-[10px] text-on-surface-variant">
        Graph bounded to the first {GRAPH_LIMIT} nodes/edges returned by the backend for safe rendering.
      </p>
      {shownEdges.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">No dependency edges returned.</p>
      ) : (
        <div>
          <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Edges</h3>
          <ul className="mt-1 space-y-1">
            {shownEdges.map((edge, i) => (
              <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                {edge.source} → {edge.target}{" "}
                <span className="text-on-surface-variant/60">({edge.edge_type})</span>
              </li>
            ))}
          </ul>
          {edges.length > shownEdges.length ? (
            <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
              {edges.length - shownEdges.length} more edges truncated.
            </p>
          ) : null}
        </div>
      )}
    </div>
  );
}