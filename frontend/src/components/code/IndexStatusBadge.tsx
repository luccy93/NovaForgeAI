"use client";

import { BrutalBadge } from "@/components/ui/BrutalBadge";

export type IndexState =
  | "loading"
  | "indexing"
  | "ready"
  | "stale"
  | "failed"
  | "no-data"
  | "unavailable";

const LABELS: Record<IndexState, string> = {
  loading: "Loading index",
  indexing: "Indexing",
  ready: "Indexed",
  stale: "Stale",
  failed: "Failed",
  "no-data": "No data",
  unavailable: "Index unavailable",
};

// Color-independent status: every state renders its full text label so
// severity is never conveyed by color alone.
export function IndexStatusBadge({ state }: { state: IndexState }) {
  const tone =
    state === "ready"
      ? "default"
      : state === "failed"
        ? "error"
        : state === "indexing" || state === "stale"
          ? "yellow"
          : "muted";
  return <BrutalBadge tone={tone}>{LABELS[state]}</BrutalBadge>;
}