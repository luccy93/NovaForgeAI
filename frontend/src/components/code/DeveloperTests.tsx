"use client";

import { useState } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { api, getToken } from "@/lib/api";
import type { AiDevTestRunOut } from "@/types/code";
import { asString, devErrorMessage } from "./dev-utils";

export function DeveloperTests({ repoId, defaultBranch }: { repoId: string; defaultBranch?: string | null }) {
  const [branch, setBranch] = useState(defaultBranch ?? "main");
  const [framework, setFramework] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AiDevTestRunOut | null>(null);

  const run = async () => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.aiDevTestGenerate(token, {
        repository_id: repoId,
        branch: branch.trim() || null,
        framework: framework.trim() || null,
      });
      setResult(data);
    } catch (e) {
      const msg = devErrorMessage(e, "test plan");
      if (msg) setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const statusMeta = result ? statusTone(result.status) : null;

  return (
    <div className="space-y-3">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <div className="flex flex-wrap items-end gap-2">
          <div className="w-48">
            <BrutalInput
              id="dev-tests-branch"
              label="Branch"
              value={branch}
              onChange={(e) => setBranch(e.target.value)}
            />
          </div>
          <div className="min-w-40 flex-1">
            <BrutalInput
              id="dev-tests-framework"
              label="Framework (optional)"
              placeholder="pytest, jest, …"
              value={framework}
              onChange={(e) => setFramework(e.target.value)}
            />
          </div>
          <BrutalButton type="submit" size="sm" disabled={loading}>
            {loading ? "Generating…" : "Suggest tests"}
          </BrutalButton>
        </div>
      </form>

      {loading ? <BrutalSkeleton className="h-32 w-full" label="Generating test plan" /> : null}
      {error ? (
        <BrutalErrorState title="Test planning unavailable" description={error} onRetry={() => void run()} />
      ) : null}
      {result && !loading ? (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <BrutalBadge tone={statusMeta?.tone ?? "default"}>{result.status}</BrutalBadge>
            {result.framework ? (
              <span className="font-mono text-[11px] text-on-surface-variant">{result.framework}</span>
            ) : null}
            {result.branch ? (
              <span className="font-mono text-[11px] text-on-surface-variant">branch {result.branch}</span>
            ) : null}
          </div>
          {result.duration_ms != null ? (
            <p className="font-mono text-[11px] text-on-surface-variant">duration {result.duration_ms} ms</p>
          ) : null}
          {asString(result.command) ? (
            <div>
              <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Command</h3>
              <pre className="mt-1 overflow-auto whitespace-pre border border-outline bg-surface p-3 font-mono text-[11px] text-on-surface">
                {asString(result.command)}
              </pre>
            </div>
          ) : null}
          {result.test_plan ? (
            <div>
              <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Test plan</h3>
              <pre className="mt-1 max-h-56 overflow-auto whitespace-pre-wrap border border-outline bg-surface p-3 font-mono text-[11px] text-on-surface">
                {typeof result.test_plan === "string" ? result.test_plan : JSON.stringify(result.test_plan, null, 2)}
              </pre>
            </div>
          ) : null}
          {asString(result.failures_analysis) ? (
            <div>
              <h3 className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Failures analysis</h3>
              <pre className="mt-1 whitespace-pre-wrap border border-outline bg-surface p-3 font-mono text-[11px] text-on-surface">
                {asString(result.failures_analysis)}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function statusTone(status: string): { tone: "yellow" | "default" | "error" | "muted" } {
  const s = status.toLowerCase();
  if (s.includes("completed") || s.includes("passed")) return { tone: "yellow" };
  if (s.includes("fail") || s.includes("error")) return { tone: "error" };
  if (s.includes("canceled") || s.includes("cancelled")) return { tone: "muted" };
  return { tone: "default" };
}