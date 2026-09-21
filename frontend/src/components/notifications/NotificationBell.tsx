"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative unread-count load on mount and context switch */

import { useCallback, useEffect, useRef, useState } from "react";
import { Bell } from "lucide-react";
import { ApiError, api, getToken } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

/** Dispatched by the notification workspace after any read-state mutation. */
export const NOTIFICATIONS_CHANGED = "notifications:changed";

/**
 * AppShell notification entry. Reads the authoritative GET /notifications/unread-count.
 * Explicitly NOT realtime: the count is refreshed on mount, on tenant/workspace
 * context switches and on the notifications:changed event — never by polling.
 */
export function NotificationBell() {
  const [count, setCount] = useState<number | null>(null);
  const seqRef = useRef(0);
  const markExpired = useAuthStore((s) => s.markExpired);

  const refresh = useCallback(() => {
    const token = getToken();
    if (!token) {
      setCount(null);
      return;
    }
    const seq = ++seqRef.current;
    api
      .notificationsUnreadCount(token)
      .then((res) => {
        if (seq !== seqRef.current) return;
        setCount(typeof res.count === "number" ? res.count : null);
      })
      .catch((error: unknown) => {
        if (seq !== seqRef.current) return;
        setCount(null);
        if (error instanceof ApiError && error.kind === "unauthorized") {
          markExpired();
        }
      });
  }, [markExpired]);

  useEffect(() => {
    refresh();
    window.addEventListener("tenant:switched", refresh);
    window.addEventListener("workspace:switched", refresh);
    window.addEventListener(NOTIFICATIONS_CHANGED, refresh);
    return () => {
      window.removeEventListener("tenant:switched", refresh);
      window.removeEventListener("workspace:switched", refresh);
      window.removeEventListener(NOTIFICATIONS_CHANGED, refresh);
    };
  }, [refresh]);

  const unread = count && count > 0 ? count : null;
  return (
    <a
      href="/notifications"
      aria-label={unread ? `Notifications (${unread} unread)` : "Notifications"}
      title={unread ? `Notifications (${unread} unread)` : "Notifications"}
      className="relative flex min-h-[44px] min-w-[44px] items-center justify-center border border-outline p-2 text-on-surface-variant hover:border-primary-container hover:text-on-surface"
    >
      <Bell className="h-4 w-4" />
      {unread ? (
        <span className="absolute -right-2 -top-2 flex h-5 min-w-5 items-center justify-center border border-error bg-error px-1 font-mono text-[10px] font-bold leading-none text-error-on-container">
          {unread}
        </span>
      ) : null}
    </a>
  );
}