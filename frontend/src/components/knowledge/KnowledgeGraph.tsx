"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant/workspace entity data synchronously on context switch */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { KnowledgeEntity, KnowledgeEntityDetail } from "@/types/knowledge";

const ENTITY_LIMIT = 100;
const DETAIL_LIMIT = 25;

const TYPE_COLORS: Record<string, string> = {
  person: "#facc15",
  service: "#60a5fa",
  repository: "#4ade80",
  dataset: "#c084fc",
  api: "#fb923c",
  team: "#f472b6",
  file: "#94a3b8",
  concept: "#2dd4bf",
};

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

interface Edge {
  source: string;
  target: string;
  link_type: string;
}

export function KnowledgeGraph() {
  const [entities, setEntities] = useState<KnowledgeEntity[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [details, setDetails] = useState<Record<string, KnowledgeEntityDetail>>({});
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<"graph" | "list">("graph");

  const abortRef = useRef<AbortController | null>(null);
  const seqRef = useRef(0);

  const edges = useMemo<Edge[]>(() => {
    const known = new Set(entities?.map((e) => e.entity_id) ?? []);
    const seen = new Set<string>();
    const out: Edge[] = [];
    for (const detail of Object.values(details)) {
      for (const link of detail.links ?? []) {
        if (known.has(link.source_entity_id) && known.has(link.target_entity_id)) {
          const key = `${link.source_entity_id}|${link.target_entity_id}|${link.link_type}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({ source: link.source_entity_id, target: link.target_entity_id, link_type: link.link_type });
        }
      }
    }
    return out;
  }, [details, entities]);

  const load = useCallback(async () => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    seqRef.current += 1;
    const seq = seqRef.current;
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setEntities(null);
    setDetails({});
    setSelectedId(null);
    try {
      const listRes = await api.knowledgeListEntities(token, { limit: ENTITY_LIMIT });
      if (seq !== seqRef.current) return;
      const list = listRes.items ?? [];
      setEntities(list);
      const head = list.slice(0, DETAIL_LIMIT);
      const detailEntries: Array<[string, KnowledgeEntityDetail]> = [];
      for (const chunk of batch(head, 6)) {
        const settled = await Promise.allSettled(
          chunk.map((e) => api.knowledgeGetEntity(token, e.entity_id)),
        );
        if (seq !== seqRef.current) return;
        settled.forEach((res, i) => {
          if (res.status === "fulfilled") detailEntries.push([chunk[i].entity_id, res.value]);
        });
      }
      if (seq !== seqRef.current) return;
      setDetails(Object.fromEntries(detailEntries));
    } catch (e) {
      if (seq !== seqRef.current) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load the knowledge graph");
    } finally {
      if (seq === seqRef.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const resetForContextSwitch = () => {
      seqRef.current += 1;
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
      setEntities(null);
      setDetails({});
      setSelectedId(null);
      setError(null);
      setLoading(true);
      void load();
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
  }, [load]);

  const selected = selectedId
    ? (entities ?? []).find((e) => e.entity_id === selectedId) ?? null
    : null;
  const selectedDetail = selectedId ? details[selectedId] ?? null : null;
  const neighborIds = useMemo(() => {
    if (!selectedId) return new Set<string>();
    const set = new Set<string>();
    for (const edge of edges) {
      if (edge.source === selectedId) set.add(edge.target);
      if (edge.target === selectedId) set.add(edge.source);
    }
    return set;
  }, [edges, selectedId]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between gap-3 border-b border-outline px-4 py-2">
        <p className="font-mono text-xs uppercase tracking-widest text-primary-container">
          Knowledge graph
        </p>
        <div className="flex items-center gap-2">
          <BrutalSelect
            label="View"
            aria-label="Graph view"
            value={view}
            onChange={(e) => setView(e.target.value as "graph" | "list")}
            options={[
              { value: "graph", label: "Graph" },
              { value: "list", label: "List" },
            ]}
          />
          <BrutalButton variant="ghost" size="sm" onClick={() => void load()}>
            Refresh
          </BrutalButton>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {loading ? (
          <div className="space-y-3 p-4" role="status" aria-label="Loading knowledge graph">
            <BrutalSkeleton className="h-24" />
            <BrutalSkeleton className="h-24" />
          </div>
        ) : error ? (
          <div className="p-4">
            <BrutalErrorState title="Knowledge graph unavailable" description={error} onRetry={() => void load()} />
          </div>
        ) : !entities || entities.length === 0 ? (
          <div className="p-4">
            <BrutalEmptyState
              title="No entities in this workspace"
              description="The knowledge graph is built from real entities and links returned by the Knowledge API. Nothing is generated client-side."
            />
          </div>
        ) : view === "graph" ? (
          <GraphView
            entities={entities}
            edges={edges}
            selectedId={selectedId}
            neighborIds={neighborIds}
            onSelect={setSelectedId}
          />
        ) : (
          <ListView
            entities={entities}
            edges={edges}
            selectedId={selectedId}
            neighborIds={neighborIds}
            onSelect={setSelectedId}
          />
        )}
      </div>

      {selected ? (
        <div className="border-t border-outline bg-surface p-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-bold text-on-surface">{selected.name}</h2>
            <BrutalBadge tone={selected.classification === "PUBLIC" ? "yellow" : "muted"}>
              {selected.classification ?? "INTERNAL"}
            </BrutalBadge>
          </div>
          <p className="mt-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
            {selected.entity_type} · confidence {String(selected.confidence ?? "—")}
          </p>
          {selected.description ? (
            <p className="mt-2 text-sm text-on-surface-variant">{selected.description}</p>
          ) : null}
          <div className="mt-2">
            <p className="font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
              Links ({selectedDetail?.links?.length ?? 0})
            </p>
            {selectedDetail && selectedDetail.links.length > 0 ? (
              <ul className="mt-1 space-y-1">
                {selectedDetail.links.slice(0, 8).map((link, i) => (
                  <li key={`${link.link_id}-${i}`} className="font-mono text-xs text-on-surface-variant">
                    {link.link_type} → {link.target_entity_id === selectedId ? link.source_entity_id : link.target_entity_id}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-xs text-on-surface-variant">
                No link metadata returned by the backend for this entity.
              </p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function batch<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function GraphView({
  entities,
  edges,
  selectedId,
  neighborIds,
  onSelect,
}: {
  entities: KnowledgeEntity[];
  edges: Edge[];
  selectedId: string | null;
  neighborIds: Set<string>;
  onSelect: (id: string) => void;
}) {
  const width = 800;
  const height = 480;
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(cx, cy) - 60;
  const positions = useMemo(() => {
    const out = new Map<string, { x: number; y: number }>();
    const n = entities.length;
    if (n === 0) return out;
    const isEdge = (id: string) => edges.some((e) => e.source === id || e.target === id);
    const nodeList = [...entities];
    if (n === 1) {
      out.set(nodeList[0].entity_id, { x: cx, y: cy });
      return out;
    }
    nodeList.forEach((node, i) => {
      const isConnected = isEdge(node.entity_id) || n === 1;
      const ring = isConnected ? 0.62 : 0.95;
      const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
      out.set(node.entity_id, {
        x: cx + Math.cos(angle) * radius * ring,
        y: cy + Math.sin(angle) * radius * ring,
      });
    });
    return out;
  }, [cx, cy, edges, entities, radius]);

  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      {edges.length === 0 ? (
        <p className="py-2 text-sm text-on-surface-variant">
          {entities.length} entities are indexed, but the backend returned no entity links — a graph
          cannot be drawn without real edges.
        </p>
      ) : null}
      <svg
        width={width}
        height={height}
        className="mx-auto border border-outline bg-surface-container"
        role="img"
        aria-label="Knowledge graph of real entities and links"
      >
        {edges.map((edge, i) => {
          const a = positions.get(edge.source);
          const b = positions.get(edge.target);
          if (!a || !b) return null;
          const active = selectedId !== null && (edge.source === selectedId || edge.target === selectedId);
          return (
            <line
              key={`${edge.source}-${edge.target}-${i}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={active ? "#facc15" : "#475569"}
              strokeWidth={active ? 2 : 1}
            />
          );
        })}
        {entities.map((entity) => {
          const p = positions.get(entity.entity_id);
          if (!p) return null;
          const isSelected = entity.entity_id === selectedId;
          const isNeighbor = neighborIds.has(entity.entity_id);
          const r = isSelected ? 9 : isNeighbor ? 7 : 5;
          return (
            <g key={entity.entity_id} transform={`translate(${p.x}, ${p.y})`} onClick={() => onSelect(entity.entity_id)} className="cursor-pointer">
              <circle r={r + 3} fill={isSelected ? "#facc15" : isNeighbor ? "#38bdf8" : "transparent"} opacity={isSelected || isNeighbor ? 0.35 : 0} />
              <circle r={r} fill={TYPE_COLORS[entity.entity_type] ?? "#94a3b8"} stroke="#0f172a" strokeWidth={1} />
              <text y={r + 12} textAnchor="middle" className="fill-on-surface-variant font-mono text-[9px]">
                {entity.name.length > 18 ? `${entity.name.slice(0, 17)}…` : entity.name}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-2 text-center font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
        {entities.length} entities · {edges.length} real edges · click a node to inspect
      </p>
    </div>
  );
}

function ListView({
  entities,
  edges,
  selectedId,
  neighborIds,
  onSelect,
}: {
  entities: KnowledgeEntity[];
  edges: Edge[];
  selectedId: string | null;
  neighborIds: Set<string>;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="min-h-0 flex-1 overflow-auto p-4">
      <table className="w-full border-collapse text-sm">
        <thead>
          <tr className="border-b border-outline text-left font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
            <th className="px-2 py-2">Name</th>
            <th className="px-2 py-2">Type</th>
            <th className="px-2 py-2">Classification</th>
            <th className="px-2 py-2">Confidence</th>
            <th className="px-2 py-2">Links</th>
          </tr>
        </thead>
        <tbody>
          {entities.map((entity) => {
            const isSelected = entity.entity_id === selectedId;
            const isNeighbor = neighborIds.has(entity.entity_id);
            const linkCount = edges.filter(
              (e) => e.source === entity.entity_id || e.target === entity.entity_id,
            ).length;
            return (
              <tr
                key={entity.entity_id}
                className={`cursor-pointer border-b border-outline-variant ${
                  isSelected ? "bg-surface-container-high" : isNeighbor ? "bg-primary-container/10" : ""
                }`}
                onClick={() => onSelect(entity.entity_id)}
              >
                <td className="px-2 py-2 font-bold text-on-surface">{entity.name}</td>
                <td className="px-2 py-2 font-mono text-xs text-on-surface-variant">{entity.entity_type}</td>
                <td className="px-2 py-2"><BrutalBadge tone="muted">{entity.classification ?? "INTERNAL"}</BrutalBadge></td>
                <td className="px-2 py-2 font-mono text-xs text-on-surface-variant">{String(entity.confidence ?? "—")}</td>
                <td className="px-2 py-2 font-mono text-xs text-on-surface-variant">{linkCount}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
        {entities.length} entities · {edges.length} real edges · click a row to inspect
      </p>
    </div>
  );
}