import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import PreferencesPage from "@/app/settings/preferences/page";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import type { ApiUser, WhoAmI } from "@/types/api";

const { meMock, whoamiMock, notificationPreferencesMock } = vi.hoisted(() => ({
  meMock: vi.fn(),
  whoamiMock: vi.fn(),
  notificationPreferencesMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/preferences",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    api: {
      ...actual.api,
      me: meMock,
      whoami: whoamiMock,
      notificationPreferences: notificationPreferencesMock,
    },
  };
});

const FULL_ME: ApiUser = {
  id: "user-1234",
  email: "dev@corp.dev",
  username: "dev",
  full_name: "Dev End",
  is_active: true,
  created_at: "2026-01-01T00:00:00Z",
  avatar_url: null,
};

const FULL_WHOAMI: WhoAmI = {
  user_id: "user-1234",
  email: "dev@corp.dev",
  username: "dev",
  full_name: "Dev End",
  is_active: true,
  is_superuser: false,
  mfa_enabled: false,
  auth_method: "password",
  organizations: [{ organization_id: "org-12345678", role: "admin" }],
  permissions: ["zero_trust:read"],
};

describe("PreferencesPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "user-1234", email: "dev@corp.dev", username: "dev" },
    });
    useTenantStore.getState().setContext("org-12345678", "ws-abcdef123456");
    meMock.mockResolvedValue(FULL_ME);
    whoamiMock.mockResolvedValue(FULL_WHOAMI);
    notificationPreferencesMock.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the preferences workspace from backend profile and whoami data", async () => {
    render(<PreferencesPage />);
    await screen.findByText("User Experience");
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("ws-abcdef123456").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("org-1234")).toBeInTheDocument();
    expect(screen.getByText("ws-abcde")).toBeInTheDocument();
    expect(screen.getByText("Permission filtering active")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open dashboard" })).toHaveAttribute("href", "/dashboard");
    expect(screen.getByRole("link", { name: "Manage notification preferences" })).toHaveAttribute("href", "/notifications");
  });

  it("loads only the two read endpoints and never touches notification preferences", async () => {
    render(<PreferencesPage />);
    await screen.findByText("User Experience");
    expect(meMock).toHaveBeenCalledTimes(1);
    expect(whoamiMock).toHaveBeenCalledTimes(1);
    expect(notificationPreferencesMock).not.toHaveBeenCalled();
  });

  it("reloads under the same context on tenant and workspace switches without duplicate state", async () => {
    render(<PreferencesPage />);
    await screen.findByText("User Experience");
    expect(meMock).toHaveBeenCalledTimes(1);
    act(() => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() => expect(meMock).toHaveBeenCalledTimes(2));
    act(() => {
      window.dispatchEvent(new Event("workspace:switched"));
    });
    await waitFor(() => expect(meMock).toHaveBeenCalledTimes(3));
  });

  it("marks the session expired when the profile endpoint returns 401", async () => {
    meMock.mockRejectedValue(new ApiError("unauthorized", 401, "Unauthorized"));
    render(<PreferencesPage />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("marks the session expired when whoami reports 401", async () => {
    whoamiMock.mockRejectedValue(new ApiError("unauthorized", 401, "Unauthorized"));
    render(<PreferencesPage />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("maps 403 to the authorization message", async () => {
    meMock.mockRejectedValue(new ApiError("forbidden", 403, "Forbidden"));
    render(<PreferencesPage />);
    expect(
      await screen.findByText("Backend denied access: additional authorization is required for your role."),
    ).toBeInTheDocument();
  });

  it("maps 404 to a not-found message", async () => {
    meMock.mockRejectedValue(new ApiError("unknown", 404, "Not found"));
    render(<PreferencesPage />);
    expect(await screen.findByText("Not found on the backend.")).toBeInTheDocument();
  });

  it("maps 409 to a changed-on-server message", async () => {
    meMock.mockRejectedValue(new ApiError("unknown", 409, "Conflict"));
    render(<PreferencesPage />);
    expect(await screen.findByText("Changed on the server — use Refresh to reload.")).toBeInTheDocument();
  });

  it("maps 422 validation to a rejected-request message", async () => {
    meMock.mockRejectedValue(new ApiError("validation", 422, "Bad payload"));
    render(<PreferencesPage />);
    expect(await screen.findByText("Backend rejected the request.")).toBeInTheDocument();
  });

  it("surfaces a 500 server error message without fabricating state", async () => {
    meMock.mockRejectedValue(new ApiError("server", 500, "Internal exploded"));
    render(<PreferencesPage />);
    expect(await screen.findByText("Internal exploded")).toBeInTheDocument();
  });
});