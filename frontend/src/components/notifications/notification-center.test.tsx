import { render, screen, waitFor, fireEvent, cleanup, within, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import NotificationsPage from "@/app/notifications/page";
import { NotificationCenter } from "@/components/notifications/NotificationCenter";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import type { Notification } from "@/types/notifications";

vi.mock("next/navigation", () => ({
  usePathname: () => "/notifications",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

vi.mock("@/components/auth/Protected", async () => {
  const actual = await vi.importActual<typeof import("@/components/auth/Protected")>(
    "@/components/auth/Protected",
  );
  return {
    ...actual,
    Protected: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

function notification(overrides: Partial<Notification>): Notification {
  return {
    id: "n1",
    title: "Deployment complete",
    body: "staging deployed successfully",
    notification_type: "deployment_complete",
    is_read: false,
    read_at: null,
    action_url: "/knowledge/universal",
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function makeNotifications(count: number, start = 0): Notification[] {
  return Array.from({ length: count }, (_, i) =>
    notification({
      id: `n${start + i}`,
      title: `Deployment ${start + i}`,
      body: `body ${start + i}`,
      is_read: true,
      read_at: "2026-01-01T00:00:00Z",
      action_url: null,
    }),
  );
}

const unreadCountResponse = { count: 1 };
const preferencesResponse = {
  preferences: [
    { event_type: "deployment_complete", channels: ["in_app", "email"], enabled: true },
    { event_type: "security_alert", channels: [], enabled: false },
  ],
};
const channelsResponse = [
  {
    id: "c1",
    channel_type: "email",
    name: "ops-email",
    is_active: true,
    verified_at: "2026-01-01T00:00:00Z",
    created_at: "2025-12-01T00:00:00Z",
    // never rendered — provokes leaks if the component prints raw payloads
    config: { url: "https://hooks.example/abc123", secret: "xoxb-topsecret" },
  } as unknown as import("@/types/notifications").NotificationChannel,
];
const auditResponse = {
  items: [
    {
      query_id: "q1",
      query_text: "How do I reset service tokens?",
      query_type: "search",
      results_count: 3,
      latency_ms: 12,
      user_id: "user-1234-tenant-5678",
      created_at: "2026-01-02T00:00:00Z",
    },
  ],
  total: 1,
};

function installApiMock(): Record<string, ReturnType<typeof vi.fn>> {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
    notificationsList: vi.fn().mockResolvedValue([notification({})]),
    notificationsUnreadCount: vi.fn().mockResolvedValue(unreadCountResponse),
    notificationPreferences: vi.fn().mockResolvedValue(preferencesResponse),
    notificationChannels: vi.fn().mockResolvedValue(channelsResponse),
    knowledgeHistory: vi.fn().mockResolvedValue(auditResponse),
    recentActivity: vi.fn().mockResolvedValue({ items: [] }),
    notificationMarkRead: vi.fn().mockResolvedValue(notification({})),
    notificationsMarkAllRead: vi.fn().mockResolvedValue(null),
    notificationUpdatePreferences: vi.fn().mockResolvedValue(preferencesResponse),
    notificationCreateChannel: vi.fn().mockResolvedValue(channelsResponse[0]),
    notificationUpdateChannel: vi.fn().mockResolvedValue(channelsResponse[0]),
    notificationDeleteChannel: vi.fn().mockResolvedValue(null),
    notificationTestChannel: vi.fn().mockResolvedValue({ status: "sent" }),
  };
  for (const [key, value] of Object.entries(defaults)) {
    api[key] = value;
  }
  return api;
}

const api = () => apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;

async function openTab(name: string) {
  fireEvent.click(screen.getByRole("tab", { name }));
  await waitFor(() =>
    expect(screen.getByRole("tab", { name })).toHaveAttribute("aria-selected", "true"),
  );
}

async function initialSettle() {
  await waitFor(() => expect(screen.getByText("Deployment complete")).toBeInTheDocument());
}

describe("Notification Center — read-only (C1)", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, "", "/notifications");
  });

  it("renders the page shell with a workspace title", async () => {
    render(<NotificationsPage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Notifications" })).toBeInTheDocument(),
    );
  });

  it("loads notifications, unread count, preferences and channels from the backend", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    expect(api().notificationsList).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({ limit: 50, offset: 0 }),
    );
    expect(api().notificationsUnreadCount).toHaveBeenCalledWith("test-token");
    expect(api().notificationPreferences).toHaveBeenCalledWith("test-token");
    expect(api().notificationChannels).toHaveBeenCalledWith("test-token");
    expect(screen.getByText("1 UNREAD")).toBeInTheDocument();
    expect(screen.getByText("UNREAD: 1 (AUTHORITATIVE COUNT)")).toBeInTheDocument();
  });

  it("shows read/unread states, expands a notification body and hosts Ask AI", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    expect(screen.getAllByText(/^UNREAD$/).length).toBeGreaterThanOrEqual(2);
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    await waitFor(() => expect(screen.getByText("staging deployed successfully")).toBeInTheDocument());
    const askAi = screen.getByRole("link", { name: "Ask AI" });
    expect(askAi.getAttribute("href")).toContain("/ai?ref=");
    expect(askAi.getAttribute("href")).toContain("topic=deployment_complete");
  });

  it("switches to UNREAD with an unread_only filter", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("UNREAD");
    await waitFor(() =>
      expect(api().notificationsList).toHaveBeenLastCalledWith(
        "test-token",
        expect.objectContaining({ unreadOnly: true, offset: 0 }),
      ),
    );
  });

  it("pages through notifications using backend offset pagination", async () => {
    let calls = 0;
    api().notificationsList.mockImplementation(async () => {
      calls += 1;
      if (calls === 1) return makeNotifications(50);
      return makeNotifications(2, 50);
    });
    render(<NotificationCenter />);
    await waitFor(() => expect(screen.getByText("Deployment 49")).toBeInTheDocument());
    expect(screen.getByText("SHOWING PAGE 1 — SERVER DOES NOT REPORT TOTAL")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prev" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(api().notificationsList).toHaveBeenLastCalledWith(
        "test-token",
        expect.objectContaining({ offset: 50 }),
      ),
    );
    expect(screen.getByText("SHOWING PAGE 2 — SERVER DOES NOT REPORT TOTAL")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Prev" }));
    await waitFor(() =>
      expect(api().notificationsList).toHaveBeenLastCalledWith(
        "test-token",
        expect.objectContaining({ offset: 0 }),
      ),
    );
  });

  it("shows an honest empty state when the backend returns no notifications", async () => {
    api().notificationsList.mockResolvedValueOnce([]);
    render(<NotificationCenter />);
    await waitFor(() => expect(screen.getByText("NO NOTIFICATIONS")).toBeInTheDocument());
  });

  it("shows backend errors per source without blanking the rest of the board", async () => {
    api().notificationsList.mockRejectedValue(new ApiError("forbidden", 403, "Forbidden"));
    render(<NotificationCenter />);
    await waitFor(() =>
      expect(screen.getByText(/additional authorization is required/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("tab", { name: "PREFERENCES" })).toBeInTheDocument();
  });

  it("surfaces a server error for preferences while the board still works", async () => {
    api().notificationPreferences.mockRejectedValue(new ApiError("server", 500, "boom"));
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("PREFERENCES");
    await waitFor(() => expect(screen.getByText("Preferences unavailable")).toBeInTheDocument());
    expect(screen.getByRole("tab", { name: "ALL" })).toBeInTheDocument();
  });

  it("renders the preferences matrix from the backend", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("PREFERENCES");
    expect(screen.getByText("deployment_complete")).toBeInTheDocument();
    expect(screen.getByText("security_alert")).toBeInTheDocument();
    expect(screen.getByText("DISABLED")).toBeInTheDocument();
    expect(screen.getAllByText("YES").length).toBeGreaterThan(0);
  });

  it("renders channels without exposing configuration or secrets", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    expect(screen.getByText("ops-email")).toBeInTheDocument();
    expect(screen.getByText("email")).toBeInTheDocument();
    expect(screen.queryByText(/hooks\.example|xoxb|topsecret|webhook_url|secret/i)).not.toBeInTheDocument();
  });

  it("renders activity from the knowledge audit with explicit scope labels", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("ACTIVITY");
    await waitFor(() => expect(api().knowledgeHistory).toHaveBeenCalledWith("test-token", 50));
    expect(screen.getByText("SOURCE: KNOWLEDGE AUDIT")).toBeInTheDocument();
    expect(screen.getByText("SCOPE: TENANT-SCOPED (SERVER-DERIVED)")).toBeInTheDocument();
    expect(screen.getByText("How do I reset service tokens?")).toBeInTheDocument();
    expect(screen.getByText("search")).toBeInTheDocument();
    expect(screen.getByText("3 RESULTS · 12 MS")).toBeInTheDocument();
    expect(screen.getByText("user-1234-t")).toBeInTheDocument();
  });

  it("shows an honest empty state when the audit has no records", async () => {
    api().knowledgeHistory.mockResolvedValueOnce({ items: [], total: 0 });
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("ACTIVITY");
    await waitFor(() => expect(screen.getByText("NO KNOWLEDGE ACTIVITY")).toBeInTheDocument());
  });

  it("shows ACTIVITY UNAVAILABLE when knowledge audit access is forbidden", async () => {
    api().knowledgeHistory.mockRejectedValueOnce(new ApiError("forbidden", 403, "Forbidden"));
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("ACTIVITY");
    await waitFor(() =>
      expect(
        screen.getByText("ACTIVITY UNAVAILABLE — knowledge audit access requires knowledge:read."),
      ).toBeInTheDocument(),
    );
  });

  it("never calls the unsafe /analytics/events source", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("UNREAD");
    await openTab("ACTIVITY");
    await openTab("PREFERENCES");
    await openTab("CHANNELS");
    expect(api().recentActivity).not.toHaveBeenCalled();
  });

  it("validates deep links against the target allowlist", async () => {
    api().notificationsList.mockResolvedValue([
      notification({}),
      notification({
        id: "n2",
        title: "Security alert",
        body: "did not include credentials",
        notification_type: "security_alert",
        is_read: true,
        read_at: "2026-01-01T01:00:00Z",
        action_url: "https://evil.example/steal",
        created_at: "2026-01-01T00:30:00Z",
      }),
    ]);
    render(<NotificationCenter />);
    await waitFor(() => expect(screen.getByText("Security alert")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Open target" })).toHaveAttribute(
        "href",
        "/knowledge/universal",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: /Security alert/ }));
    await waitFor(() =>
      expect(screen.getByText("RESOURCE TARGET NOT AVAILABLE")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/evil\.example/)).not.toBeInTheDocument();
    // re-opening the safe item still yields the allowlisted target
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    await waitFor(() =>
      expect(screen.getByRole("link", { name: "Open target" })).toHaveAttribute(
        "href",
        "/knowledge/universal",
      ),
    );
  });

  it("reloads on tenant switch and ignores stale responses", async () => {
    let calls = 0;
    api().notificationsList.mockImplementation(async () => {
      calls += 1;
      if (calls === 1) return new Promise<Notification[]>(() => {});
      return [
        notification({
          id: "fresh",
          title: "FRESH",
          is_read: true,
          read_at: "2026-01-01T00:00:00Z",
          action_url: null,
        }),
      ];
    });
    render(<NotificationCenter />);
    await waitFor(() => expect(api().notificationsList).toHaveBeenCalledTimes(1));
    act(() => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() => expect(screen.getByText("FRESH")).toBeInTheDocument());
    expect(screen.queryByText(/Deployment complete/)).not.toBeInTheDocument();
  });

  it("refreshes from the backend and stamps the refresh time", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    const callsBefore = api().notificationsList.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect(api().notificationsList.mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expect(screen.getByText(/REFRESHED/)).toBeInTheDocument();
  });

  it("marks sessions expired on 401", async () => {
    api().notificationsList.mockRejectedValue(new ApiError("unauthorized", 401, "Unauthorized"));
    render(<NotificationCenter />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("runs no mutation calls in the read-only build", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("UNREAD");
    await openTab("ACTIVITY");
    expect(api().notificationMarkRead).not.toHaveBeenCalled();
    expect(api().notificationsMarkAllRead).not.toHaveBeenCalled();
    expect(api().notificationUpdatePreferences).not.toHaveBeenCalled();
    expect(api().notificationCreateChannel).not.toHaveBeenCalled();
    expect(api().notificationUpdateChannel).not.toHaveBeenCalled();
    expect(api().notificationDeleteChannel).not.toHaveBeenCalled();
    expect(api().notificationTestChannel).not.toHaveBeenCalled();
  });
});

describe("Notification Center — actions (C2)", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    useToastStore.setState({ toasts: [] });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, "", "/notifications");
  });

  function expectToast(message: string) {
    expect(
      useToastStore.getState().toasts.some((t) => t.tone === "success" && t.message.includes(message)),
    ).toBe(true);
  }

  it("marks a single notification read and refetches the board", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    const callsBefore = api().notificationsList.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark read" }));
    await waitFor(() => expect(api().notificationMarkRead).toHaveBeenCalledWith("test-token", "n1"));
    await waitFor(() =>
      expect(api().notificationsList.mock.calls.length).toBeGreaterThan(callsBefore),
    );
    expectToast("Notification marked as read");
  });

  it("marks all read only after explicit confirmation", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    const dialog = await screen.findByRole("dialog");
    expect(api().notificationsMarkAllRead).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api().notificationsMarkAllRead).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    const dialog2 = await screen.findByRole("dialog");
    fireEvent.click(within(dialog2).getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(api().notificationsMarkAllRead).toHaveBeenCalledWith("test-token"));
    expectToast("Marked all notifications as read");
  });

  it("hides the mark-read action for already-read notifications", async () => {
    api().notificationsList.mockResolvedValue([
      notification({}),
      notification({
        id: "n2",
        title: "Security alert",
        notification_type: "security_alert",
        is_read: true,
        read_at: "2026-01-01T01:00:00Z",
      }),
    ]);
    render(<NotificationCenter />);
    await waitFor(() => expect(screen.getByText("Security alert")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /Security alert/ }));
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Mark read" })).not.toBeInTheDocument(),
    );
  });

  it("edits preferences and saves the full matrix as a bulk PUT", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("PREFERENCES");
    fireEvent.click(screen.getByRole("button", { name: "Edit preferences" }));
    fireEvent.click(screen.getByLabelText("Enable deployment_complete"));
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(api().notificationUpdatePreferences).toHaveBeenCalled());
    const body = api().notificationUpdatePreferences.mock.calls[0][1];
    expect(body.preferences).toHaveLength(2);
    expect(
      body.preferences.find((p: { event_type: string }) => p.event_type === "deployment_complete")
        .enabled,
    ).toBe(false);
    expect(
      body.preferences.find((p: { event_type: string }) => p.event_type === "security_alert")
        .enabled,
    ).toBe(false);
    await waitFor(() =>
      expect(api().notificationsList.mock.calls.length).toBeGreaterThan(1),
    );
  });

  it("creates a webhook channel with per-type config", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    fireEvent.click(screen.getByRole("button", { name: "Add channel" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Channel name/), {
      target: { value: "alerts-webhook" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Channel type/), {
      target: { value: "webhook" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Webhook URL/), {
      target: { value: "https://hooks.example/abc" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Secret \(optional\)/), {
      target: { value: "xoxb-1" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create channel" }));
    await waitFor(() =>
      expect(api().notificationCreateChannel).toHaveBeenCalledWith("test-token", {
        channel_type: "webhook",
        name: "alerts-webhook",
        config: { url: "https://hooks.example/abc", secret: "xoxb-1" },
      }),
    );
    expectToast("Notification channel created");
  });

  it("validates the channel form before submitting", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    fireEvent.click(screen.getByRole("button", { name: "Add channel" }));
    const dialog = await screen.findByRole("dialog");

    fireEvent.click(within(dialog).getByRole("button", { name: "Create channel" }));
    expect(await within(dialog).findByText("Channel name is required.")).toBeInTheDocument();
    expect(api().notificationCreateChannel).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/Channel name/), {
      target: { value: "ops" },
    });
    fireEvent.change(within(dialog).getByLabelText(/Channel type/), {
      target: { value: "slack" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create channel" }));
    expect(await within(dialog).findByText("A webhook URL is required.")).toBeInTheDocument();
    expect(api().notificationCreateChannel).not.toHaveBeenCalled();

    fireEvent.change(within(dialog).getByLabelText(/Webhook URL/), {
      target: { value: "http://insecure.example" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create channel" }));
    expect(
      await within(dialog).findByText("Webhook URL must start with https://."),
    ).toBeInTheDocument();
    expect(api().notificationCreateChannel).not.toHaveBeenCalled();
  });

  it("toggles a channel active state with a PATCH", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await waitFor(() =>
      expect(api().notificationUpdateChannel).toHaveBeenCalledWith("test-token", "c1", {
        is_active: false,
      }),
    );
    expectToast("Notification channel deactivated");
  });

  it("deletes a channel only after confirmation", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog = await screen.findByRole("dialog");
    expect(api().notificationDeleteChannel).not.toHaveBeenCalled();
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(api().notificationDeleteChannel).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    const dialog2 = await screen.findByRole("dialog");
    fireEvent.click(within(dialog2).getByRole("button", { name: "Delete channel" }));
    await waitFor(() =>
      expect(api().notificationDeleteChannel).toHaveBeenCalledWith("test-token", "c1"),
    );
    expectToast("Notification channel deleted");
  });

  it("reports the backend test status verbatim", async () => {
    render(<NotificationCenter />);
    await initialSettle();
    await openTab("CHANNELS");
    fireEvent.click(screen.getByRole("button", { name: "Test" }));
    await waitFor(() =>
      expect(api().notificationTestChannel).toHaveBeenCalledWith("test-token", "c1"),
    );
    await waitFor(() =>
      expect(screen.getByText(/CHANNEL TEST \(c1\): STATUS sent/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/DELIVERY NOT GUARANTEED/)).toBeInTheDocument();
  });

  it("surfaces backend rejection errors without erasing the board", async () => {
    api().notificationMarkRead.mockRejectedValueOnce(
      new ApiError("forbidden", 403, "Forbidden"),
    );
    render(<NotificationCenter />);
    await initialSettle();
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark read" }));
    await waitFor(() =>
      expect(
        screen.getByText("Backend denied this action: additional authorization is required for your role."),
      ).toBeInTheDocument(),
    );
    expect(screen.getByText("Deployment complete")).toBeInTheDocument();
  });

  it("warns and refreshes when a target changed on the server (409)", async () => {
    api().notificationMarkRead.mockRejectedValueOnce(new ApiError("server", 409, "Changed"));
    render(<NotificationCenter />);
    await initialSettle();
    const callsBefore = api().notificationsList.mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: /Deployment complete/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Mark read" }));
    await waitFor(() =>
      expect(
        useToastStore
          .getState()
          .toasts.some(
            (t) => t.tone === "warning" && t.message.includes("Changed on the server"),
          ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(api().notificationsList.mock.calls.length).toBeGreaterThan(callsBefore),
    );
  });
});