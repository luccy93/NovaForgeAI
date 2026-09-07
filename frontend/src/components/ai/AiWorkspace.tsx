"use client";

/* eslint-disable react-hooks/set-state-in-effect -- must clear stale tenant data synchronously on context switch */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ConversationList } from "@/components/ai/ConversationList";
import { MessageTimeline } from "@/components/ai/MessageTimeline";
import { Composer, type ComposerState } from "@/components/ai/Composer";
import { ContextPanel } from "@/components/ai/ContextPanel";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { api, clearToken, getToken, streamChatResponse } from "@/lib/api";
import type { ChatMessage, ChatSource, ConversationDetail, ConversationSummary } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";

function sessionExpired() {
  clearToken();
  window.location.href = "/auth/login";
}

export function AiWorkspace() {
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationsLoading, setConversationsLoading] = useState(true);
  const [conversationsError, setConversationsError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sendState, setSendState] = useState<ComposerState>("idle");
  const [streamingContent, setStreamingContent] = useState("");
  const [responseModel, setResponseModel] = useState<string | null>(null);
  const [responseConfidence, setResponseConfidence] = useState<number | null>(null);
  const [responseSources, setResponseSources] = useState<ChatSource[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<ConversationSummary | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [streamedWithoutMetadata, setStreamedWithoutMetadata] = useState(false);
  const [needsRetry, setNeedsRetry] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const lastUserMessageRef = useRef<string>("");
  const streamedAnyRef = useRef(false);
  const conversationRef = useRef<string | null>(null);
  const loadingIdRef = useRef<string | null>(null);

  const pushToast = useToastStore((s) => s.push);

  const loadConversations = useCallback(async () => {
    const token = getToken();
    if (!token) {
      window.location.href = "/auth/login";
      return;
    }
    setConversationsLoading(true);
    setConversationsError(null);
    try {
      const res = await api.listConversations(token, 50, 0);
      setConversations(Array.isArray(res) ? res : []);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      setConversationsError(e instanceof Error ? e.message : "Failed to load conversations");
    } finally {
      setConversationsLoading(false);
    }
  }, []);

  const resetAllState = useCallback(() => {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    loadingIdRef.current = null;
    setActiveId(null);
    conversationRef.current = null;
    setMessages([]);
    setSendState("idle");
    setStreamingContent("");
    setResponseModel(null);
    setResponseConfidence(null);
    setResponseSources([]);
    setDetailLoading(false);
    setDetailError(null);
    setContextLoading(false);
    setStreamedWithoutMetadata(false);
  }, []);

  useEffect(() => {
    void loadConversations();
    const handler = () => {
      resetAllState();
      setConversations([]);
      void loadConversations();
    };
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
    };
  }, [loadConversations, resetAllState]);

  // Terminate any active stream on unmount/logout
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort();
        abortRef.current = null;
      }
    };
  }, []);

  async function loadConversation(id: string) {
    const token = getToken();
    if (!token) return;
    if (abortRef.current) abortRef.current.abort();
    loadingIdRef.current = id;
    setActiveId(id);
    setDetailLoading(true);
    setDetailError(null);
    setContextLoading(true);
    setStreamedWithoutMetadata(false);
    try {
      const detail: ConversationDetail = await api.getConversation(token, id);
      // Ignore stale responses if the user switched context during the fetch.
      if (loadingIdRef.current !== id) return;
      setMessages(detail.messages ?? []);
      setSendState("idle");
      setStreamingContent("");
    } catch (e) {
      if (loadingIdRef.current !== id) return;
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      if (e instanceof ApiError && e.status === 404) {
        setDetailError("Conversation not found");
        setActiveId(null);
        conversationRef.current = null;
        setMessages([]);
        void loadConversations();
      } else {
        setDetailError(e instanceof Error ? e.message : "Failed to load conversation");
      }
    } finally {
      if (loadingIdRef.current === id) {
        setDetailLoading(false);
        setContextLoading(false);
      }
    }
  }

  function appendAssistant(content: string, source: "stream" | "fallback") {
    setMessages((prev) => [
      ...prev,
      { id: `assistant-${Date.now()}`, role: "assistant", content, created_at: new Date().toISOString() },
    ]);
    setStreamingContent("");
    setSendState("idle");
    setNeedsRetry(false);
    setContextLoading(false);
    setStreamedWithoutMetadata(source === "stream");
    void loadConversations();
  }

  async function handleSend(raw: string) {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const content = raw.trim();
    if (!content) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, userMessage]);
    setSendState("streaming");
    setStreamingContent("");
    setNeedsRetry(false);
    setResponseModel(null);
    setResponseConfidence(null);
    setResponseSources([]);
    setContextLoading(true);
    setStreamedWithoutMetadata(false);

    const controller = new AbortController();
    abortRef.current = controller;
    streamedAnyRef.current = false;

    const conversationId = conversationRef.current;

    try {
      let receivedChunk = false;
      let accumulated = "";
      for await (const event of streamChatResponse(
        "/chat/stream",
        token,
        { message: content, ...(conversationId ? { conversation_id: conversationId } : {}) },
        controller.signal,
      )) {
        if (event.type === "chunk" && event.content) {
          receivedChunk = true;
          streamedAnyRef.current = true;
          accumulated += event.content;
          setStreamingContent(accumulated);
        } else if (event.type === "done" && event.conversation_id) {
          conversationRef.current = event.conversation_id;
          setActiveId(event.conversation_id);
        }
      }

      if (!receivedChunk && !streamedAnyRef.current) {
        // Stream completed but produced no content events — treat as a pre-content failure.
        throw new ApiError("server", 0, "Stream ended without content");
      }

      // Stream completed successfully. The stream endpoint does not expose
      // model/confidence/sources and does not persist the assistant reply, so we
      // keep the streamed text locally and show metadata as unavailable — we do
      // NOT re-run /chat to fetch it (that would duplicate the AI operation).
      setActiveId(conversationRef.current);
      appendAssistant(accumulated, "stream");
    } catch (e) {
      if (e instanceof DOMException && e.name === "AbortError") {
        // User-cancelled generation.
        setSendState("idle");
        setStreamingContent("");
        setContextLoading(false);
        setNeedsRetry(false);
        return;
      }
      if (streamedAnyRef.current) {
        // Partial content already delivered — do NOT auto-fallback (would
        // duplicate the AI operation/cost). Surface an explicit retry.
        setSendState("stream-error");
        setNeedsRetry(true);
        setContextLoading(false);
        return;
      }
      // No content delivered — safe to retry via the non-streaming endpoint.
      setSendState("processing");
      try {
        const res = await api.chat(token, {
          message: content,
          ...(conversationId ? { conversation_id: conversationId } : {}),
        });
        conversationRef.current = res.conversation_id;
        setActiveId(res.conversation_id);
        setResponseModel(res.model_used || null);
        setResponseConfidence(res.confidence ?? null);
        setResponseSources(Array.isArray(res.sources) ? res.sources : []);
        appendAssistant(res.answer, "fallback");
      } catch (fallbackError) {
        if (fallbackError instanceof ApiError && fallbackError.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        setSendState("error");
        setNeedsRetry(true);
        setContextLoading(false);
        pushToast(
          "error",
          fallbackError instanceof Error ? fallbackError.message : "Failed to generate response",
        );
      }
    }
  }

  function handleCancel() {
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
  }

  function retryLast() {
    const last = lastUserMessageRef.current;
    if (!last || sendState === "streaming" || sendState === "processing") return;
    void handleSend(last);
  }

  async function handleDelete(convo: ConversationSummary) {
    setPendingDelete(null);
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteConversation(token, convo.id);
      setConversations((prev) => prev.filter((item) => item.id !== convo.id));
      if (conversationRef.current === convo.id) {
        resetAllState();
      }
      pushToast("info", "Conversation deleted");
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        sessionExpired();
        return;
      }
      pushToast("error", e instanceof Error ? e.message : "Failed to delete conversation");
    }
  }

  // Track last user message for explicit retry.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (last && last.role === "user") lastUserMessageRef.current = last.content;
  }, [messages]);

  const streaming = sendState === "streaming";

  const sources = useMemo(() => responseSources, [responseSources]);

  return (
    <div className="flex h-full min-h-0">
      <aside className="hidden w-64 shrink-0 border-r border-outline bg-surface md:block" aria-label="Conversations">
        <ConversationList
          conversations={conversations}
          activeId={activeId}
          loading={conversationsLoading}
          onSelect={(id) => void loadConversation(id)}
          onNew={() => {
            resetAllState();
          }}
          onDelete={(id) => {
            const convo = conversations.find((c) => c.id === id);
            if (convo) setPendingDelete(convo);
          }}
        />
      </aside>

      <main className="relative flex min-h-0 min-w-0 flex-1 flex-col" aria-label="AI conversation">
        {conversationsError ? (
          <div className="p-4">
            <BrutalErrorState
              title="Conversation list unavailable"
              description={conversationsError}
              onRetry={() => void loadConversations()}
            />
          </div>
        ) : detailError ? (
          <div className="p-4">
            <BrutalErrorState
              title="Conversation unavailable"
              description={detailError}
              onRetry={() => (activeId ? void loadConversation(activeId) : undefined)}
            />
          </div>
        ) : (
          <>
            <MessageTimeline
              messages={messages}
              streamingContent={streamingContent}
              streaming={streaming}
              sources={sources}
            />
            {needsRetry && (
              <div className="flex items-center justify-between gap-2 border-t border-outline-variant px-4 py-2">
                <p className="font-mono text-[11px] uppercase tracking-widest text-error">
                  Generation incomplete — retrying will re-run the request
                </p>
                <BrutalButton variant="default" size="sm" onClick={retryLast}>
                  Retry
                </BrutalButton>
              </div>
            )}
            <Composer state={sendState} onSend={(content) => void handleSend(content)} onCancel={handleCancel} />
          </>
        )}
      </main>

      {activeId && (
        <ContextPanel
          model={responseModel}
          provider={null}
          confidence={responseConfidence}
          sources={sources}
          streamedWithoutMetadata={streamedWithoutMetadata}
          loading={detailLoading || contextLoading}
        />
      )}

      <BrutalModal
        open={pendingDelete !== null}
        title="Delete conversation?"
        onClose={() => setPendingDelete(null)}
        actions={
          <>
            <BrutalButton variant="default" onClick={() => setPendingDelete(null)}>
              Cancel
            </BrutalButton>
            <BrutalButton
              variant="default"
              onClick={() => {
                if (pendingDelete) void handleDelete(pendingDelete);
              }}
            >
              Delete
            </BrutalButton>
          </>
        }
      >
        <p className="text-on-surface-variant">
          <span className="font-bold text-on-surface">{pendingDelete?.title}</span> will be permanently
          removed. This cannot be undone.
        </p>
      </BrutalModal>
    </div>
  );
}