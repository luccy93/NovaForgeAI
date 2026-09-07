"use client";

import { useEffect, useMemo, useRef, useState, useCallback } from "react";
import { DashboardRealtime, isRealtimeAvailable, type DashboardRealtimeEvent, type RealtimeStatus } from "@/lib/dashboard-realtime";

/**
 * Wires a DashboardRealtime adapter into a component lifecycle.
 *
 * Honors tenant/workspace context: a context change closes the previous
 * stream and re-creates the adapter for the new scope. When no backend
 * subscription endpoint exists the status is `unavailable` and no connection
 * is attempted — the dashboard never pretends realtime is live.
 */
export function useDashboardRealtime(
  organizationId: string | null,
  workspaceId: string | null,
  handlers: {
    onEvent?: (event: DashboardRealtimeEvent) => void;
    onNotify?: (message: string, tone: "warning" | "error" | "info") => void;
  },
) {
  const [status, setStatus] = useState<RealtimeStatus>("unavailable");
  const [nonce, setNonce] = useState(0);
  const handlersRef = useRef(handlers);

  useEffect(() => {
    handlersRef.current = handlers;
  });

  const contextKey = `${organizationId ?? ""}:${workspaceId ?? ""}`;

  useEffect(() => {
    // No backend subscription contract exists yet — stay honestly unavailable.
    if (!isRealtimeAvailable()) return;
    const rt = new DashboardRealtime({
      endpoint: "/realtime/stream",
      token: typeof window !== "undefined" ? window.localStorage.getItem("nf_token") : null,
      organizationId,
      workspaceId,
      onStatusChange: (s) => setStatus(s),
      onEvent: (event) => handlersRef.current.onEvent?.(event),
      onNotify: (message, tone) => handlersRef.current.onNotify?.(message, tone),
    });
    rt.connect();
    return () => {
      rt.close();
    };
  }, [contextKey, organizationId, workspaceId, nonce]);

  const refresh = useCallback(() => {
    // Disconnect + reconnect for the current context.
    setNonce((n) => n + 1);
  }, []);

  const connected = status === "open";
  return useMemo(
    () => ({ status, connected, unavailable: status === "unavailable", refresh }),
    [status, connected, refresh],
  );
}