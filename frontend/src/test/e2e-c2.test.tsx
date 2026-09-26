import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useTenantStore } from "@/stores/tenant";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { isSafeNotificationTarget, NAV_ITEMS } from "@/lib/navigation";
import { CommandPalette } from "@/components/navigation/CommandPalette";

const pushMock = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock.push, replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    clearAllTokens: vi.fn(),
    api: {
      ...actual.api,
      me: vi.fn(),
      whoami: vi.fn(),
      notificationsList: vi.fn(),
      notificationsUnreadCount: vi.fn().mockResolvedValue({ count: 0 }),
      notificationPreferences: vi.fn(),
      notificationChannels: vi.fn(),
      knowledgeHistory: vi.fn().mockResolvedValue({ items: [] }),
      listConversations: vi.fn(),
      listMyOrganizations: vi.fn().mockResolvedValue([]),
      listWorkspaces: vi.fn().mockResolvedValue([]),
      getOrganization: vi.fn(),
      deleteOrganization: vi.fn(),
      listMembers: vi.fn(),
      removeMember: vi.fn(),
      zeroTrustAccessRequests: vi.fn().mockResolvedValue({ items: [] }),
      zeroTrustReviews: vi.fn().mockResolvedValue({ items: [] }),
    },
  };
});

import * as apiModule from "@/lib/api";

function api() {
  return apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
}

function resetStores(authenticated = false) {
  useAuthStore.setState({
    status: authenticated ? "authenticated" : "loading",
    user: authenticated ? { id: "u1", email: "a@b.io", username: "ab" } : null,
    mfaChallengeToken: null,
  });
  useTenantStore.setState({
    organizationId: "org-1",
    workspaceId: "ws-1",
    workspaceName: "WS",
    organizations: [{ id: "org-1", name: "Org", slug: "org" } as never],
    workspaces: [{ id: "ws-1", name: "WS" } as never],
  });
  useToastStore.setState({ toasts: [] });
  localStorage.clear();
}

function stubLocation() {
  let navigated = "";
  const original = Object.getOwnPropertyDescriptor(window, "location");
  Object.defineProperty(window, "location", {
    configurable: true,
    value: {
      get href() {
        return "http://localhost:3000/";
      },
      set href(v: string) {
        navigated = v;
      },
    },
  });
  return {
    get navigated() {
      return navigated;
    },
    restore() {
      if (original) Object.defineProperty(window, "location", original);
    },
  };
}

beforeEach(() => {
  pushMock.push.mockClear();
  vi.clearAllMocks();
  resetStores(false);
  window.history.replaceState({}, "", "/");
});

afterEach(() => {
  cleanup();
  localStorage.clear();
});

describe("e2e C2 — notification target query/hash edges", () => {
  it("allows canonical paths with query and hash context", () => {
    expect(isSafeNotificationTarget("/knowledge?q=hello")).toBe(true);
    expect(isSafeNotificationTarget("/dashboard?range=7d")).toBe(true);
    expect(isSafeNotificationTarget("/docs#quick-start")).toBe(true);
    expect(isSafeNotificationTarget("/settings/identity?tab=sso")).toBe(true);
    expect(isSafeNotificationTarget("/knowledge/document/abc?version=2")).toBe(true);
  });

  it("still blocks hostile targets carrying query strings", () => {
    expect(isSafeNotificationTarget("https://evil.com?x=/knowledge")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com?q=1")).toBe(false);
    expect(isSafeNotificationTarget("javascript:alert(1)?x=/dashboard")).toBe(false);
    expect(isSafeNotificationTarget("data:text/html,hi")).toBe(false);
    expect(isSafeNotificationTarget("/unknown-route-xyz?q=1")).toBe(false);
    expect(isSafeNotificationTarget("")).toBe(false);
    expect(isSafeNotificationTarget(null)).toBe(false);
  });

  it("renders Open target for a query-bearing canonical action_url", async () => {
    resetStores(true);
    const { NotificationCenter } = await import("@/components/notifications/NotificationCenter");
    api().notificationsList.mockResolvedValue([
      {
        id: "nq",
        title: "Query finding",
        body: "has query target",
        notification_type: "info",
        is_read: true,
        read_at: "2026-01-01T00:00:00Z",
        action_url: "/knowledge?q=hello",
        created_at: "2026-01-01T00:00:00Z",
      },
    ]);
    api().notificationPreferences.mockResolvedValue({ preferences: [] });
    api().notificationChannels.mockResolvedValue([]);
    render(<NotificationCenter />);
    await waitFor(() => expect(screen.getByText("Query finding")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /query finding/i }));
    const link = await screen.findByRole("link", { name: /open target/i });
    expect(link.getAttribute("href")).toBe("/knowledge?q=hello");
  });
});

describe("e2e C2 — privileged confirmation gating", () => {
  it("organization delete requires modal confirm; cancel performs no mutation", async () => {
    resetStores(true);
    const { default: OrganizationPage } = await import("@/app/settings/organization/page");
    const org = { id: "org-1", name: "Org", slug: "org" };
    api().listMyOrganizations.mockResolvedValue([org]);
    api().getOrganization.mockResolvedValue(org);
    api().deleteOrganization.mockResolvedValue({});
    render(<OrganizationPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Delete organization" })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api().deleteOrganization).not.toHaveBeenCalled();
  });

  it("organization delete confirm performs the mutation and refetches", async () => {
    resetStores(true);
    const { default: OrganizationPage } = await import("@/app/settings/organization/page");
    const org = { id: "org-1", name: "Org", slug: "org" };
    api().listMyOrganizations.mockResolvedValue([org]);
    api().getOrganization.mockResolvedValue(org);
    api().deleteOrganization.mockResolvedValue({});
    render(<OrganizationPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: /^delete$/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^delete$/i }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /^delete$/i }));
    await waitFor(() => expect(api().deleteOrganization).toHaveBeenCalledWith("test-token", "org-1"));
    expect(api().listMyOrganizations.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("member remove cancel performs no mutation", async () => {
    resetStores(true);
    const { default: MembersPage } = await import("@/app/settings/members/page");
    api().listMembers.mockResolvedValue([
      { user_id: "u9", email: "member@co.io", username: "member", role: "member" },
    ]);
    api().removeMember.mockResolvedValue({});
    render(<MembersPage />);
    await waitFor(() => expect(screen.getByText("member@co.io")).toBeInTheDocument());
    const rowButtons = screen.getAllByRole("button", { name: /^remove$/i });
    fireEvent.click(rowButtons[0]);
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /cancel/i }));
    expect(api().removeMember).not.toHaveBeenCalled();
  });
});

describe("e2e C2 — notifications tab keyboard flow", () => {
  it("ArrowRight moves across tabs and switches panels", async () => {
    resetStores(true);
    const { NotificationCenter } = await import("@/components/notifications/NotificationCenter");
    api().notificationsList.mockResolvedValue([]);
    api().notificationPreferences.mockResolvedValue({ preferences: [] });
    api().notificationChannels.mockResolvedValue([]);
    api().knowledgeHistory.mockResolvedValue({ items: [] });
    render(<NotificationCenter />);
    const allTab = await screen.findByRole("tab", { name: "ALL" });
    expect(allTab).toHaveAttribute("aria-selected", "true");
    act(() => {
      allTab.focus();
    });
    fireEvent.keyDown(screen.getByRole("tablist"), { key: "ArrowRight" });
    await waitFor(() => expect(screen.getByRole("tab", { name: "UNREAD" })).toHaveAttribute("aria-selected", "true"));
  });
});

describe("e2e C2 — rapid context switching", () => {
  function avatar(id: string, title: string) {
    return { id, title, message_count: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
  }

  it("A→B→C switches render only the latest context data", async () => {
    resetStores(true);
    const { AiWorkspace } = await import("@/components/ai/AiWorkspace");
    let resolveFirst!: (v: unknown) => void;
    const firstFlight = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    api().listConversations.mockReturnValueOnce(firstFlight).mockResolvedValue([]);
    render(<AiWorkspace />);
    act(() => {
      useTenantStore.getState().switchOrganization("org-2");
    });
    api().listConversations.mockResolvedValue([avatar("c-latest", "Latest conversation")]);
    act(() => {
      useTenantStore.getState().switchOrganization("org-3");
    });
    await act(async () => {
      resolveFirst([avatar("c-stale", "Stale Tenant A conversation")]);
    });
    await waitFor(() => expect(screen.getByText("Latest conversation")).toBeInTheDocument());
    expect(screen.queryByText("Stale Tenant A conversation")).toBeNull();
  });
});

describe("e2e C2 — command palette canonical matrix", () => {
  it("exposes every NAV_ITEM as a safe Go-to option", async () => {
    api().whoami.mockResolvedValue({ permissions: [] });
    render(<CommandPalette open onClose={() => {}} />);
    for (const item of NAV_ITEMS) {
      // Exact <p> text match: the option button also carries the hint text.
      expect(screen.getByText(`Go to ${item.label}`)).toBeInTheDocument();
    }
  });

  it("navigates to the canonical href on option activation", async () => {
    api().whoami.mockResolvedValue({ permissions: [] });
    const loc = stubLocation();
    try {
      render(<CommandPalette open onClose={() => {}} />);
      const label = await screen.findByText("Go to Dashboard");
      const option = label.closest("button");
      expect(option).toBeTruthy();
      fireEvent.click(option!);
      expect(loc.navigated).toBe("/dashboard");
    } finally {
      loc.restore();
    }
  });
});
