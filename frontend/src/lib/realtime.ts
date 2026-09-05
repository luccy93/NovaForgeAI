"use client";

import { apiBase } from "@/lib/env";

export type ConnectionState = "idle" | "connecting" | "open" | "closed" | "error";
export type StreamMessage = { event: string; data: unknown };

const MAX_BACKOFF_MS = 30000;

/**
 * Server-sent event stream foundation: connection state, reconnect with
 * backoff, cleanup and cancellation. No fake data — consumers provide
 * real endpoints and handlers.
 */
export class EventStream {
  private source: EventSource | null = null;
  private backoffMs = 1000;
  private closed = false;
  private listeners = new Set<(state: ConnectionState) => void>();

  constructor(
    private readonly path: string,
    private readonly onMessage: (message: StreamMessage) => void,
    private readonly token?: string | null,
  ) {}

  onStateChange(listener: (state: ConnectionState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  private setState(state: ConnectionState) {
    for (const listener of this.listeners) listener(state);
  }

  connect(): void {
    if (typeof window === "undefined" || this.closed) return;
    this.setState("connecting");
    const url = new URL(`${apiBase()}${this.path}`);
    // Tokens travel as a query parameter only because EventSource
    // cannot set headers; prefer short-lived tokens.
    if (this.token) url.searchParams.set("access_token", this.token);
    const source = new EventSource(url.toString());
    this.source = source;
    source.onopen = () => {
      this.backoffMs = 1000;
      this.setState("open");
    };
    source.onmessage = (event) => {
      try {
        this.onMessage({ event: event.type || "message", data: JSON.parse(event.data) });
      } catch {
        this.onMessage({ event: "message", data: event.data });
      }
    };
    source.onerror = () => {
      source.close();
      if (this.closed) return;
      this.setState("error");
      const delay = this.backoffMs;
      this.backoffMs = Math.min(this.backoffMs * 2, MAX_BACKOFF_MS);
      setTimeout(() => {
        if (!this.closed) this.connect();
      }, delay);
    };
  }

  close(): void {
    this.closed = true;
    this.source?.close();
    this.source = null;
    this.setState("closed");
  }
}
