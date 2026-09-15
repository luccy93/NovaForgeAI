import { render, screen, waitFor, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { NotificationBell, NOTIFICATIONS_CHANGED } from "@/components/notifications/NotificationBell";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn(),
    api: { ...actual.api },
  };
});

const api = () => apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;

describe("Notification Bell", () => {
  beforeEach(() => {
    (apiModule.getToken as ReturnType<typeof vi.fn>).mockReturnValue("test-token");
    api().notificationsUnreadCount = vi.fn().mockResolvedValue({ count: 3 });
    vi.clearAllMocks();
    (apiModule.getToken as ReturnType<typeof vi.fn>).mockReturnValue("test-token");
  });

  afterEach(() => {
    cleanup();
  });

  it("links to the notifications workspace and shows the exact backend count", async () => {
    render(<NotificationBell />);
    const link = await screen.findByRole("link", { name: "Notifications (3 unread)" });
    expect(link).toHaveAttribute("href", "/notifications");
    expect(api().notificationsUnreadCount).toHaveBeenCalledWith("test-token");
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("shows no badge when the backend reports zero", async () => {
    api().notificationsUnreadCount.mockResolvedValue({ count: 0 });
    render(<NotificationBell />);
    await screen.findByRole("link", { name: "Notifications" });
    expect(screen.queryByText(/^\d+$/)).not.toBeInTheDocument();
  });

  it("renders no badge and issues no request without a token", async () => {
    (apiModule.getToken as ReturnType<typeof vi.fn>).mockReturnValue(null);
    render(<NotificationBell />);
    await screen.findByRole("link", { name: "Notifications" });
    expect(api().notificationsUnreadCount).not.toHaveBeenCalled();
  });

  it("refreshes the count on tenant and workspace context switches", async () => {
    render(<NotificationBell />);
    await screen.findByRole("link", { name: "Notifications (3 unread)" });
    act(() => window.dispatchEvent(new Event("tenant:switched")));
    await waitFor(() => expect(api().notificationsUnreadCount).toHaveBeenCalledTimes(2));
    act(() => window.dispatchEvent(new Event("workspace:switched")));
    await waitFor(() => expect(api().notificationsUnreadCount).toHaveBeenCalledTimes(3));
  });

  it("refreshes the count when notifications change", async () => {
    render(<NotificationBell />);
    await screen.findByRole("link", { name: "Notifications (3 unread)" });
    api().notificationsUnreadCount.mockResolvedValue({ count: 9 });
    act(() => window.dispatchEvent(new Event(NOTIFICATIONS_CHANGED)));
    await screen.findByRole("link", { name: "Notifications (9 unread)" });
  });

  it("fails silently and clears the badge without retries", async () => {
    api().notificationsUnreadCount.mockRejectedValue(new ApiError("server", 500, "boom"));
    render(<NotificationBell />);
    await screen.findByRole("link", { name: "Notifications" });
    expect(api().notificationsUnreadCount).toHaveBeenCalledTimes(1);
    expect(useAuthStore.getState().status).not.toBe("expired");
  });

  it("marks the session expired on a 401 from the count endpoint", async () => {
    api().notificationsUnreadCount.mockRejectedValue(new ApiError("unauthorized", 401, "Unauthorized"));
    render(<NotificationBell />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });
});