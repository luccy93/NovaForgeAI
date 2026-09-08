"use client";

import { useState } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { ChangeSummaryOut2 } from "@/types/code";
import { devErrorMessage } from "./dev-utils";

export function DeveloperChanges({ repoId }: { repoId: string }) {
  const [commitSha, setCommitSha] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ChangeSummaryOut2 | null>(null);

  const run = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.aiDevChangesSummary(token, {
        repository_id: repoId,
        commit_sha: commitSha.trim() || null,
      });
      setResult(data);
    } catch (e) {
      const msg = devErrorMessage(e, "change analysis");
      if (msg) setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="min-w-56 flex-1">
            <BrutalInput
              id="dev-changes-commit"
              label="Commit SHA (optional)"
              placeholder="e.g. 9f2b1c7"
              value={commitSha}
              onChange={(e) => setCommitSha(e.target.value)}
            />
          </div>
          <BrutalButton type="submit" size="sm" disabled={loading}>
            {loading ? "Analyzing…" : "Analyze changes"}
          </BrutalButton>
        </div>
      </form>

      {loading ? <BrutalSkeleton className="h-32 w-full" label="Analyzing changes" /> : null}
      {error ? (
        <BrutalErrorState title="Change analysis unavailable" description={error} onRetry={() => void run()} />
      ) : null}
      {result && !loading ? (
        <div className="space-y-3">
          <dl className="grid grid-cols-2 gap-2">
            <Stat label="Commit" value={result.commit_sha ?? "HEAD"}>
              <p className="mt-0.5 break-words font-mono text-[11px] text-on-surface-variant">{result.commit_message ?? ""}</p>
              <p className="mt-0.5 font-mono text-[10px] text-on-surface-variant/70">{result.author ?? ""}</p>
            </Stat>
            <Stat label="Stats" value={`+${result.stats.additions} −${result.stats.deletions}`}>
              <p className="mt-0.5 font-mono text-[11px] text-on-surface-variant">
                {result.stats.files} files changed
              </p>
            </Stat>
          </dl>
          {result.notes.length > 0 ? (
            <div>
              <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Notes</h3>
              <ul className="mt-1 space-y-1">
                {result.notes.map((note, i) => (
                  <li key={i} className="border border-outline bg-surface p-2 font-mono text-[11px] text-on-surface-variant">
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function Stat({ label, value, children }: { label: string; value: string; children?: React.ReactNode }) {
  return (
    <div className="border border-outline bg-surface p-2">
      <dt className="font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">{label}</dt>
      <dd className="mt-0.5 font-mono text-xs font-bold text-on-surface">{value || "—"}</dd>
      {children}
    </div>
  );
}