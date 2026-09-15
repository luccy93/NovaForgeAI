"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative backend load and tenant/workspace switch reset */

import { useCallback, useEffect, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { isSafeNotificationTarget } from "@/lib/navigation";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type {
  Notification,
  NotificationChannel,
  NotificationChannelType,
  NotificationPreferences,
} from "@/types/notifications";
import { NOTIFICATION_CHANNEL_TYPES } from "@/types/notifications";
import type { KnowledgeAuditEntry } from "@/types/knowledge";
import { NOTIFICATIONS_CHANGED } from "./NotificationBell";

const LOGIN_PATH = "/auth/login";
const PAGE_SIZE = 50;
const ACTIVITY_LIMIT = 50;

type TabId = "all" | "unread" | "activity" | "preferences" | "channels";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "all", label: "ALL" },
  { id: "unread", label: "UNREAD" },
  { id: "activity", label: "ACTIVITY" },
  { id: "preferences", label: "PREFERENCES" },
  { id: "channels", label: "CHANNELS" },
];

interface FeedState {
  items: Notification[];
  offset: number;
  hasMore: boolean;
  error: string | null;
  loaded: boolean;
}

const EMPTY_FEED: FeedState = { items: [], offset: 0, hasMore: false, error: null, loaded: false };

const EMPTY_CHANNEL_FORM = {
  name: "",
  channelType: "email" as NotificationChannelType,
  email: "",
  webhookUrl: "",
  secret: "",
};

function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function shortId(value: string | null | undefined): string {
  if (!value) return "—";
  return value.length > 11 ? value.slice(0, 11) : value;
}

function numOrDash(value: number | null | undefined): string {
  return typeof value === "number" ? String(value) : "—";
}

export function NotificationCenter() {
  const [activeTab, setActiveTab] = useState<TabId>("all");
  const [allFeed, setAllFeed] = useState<FeedState>(EMPTY_FEED);
  const [unreadFeed, setUnreadFeed] = useState<FeedState>(EMPTY_FEED);
  const [unreadCount, setUnreadCount] = useState<number | null>(null);
  const [unreadCountError, setUnreadCountError] = useState<string | null>(null);
  const [activity, setActivity] = useState<KnowledgeAuditEntry[] | null>(null);
  const [activityError, setActivityError] = useState<string | null>(null);
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [preferencesError, setPreferencesError] = useState<string | null>(null);
  const [channels, setChannels] = useState<NotificationChannel[] | null>(null);
  const [channelsError, setChannelsError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshedAt, setRefreshedAt] = useState<Date | null>(null);

  const primaryAbortRef = useRef<AbortController | null>(null);
  const primarySeqRef = useRef(0);
  const unreadAbortRef = useRef<AbortController | null>(null);
  const unreadSeqRef = useRef(0);
  const activityAbortRef = useRef<AbortController | null>(null);
  const activitySeqRef = useRef(0);

  const pushToast = useToastStore((s) => s.push);
  const [confirming, setConfirming] = useState(false);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<
    { kind: "read-all" } | { kind: "delete-channel"; id: string; name: string } | null
  >(null);
  const [channelModal, setChannelModal] = useState<
    { mode: "create" } | { mode: "rename"; id: string; name: string } | null
  >(null);
  const [channelForm, setChannelForm] = useState(EMPTY_CHANNEL_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [channelTestResult, setChannelTestResult] = useState<{ id: string; status: string } | null>(
    null,
  );
  const [prefsDraft, setPrefsDraft] = useState<NotificationPreferences | null>(null);
  const [prefsDirty, setPrefsDirty] = useState(false);

  const sessionExpired = useCallback(() => {
    useAuthStore.getState().markExpired();
    window.location.href = LOGIN_PATH;
  }, []);

  const resetAll = useCallback(() => {
    setAllFeed(EMPTY_FEED);
    setUnreadFeed(EMPTY_FEED);
    setUnreadCount(null);
    setUnreadCountError(null);
    setActivity(null);
    setActivityError(null);
    setPreferences(null);
    setPreferencesError(null);
    setChannels(null);
    setChannelsError(null);
    setExpandedId(null);
    setRefreshedAt(null);
    setChannelTestResult(null);
    setPrefsDraft(null);
    setPrefsDirty(false);
    setMutationError(null);
    setPendingConfirm(null);
    setChannelModal(null);
    setFormError(null);
  }, []);

  const settle = useCallback(
    async <T,>(
      seq: number,
      seqRef: MutableRefObject<number>,
      controller: AbortController,
      load: () => Promise<T>,
      apply: (value: T) => void,
      fail: (message: string | null) => void,
    ) => {
      try {
        const value = await load();
        if (controller.signal.aborted || seq !== seqRef.current) return;
        apply(value);
      } catch (error) {
        if (controller.signal.aborted || seq !== seqRef.current) return;
        if (error instanceof ApiError) {
          if (error.kind === "unauthorized") {
            sessionExpired();
            return;
          }
          if (error.kind === "forbidden") {
            fail("Backend denied access: additional authorization is required for your role.");
            return;
          }
          if (error.status === 404) {
            fail("Not found on the backend.");
            return;
          }
          if (error.status === 409) {
            fail("Changed on the server — use Refresh to reload.");
            return;
          }
          if (error.kind === "validation") {
            fail("Backend rejected the request.");
            return;
          }
        }
        fail(error instanceof Error ? error.message : "Unavailable");
      }
    },
    [sessionExpired],
  );

  const loadAllFeed = useCallback(
    (offset: number) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      if (primaryAbortRef.current) primaryAbortRef.current.abort();
      const controller = new AbortController();
      primaryAbortRef.current = controller;
      const seq = ++primarySeqRef.current;
      setLoading(true);
      void settle(
        seq,
        primarySeqRef,
        controller,
        () => api.notificationsList(token, { limit: PAGE_SIZE, offset }),
        (items) => setAllFeed({ items, offset, hasMore: items.length === PAGE_SIZE, error: null, loaded: true }),
        (message) => setAllFeed({ items: [], offset, hasMore: false, error: message, loaded: true }),
      ).finally(() => {
        if (seq === primarySeqRef.current) setLoading(false);
      });
    },
    [sessionExpired, settle],
  );

  const loadUnreadFeed = useCallback(
    (offset: number) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      if (unreadAbortRef.current) unreadAbortRef.current.abort();
      const controller = new AbortController();
      unreadAbortRef.current = controller;
      const seq = ++unreadSeqRef.current;
      setUnreadFeed((feed) => ({ ...feed, error: null }));
      setLoading(true);
      void settle(
        seq,
        unreadSeqRef,
        controller,
        () => api.notificationsList(token, { limit: PAGE_SIZE, offset, unreadOnly: true }),
        (items) =>
          setUnreadFeed({ items, offset, hasMore: items.length === PAGE_SIZE, error: null, loaded: true }),
        (message) => setUnreadFeed({ items: [], offset, hasMore: false, error: message, loaded: true }),
      ).finally(() => {
        if (seq === unreadSeqRef.current) setLoading(false);
      });
    },
    [sessionExpired, settle],
  );

  const loadActivity = useCallback(() => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (activityAbortRef.current) activityAbortRef.current.abort();
    const controller = new AbortController();
    activityAbortRef.current = controller;
    const seq = ++activitySeqRef.current;
    setActivityError(null);
    api
      .knowledgeHistory(token, ACTIVITY_LIMIT)
      .then((res) => {
        if (controller.signal.aborted || seq !== activitySeqRef.current) return;
        setActivity(res.items ?? []);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted || seq !== activitySeqRef.current) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        if (error instanceof ApiError && error.kind === "forbidden") {
          setActivity(null);
          setActivityError("ACTIVITY UNAVAILABLE — knowledge audit access requires knowledge:read.");
          return;
        }
        setActivity(null);
        setActivityError(error instanceof Error ? error.message : "Activity unavailable");
      });
  }, [sessionExpired]);

  const loadPrimary = useCallback(() => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    if (primaryAbortRef.current) primaryAbortRef.current.abort();
    const controller = new AbortController();
    primaryAbortRef.current = controller;
    const seq = ++primarySeqRef.current;
    setLoading(true);
    void Promise.all([
      settle(
        seq,
        primarySeqRef,
        controller,
        () => api.notificationsList(token, { limit: PAGE_SIZE, offset: 0 }),
        (items) => setAllFeed({ items, offset: 0, hasMore: items.length === PAGE_SIZE, error: null, loaded: true }),
        (message) => setAllFeed({ items: [], offset: 0, hasMore: false, error: message, loaded: true }),
      ),
      settle(
        seq,
        primarySeqRef,
        controller,
        () => api.notificationsUnreadCount(token),
        (res) => setUnreadCount(typeof res.count === "number" ? res.count : null),
        (message) => setUnreadCountError(message),
      ),
      settle(
        seq,
        primarySeqRef,
        controller,
        () => api.notificationPreferences(token),
        setPreferences,
        (message) => setPreferencesError(message),
      ),
      settle(
        seq,
        primarySeqRef,
        controller,
        () => api.notificationChannels(token),
        setChannels,
        (message) => setChannelsError(message),
      ),
    ]).finally(() => {
      if (seq === primarySeqRef.current) setLoading(false);
    });
  }, [sessionExpired, settle]);

  const refresh = useCallback(() => {
    if (primaryAbortRef.current) primaryAbortRef.current.abort();
    if (unreadAbortRef.current) unreadAbortRef.current.abort();
    if (activityAbortRef.current) activityAbortRef.current.abort();
    primarySeqRef.current += 1;
    unreadSeqRef.current += 1;
    activitySeqRef.current += 1;
    resetAll();
    setLoading(true);
    void loadPrimary();
    if (activeTab === "unread") loadUnreadFeed(0);
    else if (activeTab === "activity") loadActivity();
    setRefreshedAt(new Date());
  }, [resetAll, loadPrimary, loadUnreadFeed, loadActivity, activeTab]);

  useEffect(() => {
    void loadPrimary();
    const handler = () => {
      if (primaryAbortRef.current) primaryAbortRef.current.abort();
      if (unreadAbortRef.current) unreadAbortRef.current.abort();
      if (activityAbortRef.current) activityAbortRef.current.abort();
      primarySeqRef.current += 1;
      unreadSeqRef.current += 1;
      activitySeqRef.current += 1;
      resetAll();
      setLoading(true);
      void loadPrimary();
    };
    window.addEventListener("tenant:switched", handler as EventListener);
    window.addEventListener("workspace:switched", handler as EventListener);
    return () => {
      window.removeEventListener("tenant:switched", handler as EventListener);
      window.removeEventListener("workspace:switched", handler as EventListener);
      if (primaryAbortRef.current) primaryAbortRef.current.abort();
      if (unreadAbortRef.current) unreadAbortRef.current.abort();
      if (activityAbortRef.current) activityAbortRef.current.abort();
    };
  }, [loadPrimary, resetAll]);

  // ─── Mutations (all confirmed → backend → authoritative refetch → toast) ──

  const refetchAfterMutation = useCallback(() => {
    if (activeTab === "unread") loadUnreadFeed(0);
    void loadPrimary();
  }, [activeTab, loadUnreadFeed, loadPrimary]);

  const runMutation = useCallback(
    async (label: string, action: () => Promise<unknown>, after?: () => void) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      const seq = primarySeqRef.current;
      setConfirming(true);
      setMutationError(null);
      try {
        await action();
        if (seq !== primarySeqRef.current) return;
        window.dispatchEvent(new CustomEvent(NOTIFICATIONS_CHANGED));
        pushToast("success", label);
        after?.();
        setPendingConfirm(null);
        setChannelModal(null);
        setFormError(null);
        setPrefsDraft(null);
        setPrefsDirty(false);
        setConfirming(false);
        refetchAfterMutation();
      } catch (error) {
        if (seq !== primarySeqRef.current) return;
        if (error instanceof ApiError && error.kind === "unauthorized") {
          sessionExpired();
          return;
        }
        if (error instanceof ApiError && (error.status === 404 || error.status === 409)) {
          setPendingConfirm(null);
          setChannelModal(null);
          setPrefsDraft(null);
          setPrefsDirty(false);
          pushToast("warning", "Changed on the server — the board was refreshed from the backend.");
          setConfirming(false);
          void loadPrimary();
          return;
        }
        if (error instanceof ApiError && error.kind === "forbidden") {
          setMutationError("Backend denied this action: additional authorization is required for your role.");
          return;
        }
        if (error instanceof ApiError && error.kind === "validation") {
          setMutationError("Backend rejected the request — check the values.");
          return;
        }
        setMutationError(error instanceof Error ? error.message : "Action failed");
      } finally {
        if (seq === primarySeqRef.current) setConfirming(false);
      }
    },
    [sessionExpired, pushToast, refetchAfterMutation, loadPrimary],
  );

  const markRead = useCallback(
    (id: string) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      void runMutation("Notification marked as read", () => api.notificationMarkRead(token, id));
    },
    [sessionExpired, runMutation],
  );

  const markAllRead = useCallback(() => {
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    void runMutation("Marked all notifications as read", () => api.notificationsMarkAllRead(token));
  }, [sessionExpired, runMutation]);

  const toggleChannelActive = useCallback(
    (channel: NotificationChannel) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      const next = !channel.is_active;
      void runMutation(
        next ? "Notification channel activated" : "Notification channel deactivated",
        () => api.notificationUpdateChannel(token, channel.id, { is_active: next }),
      );
    },
    [sessionExpired, runMutation],
  );

  const testChannel = useCallback(
    (channel: NotificationChannel) => {
      const token = getToken();
      if (!token) {
        sessionExpired();
        return;
      }
      void runMutation("Channel test submitted — delivery not guaranteed", () => {
        setChannelTestResult(null);
        return api.notificationTestChannel(token, channel.id).then((res) => {
          setChannelTestResult({ id: channel.id, status: res.status ?? "sent" });
        });
      });
    },
    [sessionExpired, runMutation],
  );

  const deleteChannel = useCallback(() => {
    if (pendingConfirm?.kind !== "delete-channel") return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    void runMutation("Notification channel deleted", () =>
      api.notificationDeleteChannel(token, pendingConfirm.id),
    );
  }, [pendingConfirm, sessionExpired, runMutation]);

  const openCreateChannel = useCallback(() => {
    setFormError(null);
    setChannelTestResult(null);
    setChannelForm(EMPTY_CHANNEL_FORM);
    setChannelModal({ mode: "create" });
  }, []);

  const openRenameChannel = useCallback(
    (channel: NotificationChannel) => {
      setFormError(null);
      setChannelForm({ ...EMPTY_CHANNEL_FORM, name: channel.name });
      setChannelModal({ mode: "rename", id: channel.id, name: channel.name });
    },
    [],
  );

  const submitChannel = useCallback(() => {
    if (!channelModal) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    const name = channelForm.name.trim();
    if (!name) {
      setFormError("Channel name is required.");
      return;
    }
    if (channelModal.mode === "rename") {
      void runMutation("Notification channel renamed", () =>
        api.notificationUpdateChannel(token, channelModal.id, { name }),
      );
      return;
    }
    const type = channelForm.channelType;
    const url = channelForm.webhookUrl.trim();
    if ((type === "slack" || type === "discord" || type === "webhook") && !url) {
      setFormError("A webhook URL is required.");
      return;
    }
    if (url && !url.startsWith("https://") && type !== "email") {
      setFormError("Webhook URL must start with https://.");
      return;
    }
    if (type === "email" && !channelForm.email.includes("@")) {
      setFormError("A destination email is required.");
      return;
    }
    let config: Record<string, unknown> = {};
    if (type === "email") {
      config = { email: channelForm.email.trim() };
    } else if (type === "slack" || type === "discord") {
      config = { webhook_url: url };
    } else if (type === "webhook") {
      config = { url, ...(channelForm.secret.trim() ? { secret: channelForm.secret.trim() } : {}) };
    }
    void runMutation("Notification channel created", () =>
      api.notificationCreateChannel(token, { channel_type: type, name, config }),
    );
  }, [channelModal, sessionExpired, runMutation, channelForm]);

  const beginEditPrefs = useCallback(() => {
    if (!preferences) return;
    setPrefsDraft({
      preferences: preferences.preferences.map((p) => ({ ...p, channels: [...p.channels] })),
    });
    setPrefsDirty(false);
    setMutationError(null);
  }, [preferences]);

  const togglePref = useCallback((eventType: string) => {
    setPrefsDraft((draft) =>
      draft
        ? {
            preferences: draft.preferences.map((p) =>
              p.event_type === eventType ? { ...p, enabled: !p.enabled } : p,
            ),
          }
        : draft,
    );
    setPrefsDirty(true);
  }, []);

  const savePrefs = useCallback(() => {
    if (!prefsDraft) return;
    const token = getToken();
    if (!token) {
      sessionExpired();
      return;
    }
    void runMutation("Notification preferences saved", () =>
      api.notificationUpdatePreferences(token, prefsDraft),
    );
  }, [prefsDraft, sessionExpired, runMutation]);

  const handleTabChange = useCallback(
    (next: TabId) => {
      setActiveTab(next);
      if (next === "unread" && !unreadFeed.loaded && !unreadFeed.error) loadUnreadFeed(0);
      if (next === "activity" && activity === null && !activityError) loadActivity();
    },
    [unreadFeed.loaded, unreadFeed.error, activity, activityError, loadUnreadFeed, loadActivity],
  );

  const tab = TABS.find((t) => t.id === activeTab) ?? TABS[0];

  return (
    <div className="space-y-6">
      <BrutalCard eyebrow="NOTIFICATION CENTER" title="Notifications" className="border-0">
        <div className="flex flex-wrap items-center gap-2">
          <BrutalBadge tone="default">SOURCE: /notifications</BrutalBadge>
          <BrutalBadge tone="default">SCOPE: USER (AUTHENTICATED)</BrutalBadge>
          <BrutalBadge tone="muted">REALTIME: UNAVAILABLE</BrutalBadge>
          {unreadCount !== null && !unreadCountError ? (
            <BrutalBadge tone="yellow">{unreadCount} UNREAD</BrutalBadge>
          ) : null}
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            {unreadCountError
              ? "UNREAD COUNT UNAVAILABLE — USE REFRESH"
              : unreadCount !== null
                ? `UNREAD: ${unreadCount} (AUTHORITATIVE COUNT)`
                : "UNREAD COUNT LOADING"}
          </p>
          <div className="flex gap-2">
            {unreadCount !== null && unreadCount > 0 && !unreadCountError ? (
              <BrutalButton
                variant="ghost"
                size="sm"
                onClick={() => setPendingConfirm({ kind: "read-all" })}
                disabled={confirming}
              >
                Mark all read
              </BrutalButton>
            ) : null}
            <BrutalButton variant="ghost" size="sm" onClick={refresh} disabled={confirming}>
              Refresh
            </BrutalButton>
          </div>
        </div>
        {refreshedAt ? (
          <p className="mt-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
            REFRESHED {formatTime(refreshedAt.toISOString())}
          </p>
        ) : null}
      </BrutalCard>

      {mutationError ? (
        <div role="alert" className="border border-error bg-error-container px-4 py-3">
          <p className="font-mono text-xs uppercase tracking-widest text-error-on-container">
            {mutationError}
          </p>
        </div>
      ) : null}

      <div>
        <div role="tablist" aria-label="Notification sections" className="mb-4 flex flex-wrap gap-2">
          {TABS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={item.id === activeTab}
              onClick={() => handleTabChange(item.id)}
              className={
                item.id === activeTab
                  ? "border border-primary-container bg-primary-container px-4 py-2 font-mono text-xs uppercase tracking-widest text-black"
                  : "border border-outline bg-transparent px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-surface-variant hover:border-on-surface hover:text-on-surface"
              }
            >
              {item.label}
            </button>
          ))}
        </div>

        <div role="tabpanel">
          {tab.id === "all" ? (
            <NotificationFeedPanel
              title="ALL NOTIFICATIONS"
              feed={allFeed}
              loading={loading}
              expandedId={expandedId}
              onToggleExpand={setExpandedId}
              onMarkRead={markRead}
              busy={confirming}
              onRetry={() => loadAllFeed(allFeed.offset)}
              onPrev={() => loadAllFeed(Math.max(0, allFeed.offset - PAGE_SIZE))}
              onNext={() => loadAllFeed(allFeed.offset + PAGE_SIZE)}
              emptyTitle="NO NOTIFICATIONS"
              emptyDescription="In-app notifications for your account will appear here."
            />
          ) : null}
          {tab.id === "unread" ? (
            <NotificationFeedPanel
              title="UNREAD NOTIFICATIONS"
              feed={unreadFeed}
              loading={loading && !unreadFeed.loaded}
              expandedId={expandedId}
              onToggleExpand={setExpandedId}
              onMarkRead={markRead}
              busy={confirming}
              onRetry={() => loadUnreadFeed(unreadFeed.offset)}
              onPrev={() => loadUnreadFeed(Math.max(0, unreadFeed.offset - PAGE_SIZE))}
              onNext={() => loadUnreadFeed(unreadFeed.offset + PAGE_SIZE)}
              emptyTitle="NO UNREAD NOTIFICATIONS"
              emptyDescription="You are all caught up."
            />
          ) : null}
          {tab.id === "activity" ? (
            <ActivityPanel activity={activity} error={activityError} loading={!activity && !activityError} />
          ) : null}
          {tab.id === "preferences" ? (
            <PreferencesPanel
              preferences={preferences}
              error={preferencesError}
              loading={!preferences && !preferencesError}
              editing={prefsDraft !== null}
              draft={prefsDraft}
              dirty={prefsDirty}
              busy={confirming}
              onBeginEdit={beginEditPrefs}
              onToggle={togglePref}
              onSave={savePrefs}
              onCancel={() => {
                setPrefsDraft(null);
                setPrefsDirty(false);
                setMutationError(null);
              }}
            />
          ) : null}
          {tab.id === "channels" ? (
            <ChannelsPanel
              channels={channels}
              error={channelsError}
              loading={!channels && !channelsError}
              busy={confirming}
              testResult={channelTestResult}
              onCreate={openCreateChannel}
              onToggle={toggleChannelActive}
              onRename={openRenameChannel}
              onDelete={(channel) => setPendingConfirm({ kind: "delete-channel", id: channel.id, name: channel.name })}
              onTest={testChannel}
            />
          ) : null}
        </div>
      </div>

      {/* Confirmations & form modals */}
      <BrutalModal
        open={pendingConfirm?.kind === "read-all"}
        title="Mark all notifications read"
        onClose={() => {
          if (!confirming) setPendingConfirm(null);
        }}
        actions={
          <>
            <BrutalButton variant="ghost" size="sm" onClick={() => setPendingConfirm(null)} disabled={confirming}>
              Cancel
            </BrutalButton>
            <BrutalButton variant="primary" size="sm" onClick={() => void markAllRead()} disabled={confirming}>
              Mark all read
            </BrutalButton>
          </>
        }
      >
        <p className="text-sm text-on-surface">
          Every in-app notification for your account will be marked read. This cannot be undone.
        </p>
      </BrutalModal>

      <BrutalModal
        open={pendingConfirm?.kind === "delete-channel"}
        title="Delete notification channel"
        onClose={() => {
          if (!confirming) setPendingConfirm(null);
        }}
        actions={
          <>
            <BrutalButton variant="ghost" size="sm" onClick={() => setPendingConfirm(null)} disabled={confirming}>
              Cancel
            </BrutalButton>
            <BrutalButton variant="primary" size="sm" onClick={() => void deleteChannel()} disabled={confirming}>
              Delete channel
            </BrutalButton>
          </>
        }
      >
        <p className="text-sm text-on-surface">
          Delete delivery channel &quot;{pendingConfirm?.kind === "delete-channel" ? pendingConfirm.name : ""}&quot;?
          Existing notifications are not affected.
        </p>
      </BrutalModal>

      <BrutalModal
        open={channelModal !== null}
        title={channelModal?.mode === "rename" ? "Rename notification channel" : "Add notification channel"}
        onClose={() => {
          if (!confirming) setChannelModal(null);
        }}
        actions={
          <>
            <BrutalButton variant="ghost" size="sm" onClick={() => setChannelModal(null)} disabled={confirming}>
              Cancel
            </BrutalButton>
            <BrutalButton variant="primary" size="sm" onClick={() => void submitChannel()} disabled={confirming}>
              {channelModal?.mode === "rename" ? "Rename channel" : "Create channel"}
            </BrutalButton>
          </>
        }
      >
        <div className="space-y-4 text-sm">
          <label className="block">
            <span className="mb-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              Channel name
            </span>
            <input
              type="text"
              value={channelForm.name}
              onChange={(e) => setChannelForm((f) => ({ ...f, name: e.target.value }))}
              className="w-full border border-outline bg-surface px-2 py-1 text-on-surface"
            />
          </label>
          {channelModal?.mode === "create" ? (
            <>
              <label className="block">
                <span className="mb-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                  Channel type
                </span>
                <select
                  value={channelForm.channelType}
                  onChange={(e) =>
                    setChannelForm((f) => ({
                      ...f,
                      channelType: e.target.value as NotificationChannelType,
                    }))
                  }
                  className="w-full border border-outline bg-surface px-2 py-1 text-on-surface"
                >
                  {NOTIFICATION_CHANNEL_TYPES.map((type) => (
                    <option key={type} value={type}>
                      {type}
                    </option>
                  ))}
                </select>
              </label>
              {channelForm.channelType === "email" ? (
                <label className="block">
                  <span className="mb-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Destination email
                  </span>
                  <input
                    type="email"
                    value={channelForm.email}
                    onChange={(e) => setChannelForm((f) => ({ ...f, email: e.target.value }))}
                    className="w-full border border-outline bg-surface px-2 py-1 text-on-surface"
                  />
                </label>
              ) : null}
              {(channelForm.channelType === "slack" ||
                channelForm.channelType === "discord" ||
                channelForm.channelType === "webhook") ? (
                <label className="block">
                  <span className="mb-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Webhook URL
                  </span>
                  <input
                    type="text"
                    value={channelForm.webhookUrl}
                    onChange={(e) => setChannelForm((f) => ({ ...f, webhookUrl: e.target.value }))}
                    className="w-full border border-outline bg-surface px-2 py-1 text-on-surface"
                  />
                </label>
              ) : null}
              {channelForm.channelType === "webhook" ? (
                <label className="block">
                  <span className="mb-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Secret (optional)
                  </span>
                  <input
                    type="text"
                    value={channelForm.secret}
                    onChange={(e) => setChannelForm((f) => ({ ...f, secret: e.target.value }))}
                    className="w-full border border-outline bg-surface px-2 py-1 text-on-surface"
                  />
                </label>
              ) : null}
            </>
          ) : null}
          {formError ? (
            <p role="alert" className="border border-error bg-error-container px-3 py-2 font-mono text-xs text-error-on-container">
              {formError}
            </p>
          ) : null}
        </div>
      </BrutalModal>
    </div>
  );
}

// ─── Notification list (ALL / UNREAD) ─────────────────────────────────────

function NotificationFeedPanel({
  title,
  feed,
  loading,
  expandedId,
  onToggleExpand,
  onMarkRead,
  busy,
  onRetry,
  onPrev,
  onNext,
  emptyTitle,
  emptyDescription,
}: {
  title: string;
  feed: FeedState;
  loading: boolean;
  expandedId: string | null;
  onToggleExpand: (id: string | null) => void;
  onMarkRead: (id: string) => void;
  busy: boolean;
  onRetry: () => void;
  onPrev: () => void;
  onNext: () => void;
  emptyTitle: string;
  emptyDescription: string;
}) {
  return (
    <BrutalCard eyebrow="IN-APP" title={title}>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          SHOWING PAGE {Math.floor(feed.offset / PAGE_SIZE) + 1} — SERVER DOES NOT REPORT TOTAL
        </p>
        <div className="flex gap-2">
          <BrutalButton variant="ghost" size="sm" onClick={onPrev} disabled={feed.offset === 0}>
            Prev
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" onClick={onNext} disabled={!feed.hasMore}>
            Next
          </BrutalButton>
        </div>
      </div>
      {feed.error ? (
        <BrutalErrorState title="Notifications unavailable" description={feed.error} onRetry={onRetry} />
      ) : null}
      {!feed.error && !feed.loaded && loading ? <BrutalSkeleton className="h-64" label="Loading notifications" /> : null}
      {!feed.error && feed.loaded && feed.items.length === 0 ? (
        <BrutalEmptyState title={emptyTitle} description={emptyDescription} />
      ) : null}
      {!feed.error && feed.loaded && feed.items.length > 0 ? (
        <ul className="space-y-3" aria-label={title.toLowerCase()}>
          {feed.items.map((item) => (
            <NotificationItem
              key={item.id}
              item={item}
              expanded={expandedId === item.id}
              busy={busy}
              onToggle={() => onToggleExpand(expandedId === item.id ? null : item.id)}
              onMarkRead={onMarkRead}
            />
          ))}
        </ul>
      ) : null}
    </BrutalCard>
  );
}

function NotificationItem({
  item,
  expanded,
  busy,
  onToggle,
  onMarkRead,
}: {
  item: Notification;
  expanded: boolean;
  busy: boolean;
  onToggle: () => void;
  onMarkRead: (id: string) => void;
}) {
  const hasTarget = Boolean(item.action_url) && isSafeNotificationTarget(item.action_url);
  return (
    <li className="border border-outline bg-surface">
      <div className="flex items-start gap-3 p-4">
        {!item.is_read ? (
          <span className="relative mt-2 h-2 w-2 shrink-0" aria-hidden="true">
            <span className="absolute inline-flex h-2 w-2 rounded-full bg-error" />
            <span className="sr-only">UNREAD</span>
          </span>
        ) : null}
        <div className="min-w-0 flex-1">
          <button
            type="button"
            onClick={onToggle}
            aria-expanded={expanded}
            className="block w-full text-left"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-bold text-on-surface">{item.title}</span>
              <BrutalBadge tone="muted">{item.notification_type}</BrutalBadge>
              {item.is_read ? <BrutalBadge tone="muted">READ</BrutalBadge> : <BrutalBadge tone="yellow">UNREAD</BrutalBadge>}
            </div>
            <span className="mt-1 block font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              {formatTime(item.created_at)}
            </span>
          </button>
        </div>
      </div>
      {expanded ? (
        <div className="border-t border-outline px-4 py-3">
          {item.body ? (
            <p className="whitespace-pre-wrap text-sm text-on-surface">{item.body}</p>
          ) : (
            <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">NO BODY</p>
          )}
          <div className="mt-3 flex flex-wrap items-center gap-3">
            {hasTarget ? (
              <a
                href={item.action_url ?? undefined}
                className="border border-outline px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-on-surface hover:border-primary-container hover:text-primary-container"
              >
                Open target
              </a>
            ) : (
              <span className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                RESOURCE TARGET NOT AVAILABLE
              </span>
            )}
            <a
              href={`/ai?ref=${encodeURIComponent(item.id)}&topic=${encodeURIComponent(item.notification_type)}`}
              className="border border-outline px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-on-surface hover:border-primary-container hover:text-primary-container"
            >
              Ask AI
            </a>
            {!item.is_read ? (
              <BrutalButton variant="ghost" size="sm" onClick={() => onMarkRead(item.id)} disabled={busy}>
                Mark read
              </BrutalButton>
            ) : null}
          </div>
        </div>
      ) : null}
    </li>
  );
}

// ─── ACTIVITY (knowledge audit) ───────────────────────────────────────────

function ActivityPanel({
  activity,
  error,
  loading,
}: {
  activity: KnowledgeAuditEntry[] | null;
  error: string | null;
  loading: boolean;
}) {
  return (
    <BrutalCard eyebrow="ACTIVITY" title="Activity — knowledge audit">
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <BrutalBadge tone="default">SOURCE: KNOWLEDGE AUDIT</BrutalBadge>
        <BrutalBadge tone="default">SCOPE: TENANT-SCOPED (SERVER-DERIVED)</BrutalBadge>
        <BrutalBadge tone="muted">GET /knowledge/audit/history</BrutalBadge>
      </div>
      <p className="mb-4 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        NOT THE COMPLETE ORGANIZATION ACTIVITY FEED — SANITIZED KNOWLEDGE QUERY AUDIT ONLY.
      </p>
      {error ? (
        <BrutalErrorState title={error} />
      ) : null}
      {!error && loading ? <BrutalSkeleton className="h-64" label="Loading activity" /> : null}
      {!error && !loading && activity?.length === 0 ? (
        <BrutalEmptyState title="NO KNOWLEDGE ACTIVITY" description="No sanitized knowledge audit records in this scope yet." />
      ) : null}
      {!error && activity && activity.length > 0 ? (
        <ul className="divide-y divide-outline border border-outline" aria-label="Knowledge audit activity">
          {activity.map((entry) => (
            <li key={entry.query_id} className="grid grid-cols-1 gap-1 p-3 md:grid-cols-[130px_110px_120px_1fr_150px]">
              <span className="font-mono text-[11px] text-on-surface-variant">{formatTime(entry.created_at)}</span>
              <span className="font-mono text-[11px] text-on-surface">{shortId(entry.user_id)}</span>
              <span className="font-mono text-[11px] uppercase text-primary-container">{entry.query_type || "query"}</span>
              <span className="break-words font-mono text-xs text-on-surface" title={entry.query_text}>
                {entry.query_text || "—"}
              </span>
              <span className="font-mono text-[11px] text-on-surface-variant">
                {numOrDash(entry.results_count)} RESULTS · {numOrDash(entry.latency_ms)} MS
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </BrutalCard>
  );
}

// ─── PREFERENCES (backend authoritative, bulk PUT) ─────────────────────────

function PreferencesPanel({
  preferences,
  error,
  loading,
  editing,
  draft,
  dirty,
  busy,
  onBeginEdit,
  onToggle,
  onSave,
  onCancel,
}: {
  preferences: NotificationPreferences | null;
  error: string | null;
  loading: boolean;
  editing: boolean;
  draft: NotificationPreferences | null;
  dirty: boolean;
  busy: boolean;
  onBeginEdit: () => void;
  onToggle: (eventType: string) => void;
  onSave: () => void;
  onCancel: () => void;
}) {
  const rows = editing && draft ? draft.preferences : preferences?.preferences ?? [];
  return (
    <BrutalCard eyebrow="DELIVERY" title="Notification preferences">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          BACKEND IS AUTHORITATIVE · SOURCE: GET/PUT /notifications/preferences · SCOPE: USER
        </p>
        <div className="flex gap-2">
          {editing ? (
            <>
              <BrutalButton variant="ghost" size="sm" onClick={onCancel} disabled={busy}>
                Cancel
              </BrutalButton>
              <BrutalButton variant="primary" size="sm" onClick={onSave} disabled={!dirty || busy}>
                Save preferences
              </BrutalButton>
            </>
          ) : (
            <BrutalButton variant="ghost" size="sm" onClick={onBeginEdit} disabled={loading || error !== null}>
              Edit preferences
            </BrutalButton>
          )}
        </div>
      </div>
      {error ? <BrutalErrorState title="Preferences unavailable" description={error} /> : null}
      {!error && loading ? <BrutalSkeleton className="h-64" label="Loading preferences" /> : null}
      {!error && !loading && rows.length === 0 ? (
        <BrutalEmptyState title="NO PREFERENCES BACKEND VALUES" description="The backend returned no preference rows." />
      ) : null}
      {!error && rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-outline">
                {editing ? (
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    Enabled
                  </th>
                ) : null}
                <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Event type</th>
                {NOTIFICATION_CHANNEL_TYPES.map((channel) => (
                  <th key={channel} className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                    {channel}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((item) => (
                <tr key={item.event_type} className="border-b border-outline/60 last:border-b-0">
                  {editing ? (
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={item.enabled}
                        onChange={() => onToggle(item.event_type)}
                        aria-label={`Enable ${item.event_type}`}
                      />
                    </td>
                  ) : null}
                  <td className="px-3 py-2">
                    <span className="font-mono text-xs text-on-surface">{item.event_type}</span>
                    {!item.enabled ? <BrutalBadge tone="muted" className="ml-2">DISABLED</BrutalBadge> : null}
                  </td>
                  {NOTIFICATION_CHANNEL_TYPES.map((channel) => {
                    const active = item.enabled && item.channels.includes(channel);
                    return (
                      <td key={channel} className="px-3 py-2">
                        <span className={active ? "font-mono text-xs text-primary-container" : "font-mono text-xs text-on-surface-variant"}>
                          {active ? "YES" : "—"}
                        </span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </BrutalCard>
  );
}

// ─── CHANNELS (config never exposed) ───────────────────────────────────────

function ChannelsPanel({
  channels,
  error,
  loading,
  busy,
  testResult,
  onCreate,
  onToggle,
  onRename,
  onDelete,
  onTest,
}: {
  channels: NotificationChannel[] | null;
  error: string | null;
  loading: boolean;
  busy: boolean;
  testResult: { id: string; status: string } | null;
  onCreate: () => void;
  onToggle: (channel: NotificationChannel) => void;
  onRename: (channel: NotificationChannel) => void;
  onDelete: (channel: NotificationChannel) => void;
  onTest: (channel: NotificationChannel) => void;
}) {
  return (
    <BrutalCard eyebrow="DELIVERY" title="Notification channels">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
          CONFIGURATION IS NEVER RETURNED BY THE API AND IS NOT RENDERED · SOURCE: GET /notifications/channels · SCOPE: USER
        </p>
        <BrutalButton variant="ghost" size="sm" onClick={onCreate} disabled={busy}>
          Add channel
        </BrutalButton>
      </div>
      {error ? <BrutalErrorState title="Channels unavailable" description={error} /> : null}
      {!error && loading ? <BrutalSkeleton className="h-64" label="Loading channels" /> : null}
      {!error && !loading && channels?.length === 0 ? (
        <BrutalEmptyState title="NO CHANNELS" description="No delivery channels configured." />
      ) : null}
      {!error && channels && channels.length > 0 ? (
        <>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <thead>
                <tr className="border-b border-outline">
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Name</th>
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Type</th>
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Active</th>
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Verified</th>
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Created</th>
                  <th className="px-3 py-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">Actions</th>
                </tr>
              </thead>
              <tbody>
                {channels.map((channel) => (
                  <tr key={channel.id} className="border-b border-outline/60 last:border-b-0">
                    <td className="px-3 py-2 font-mono text-xs text-on-surface">{channel.name}</td>
                    <td className="px-3 py-2 font-mono text-xs uppercase text-on-surface-variant">{channel.channel_type}</td>
                    <td className="px-3 py-2 font-mono text-xs">{channel.is_active ? "YES" : "NO"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-on-surface-variant">{channel.verified_at ? formatTime(channel.verified_at) : "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs text-on-surface-variant">{formatTime(channel.created_at)}</td>
                    <td className="px-3 py-2">
                      <div className="flex flex-wrap gap-1">
                        <BrutalButton variant="ghost" size="sm" onClick={() => onTest(channel)} disabled={busy}>
                          Test
                        </BrutalButton>
                        <BrutalButton variant="ghost" size="sm" onClick={() => onToggle(channel)} disabled={busy}>
                          {channel.is_active ? "Deactivate" : "Activate"}
                        </BrutalButton>
                        <BrutalButton variant="ghost" size="sm" onClick={() => onRename(channel)} disabled={busy}>
                          Rename
                        </BrutalButton>
                        <BrutalButton variant="ghost" size="sm" onClick={() => onDelete(channel)} disabled={busy}>
                          Delete
                        </BrutalButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {testResult ? (
            <p className="mt-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
              CHANNEL TEST ({shortId(testResult.id)}): STATUS {testResult.status} — DELIVERY NOT GUARANTEED
            </p>
          ) : null}
        </>
      ) : null}
    </BrutalCard>
  );
}