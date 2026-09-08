"use client";

import { useEffect, useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { AiReviewDetail, PatchOut, ReviewFinding } from "@/types/code";
import { asString, devErrorMessage } from "./dev-utils";

export function DeveloperPatches({ repoId }: { repoId: string }) {
  const [patches, setPatches] = useState<PatchOut[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<PatchOut | null>(null);
  const [loadingPatch, setLoadingPatch] = useState(false);
  const [patchError, setPatchError] = useState<string | null>(null);

  const [reviewId, setReviewId] = useState("");
  const [review, setReview] = useState<AiReviewDetail | null>(null);
  const [loadingReview, setLoadingReview] = useState(false);
  const [reviewError, setReviewError] = useState<string | null>(null);

  const loadList = async () => {
    const token = getToken();
    if (!token) return;
    setLoadingList(true);
    setListError(null);
    try {
      const data = await api.aiDevListPatches(token, repoId);
      setPatches(Array.isArray(data.items) ? data.items : []);
      setLoaded(true);
    } catch (e) {
      const msg = devErrorMessage(e, "patches");
      if (msg) setListError(msg);
    } finally {
      setLoadingList(false);
    }
  };

  useEffect(() => {
    // The panel remounts per repository (parent keys it), so this runs once per repo.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadList();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [repoId]);

  const selectPatch = async (patchId: string) => {
    const token = getToken();
    if (!token) return;
    setSelectedId(patchId);
    setLoadingPatch(true);
    setPatchError(null);
    try {
      const data = await api.aiDevGetPatch(token, patchId);
      setSelected(data);
    } catch (e) {
      const msg = devErrorMessage(e, "patch");
      if (msg) setPatchError(msg);
    } finally {
      setLoadingPatch(false);
    }
  };

  const loadReview = async () => {
    const token = getToken();
    if (!token || !reviewId.trim()) return;
    setLoadingReview(true);
    setReviewError(null);
    try {
      const data = await api.aiDevGetReview(token, reviewId.trim());
      setReview(data);
    } catch (e) {
      const msg = devErrorMessage(e, "review");
      if (msg) setReviewError(msg);
    } finally {
      setLoadingReview(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="border border-outline-variant bg-surface p-2 font-mono text-[10px] text-on-surface-variant">
        New review and refactor runs are not available here: the backend only starts reviews from inlined file
        content, which indexed repositories do not expose. Existing reviews can be looked up by ID, and candidate
        AI patches are read-only below (applying patches is governed by the backend approval flow).
      </p>

      <div>
        <h3 className="mb-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          Existing review
        </h3>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void loadReview();
          }}
          className="flex flex-wrap items-end gap-2"
        >
          <div className="min-w-56 flex-1">
            <BrutalInput
              id="dev-review-id"
              label="Review ID"
              placeholder="review id"
              value={reviewId}
              onChange={(e) => setReviewId(e.target.value)}
            />
          </div>
          <BrutalButton type="submit" size="sm" disabled={loadingReview || !reviewId.trim()}>
            {loadingReview ? "Loading…" : "Load review"}
          </BrutalButton>
        </form>
        {reviewError ? (
          <BrutalErrorState title="Review unavailable" description={reviewError} onRetry={() => void loadReview()} />
        ) : null}
        {review ? <ReviewDetail data={review} /> : null}
      </div>

      <div>
        <h3 className="mb-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          AI patches
        </h3>
        {listError ? (
          <BrutalErrorState title="Patches unavailable" description={listError} onRetry={() => void loadList()} />
        ) : null}
        {loadingList ? <BrutalSkeleton className="h-24 w-full" label="Loading patches" /> : null}
        {loaded && !loadingList && patches.length === 0 ? (
          <BrutalEmptyState title="AI patches" description="No AI patches exist for this repository yet." />
        ) : null}
        {patches.length > 0 ? (
          <ul className="space-y-1">
            {patches.map((patch) => (
              <li key={patch.id} className="border border-outline bg-surface">
                <div className="flex items-center gap-2 p-2">
                  <button
                    type="button"
                    onClick={() => void selectPatch(patch.id)}
                    aria-pressed={selectedId === patch.id}
                    className="min-w-0 flex-1 truncate text-left font-mono text-xs font-bold text-on-surface hover:underline"
                  >
                    {patch.title || patch.id}
                  </button>
                  <BrutalBadge tone={patchTone(patch.status)}>{patch.status}</BrutalBadge>
                  <span className="font-mono text-[10px] text-on-surface-variant">{patch.branch}</span>
                </div>
                {selectedId === patch.id ? (
                  <div className="space-y-2 border-t border-outline-variant p-2">
                    {loadingPatch ? <BrutalSkeleton className="h-20 w-full" label="Loading patch" /> : null}
                    {patchError ? (
                      <BrutalErrorState
                        title="Patch unavailable"
                        description={patchError}
                        onRetry={() => void selectPatch(patch.id)}
                      />
                    ) : null}
                    {selected && !loadingPatch ? <PatchDetail data={selected} /> : null}
                  </div>
                ) : null}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}

function PatchDetail({ data }: { data: PatchOut }) {
  const diffEntries = Object.entries(data.diffs ?? {});
  return (
    <div className="space-y-2">
      {data.model ? <p className="font-mono text-[10px] text-on-surface-variant">model {data.model}</p> : null}
      {data.base_commit_sha ? (
        <p className="font-mono text-[10px] text-on-surface-variant">base {data.base_commit_sha}</p>
      ) : null}
      {data.applied_at ? (
        <p className="font-mono text-[10px] text-on-surface-variant">applied {data.applied_at}</p>
      ) : null}
      {data.error ? (
        <pre className="whitespace-pre-wrap border border-error bg-surface p-2 font-mono text-[11px] text-error">
          {data.error}
        </pre>
      ) : null}
      {diffEntries.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">No diff text available.</p>
      ) : (
        <ul className="space-y-1">
          {diffEntries.map(([path, diff]) => (
            <li key={path}>
              <p className="font-mono text-[11px] font-bold text-on-surface">{path}</p>
              <pre className="max-h-48 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface">
                {diff}
              </pre>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewDetail({ data }: { data: AiReviewDetail }) {
  const summary = summaryText(data.review);
  const findings = Array.isArray(data.findings) ? data.findings : [];
  return (
    <div className="mt-2 space-y-2 border border-outline bg-surface p-2">
      {summary ? <p className="break-words text-sm text-on-surface-variant">{summary}</p> : null}
      <p className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Findings ({findings.length})
      </p>
      {findings.length === 0 ? (
        <p className="font-mono text-[11px] text-on-surface-variant">No findings recorded.</p>
      ) : (
        <ul className="space-y-1">
          {findings.map((f) => (
            <li key={f.id} className="border border-outline bg-surface p-2">
              <div className="flex flex-wrap items-center gap-2">
                <BrutalBadge tone={findingTone(f.severity)}>{f.severity}</BrutalBadge>
                <span className="font-mono text-[11px] font-bold text-on-surface">{f.category}</span>
                <span className="font-mono text-[10px] text-on-surface-variant">{f.status}</span>
              </div>
              <p className="mt-1 break-words text-sm text-on-surface">{f.message}</p>
              {f.file_path ? (
                <p className="mt-1 font-mono text-[10px] text-on-surface-variant">
                  {f.file_path}
                  {f.line_start != null ? `:${f.line_start}${f.line_end != null ? `–${f.line_end}` : ""}` : ""}
                </p>
              ) : null}
              {f.reason ? <p className="mt-1 text-sm text-on-surface-variant">{f.reason}</p> : null}
              {f.suggested_fix ? (
                <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                  {f.suggested_fix}
                </pre>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function summaryText(review: Record<string, unknown>): string {
  const text = asString(review?.summary) ?? asString(review?.description) ?? asString(review?.status);
  return text ?? "";
}

function patchTone(status: string): "yellow" | "default" | "error" | "muted" {
  const s = status.toLowerCase();
  if (s.includes("applied") || s.includes("completed")) return "yellow";
  if (s.includes("fail") || s.includes("error") || s.includes("rejected") || s.includes("conflict")) return "error";
  if (s.includes("rolling") || s.includes("rolled_back")) return "muted";
  return "default";
}

function findingTone(severity: string): "yellow" | "default" | "error" | "muted" {
  const s = (severity ?? "").toLowerCase();
  if (s === "high" || s === "critical") return "error";
  if (s === "medium" || s === "warning") return "yellow";
  if (s === "info" || s === "low") return "muted";
  return "default";
}

export type { ReviewFinding };