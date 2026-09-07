"use client";

import { memo } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, ChatSource } from "@/types/api";
import { cn } from "@/lib/utils";

function formatTime(iso?: string): string {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } catch {
    return "";
  }
}

function SourcesBlock({ sources }: { sources: ChatSource[] }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 border-t border-outline-variant pt-3">
      <p className="mb-1 font-mono text-[10px] uppercase tracking-widest text-on-surface-variant">
        Sources
      </p>
      <ul className="space-y-1">
        {sources.map((src, i) => (
          <li key={i} className="text-xs text-on-surface-variant">
            {src.source && (
              <span className="font-mono font-bold text-primary-container">{src.source}</span>
            )}
            {src.text && <span className="ml-1 line-clamp-2">{src.text}</span>}
            {src.score != null && (
              <span className="ml-1 font-mono text-[10px] text-on-surface-variant/60">
                ({(src.score * 100).toFixed(0)}%)
              </span>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

export const MessageBubble = memo(function MessageBubble({
  message,
  sources,
}: {
  message: ChatMessage;
  sources?: ChatSource[];
}) {
  const isUser = message.role === "user";
  return (
    <article
      role={isUser ? "note" : "article"}
      aria-label={isUser ? "Your message" : "AI response"}
      className={cn(
        "group flex w-full gap-3 px-4 py-3",
        isUser ? "justify-end" : "justify-start",
      )}
    >
      <div
        className={cn(
          "max-w-[75%] border px-4 py-3 text-body-md",
          isUser
            ? "border-primary-container bg-primary-container/10 text-on-surface"
            : "border-outline bg-surface-container text-on-surface",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap">{message.content}</p>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none prose-p:my-1 prose-pre:my-2 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
            <Markdown remarkPlugins={[remarkGfm]}>{message.content}</Markdown>
          </div>
        )}
        {!isUser && sources && <SourcesBlock sources={sources} />}
        <p className="mt-2 font-mono text-[10px] text-on-surface-variant/50">
          {formatTime(message.created_at)}
        </p>
      </div>
    </article>
  );
});
