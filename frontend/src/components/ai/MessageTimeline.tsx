"use client";

import { useEffect, useRef } from "react";
import type { ChatMessage, ChatSource } from "@/types/api";
import { MessageBubble } from "@/components/ai/MessageBubble";
import { StreamingIndicator } from "@/components/ai/StreamingIndicator";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";

export function MessageTimeline({
  messages,
  streamingContent,
  streaming,
  sources,
}: {
  messages: ChatMessage[];
  streamingContent: string;
  streaming: boolean;
  sources: ChatSource[];
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: streaming ? "auto" : "smooth", block: "end" });
  }, [messages.length, streamingContent, streaming]);

  if (messages.length === 0 && !streaming) {
    return (
      <div className="flex flex-1 items-center justify-center p-8">
        <BrutalEmptyState
          title="Start a conversation"
          description="Ask anything. Responses surface retrieved context and citations when available."
        />
      </div>
    );
  }

  return (
    <section
      aria-label="Conversation messages"
      aria-live="polite"
      className="flex-1 overflow-y-auto"
    >
      <div className="flex flex-col py-4">
        {messages.map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            sources={message.role === "assistant" ? sources : undefined}
          />
        ))}
        {streaming && streamingContent.length > 0 && (
          <MessageBubble
            message={{ id: "__streaming__", role: "assistant", content: streamingContent }}
          />
        )}
        {streaming && streamingContent.length === 0 && <StreamingIndicator />}
        <div ref={bottomRef} />
      </div>
    </section>
  );
}
