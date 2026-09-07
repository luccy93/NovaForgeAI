"use client";

import type { ConversationSummary } from "@/types/api";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { cn } from "@/lib/utils";

function formatRelative(iso?: string): string {
  if (!iso) return "";
  try {
    const date = new Date(iso);
    const now = Date.now();
    const diff = now - date.getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "just now";
    if (min < 60) return `${min}m ago`;
    const hrs = Math.floor(min / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 7) return `${days}d ago`;
    return date.toLocaleDateString();
  } catch {
    return "";
  }
}

export function ConversationList({
  conversations,
  activeId,
  loading,
  onSelect,
  onNew,
  onDelete,
}: {
  conversations: ConversationSummary[];
  activeId: string | null;
  loading: boolean;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-outline p-4">
        <BrutalButton variant="yellow" onClick={onNew} className="w-full" aria-label="New conversation">
          + New conversation
        </BrutalButton>
      </div>
      <div className="flex-1 overflow-y-auto p-2" aria-label="Conversation history">
        {loading && conversations.length === 0 ? (
          <div className="space-y-2 p-2">
            <BrutalSkeleton className="h-12" label="Loading conversations" />
            <BrutalSkeleton className="h-12" label="Loading conversations" />
            <BrutalSkeleton className="h-12" label="Loading conversations" />
          </div>
        ) : conversations.length === 0 ? (
          <div className="p-3">
            <BrutalEmptyState title="No conversations yet" description="Start a new conversation to begin." />
          </div>
        ) : (
          <ul className="space-y-1">
            {conversations.map((convo) => (
              <li key={convo.id}>
                <div
                  className={cn(
                    "group flex items-center justify-between border px-3 py-2 transition-colors",
                    activeId === convo.id
                      ? "border-primary-container bg-surface-container-high"
                      : "border-transparent hover:border-outline hover:bg-surface-container",
                  )}
                >
                  <button
                    type="button"
                    onClick={() => onSelect(convo.id)}
                    aria-current={activeId === convo.id ? "true" : undefined}
                    className="flex-1 text-left"
                  >
                    <p className="truncate text-sm font-bold text-on-surface">{convo.title}</p>
                    <p className="mt-0.5 font-mono text-[10px] text-on-surface-variant">
                      {convo.message_count} msg · {formatRelative(convo.updated_at)}
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(convo.id)}
                    aria-label={`Delete ${convo.title}`}
                    className="ml-2 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-on-surface-variant opacity-0 transition-opacity group-hover:opacity-100 hover:text-error"
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
