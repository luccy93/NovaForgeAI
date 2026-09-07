"use client";

import type { ChatSource } from "@/types/api";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";

export function ContextPanel({
  model,
  provider,
  confidence,
  sources,
  streamedWithoutMetadata,
  loading,
}: {
  model: string | null;
  provider: string | null;
  confidence: number | null;
  sources: ChatSource[];
  streamedWithoutMetadata?: boolean;
  loading: boolean;
}) {
  return (
    <aside
      aria-label="Conversation context"
      className="hidden w-80 shrink-0 border-l border-outline p-4 xl:block"
    >
      <p className="mb-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        Context
      </p>
      {loading ? (
        <p className="font-mono text-xs text-on-surface-variant">Loading context…</p>
      ) : streamedWithoutMetadata && !model && sources.length === 0 ? (
        <div>
          <BrutalEmptyState
            title="No metadata for this reply"
            description="Streamed responses don't expose model, confidence or sources."
          />
          <p className="mt-3 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
            Streamed answer is kept locally; sources are surfaced on non-streaming replies.
          </p>
        </div>
      ) : !model && !provider && sources.length === 0 ? (
        <BrutalEmptyState
          title="No context yet"
          description="Send a message to surface model, sources and confidence."
        />
      ) : (
        <div className="space-y-4">
          {(model || provider) && (
            <div>
              <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                Model
              </p>
              <div className="flex items-center gap-2">
                <BrutalBadge tone="yellow">{model || "unknown"}</BrutalBadge>
                {provider && <BrutalBadge tone="default">{provider}</BrutalBadge>}
              </div>
            </div>
          )}
          {confidence != null && (
            <div>
              <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                Confidence
              </p>
              <p className="font-mono text-lg text-on-surface">{(confidence * 100).toFixed(0)}%</p>
            </div>
          )}
          {sources.length > 0 && (
            <div>
              <p className="mb-2 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
                Sources ({sources.length})
              </p>
              <ul className="space-y-2">
                {sources.map((src, i) => (
                  <li key={i} className="border border-outline bg-surface p-2">
                    {src.source && (
                      <p className="font-mono text-[10px] font-bold uppercase text-primary-container">
                        {src.source}
                      </p>
                    )}
                    {src.text && <p className="mt-1 text-xs text-on-surface-variant">{src.text}</p>}
                    {src.score != null && (
                      <p className="mt-1 font-mono text-[10px] text-on-surface-variant/60">
                        relevance {(src.score * 100).toFixed(0)}%
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}