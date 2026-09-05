"use client";

import { apiBase } from "@/lib/env";

export type ApiErrorKind =
  | "unauthorized"
  | "forbidden"
  | "validation"
  | "rate_limited"
  | "server"
  | "network"
  | "timeout"
  | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number;
  readonly details: unknown;

  constructor(kind: ApiErrorKind, status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.details = details;
  }
}

export interface RequestOptions extends Omit<RequestInit, "body" | "headers" | "signal"> {
  token?: string | null;
  body?: unknown;
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  /** Retried only for idempotent GETs on network failure / 429 / 5xx. Never for mutations. */
  retryGet?: boolean;
}

const DEFAULT_TIMEOUT_MS = 30000;

function classify(status: number, message: string, details?: unknown): ApiError {
  if (status === 401) return new ApiError("unauthorized", status, message, details);
  if (status === 403) return new ApiError("forbidden", status, message, details);
  if (status === 422) return new ApiError("validation", status, message, details);
  if (status === 429) return new ApiError("rate_limited", status, message, details);
  if (status >= 500) return new ApiError("server", status, message, details);
  return new ApiError("unknown", status, message, details);
}

function extractMessage(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const detail = record.detail;
    if (typeof detail === "string" && detail !== "") return detail;
    const error = record.error;
    if (error && typeof error === "object") {
      const message = (error as Record<string, unknown>).message;
      if (typeof message === "string" && message !== "") return message;
    }
  }
  return `Request failed (${status})`;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const {
    token,
    body,
    headers = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
    signal: outerSignal,
    retryGet = true,
    ...rest
  } = options;
  const method = (rest.method ?? "GET").toUpperCase();
  const requestHeaders: Record<string, string> = {
    "Content-Type": "application/json",
    ...headers,
  };
  if (token) requestHeaders["Authorization"] = `Bearer ${token}`;

  const attempt = async (): Promise<T> => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);
    const combined = outerSignal
      ? AbortSignal.any([outerSignal, controller.signal])
      : controller.signal;
    try {
      const resp = await fetch(`${apiBase()}${path}`, {
        ...rest,
        method,
        headers: requestHeaders,
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: combined,
      });
      if (!resp.ok) {
        let parsed: unknown = null;
        try {
          parsed = await resp.json();
        } catch {
          parsed = null;
        }
        throw classify(resp.status, extractMessage(resp.status, parsed), parsed);
      }
      if (resp.status === 204) return undefined as T;
      return (await resp.json()) as T;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      if (error instanceof DOMException && error.name === "TimeoutError") {
        throw new ApiError("timeout", 0, `Request timed out after ${timeoutMs}ms`);
      }
      if (error instanceof DOMException && error.name === "AbortError") {
        throw new ApiError("unknown", 0, "Request was cancelled");
      }
      throw new ApiError("network", 0, error instanceof Error ? error.message : "Network error");
    } finally {
      clearTimeout(timer);
    }
  };

  try {
    return await attempt();
  } catch (error) {
    const retryable =
      retryGet &&
      method === "GET" &&
      error instanceof ApiError &&
      (error.kind === "network" || error.kind === "timeout" || error.status === 429 || error.status >= 500);
    if (!retryable) throw error;
    await new Promise((resolve) => setTimeout(resolve, 500));
    return attempt();
  }
}
