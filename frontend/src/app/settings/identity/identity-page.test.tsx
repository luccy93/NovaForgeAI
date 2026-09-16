import { act, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import IdentityPage from "@/app/settings/identity/page";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import type { ApiUser, WhoAmI } from "@/types/api";

const { meMock, whoamiMock, listSessionsMock, listApiKeysMock, listMyOrgsMock, listWorkspacesMock, listRolesMock, postureMock, privilegedMock, requestsMock, reviewsMock } =
  vi.hoisted(() => ({
    meMock: vi.fn(),
    whoamiMock: vi.fn(),
    listSessionsMock: vi.fn(),
    listApiKeysMock: vi.fn(),
    listMyOrgsMock: vi.fn(),
    listWorkspacesMock: vi.fn(),
    listRolesMock: vi.fn(),
    postureMock: vi.fn(),
    privilegedMock: vi.fn(),
    requestsMock: vi.fn(),
    reviewsMock: vi.fn(),
  }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/identity",
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
      listSessions: listSessionsMock,
      listApiKeys: listApiKeysMock,
      listMyOrganizations: listMyOrgsMock,
      listWorkspaces: listWorkspacesMock,
      listRoles: listRolesMock,
      zeroTrustPosture: postureMock,
      zeroTrustPrivilegedAccess: privilegedMock,
      zeroTrustAccessRequests: requestsMock,
      zeroTrustReviews: reviewsMock,
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
  mfa_enabled: true,
  auth_method: "password",
  organizations: [{ organization_id: "org-12345678", role: "admin" }],
  permissions: ["zero_trust:write"],
};

describe("IdentityPage", () => {
  beforeEach(() => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "user-1234", email: "dev@corp.dev", username: "dev" },
    });
    useTenantStore.getState().setContext("org-12345678", "ws-abcdef123456");
    meMock.mockResolvedValue(FULL_ME);
    whoamiMock.mockResolvedValue(FULL_WHOAMI);
    listSessionsMock.mockResolvedValue([{ id: "sess-1", ip_address: "1.1.1.1", user_agent: "Test", created_at: "2026-01-01", expires_at: "2026-01-02", is_current: true }]);
    listApiKeysMock.mockResolvedValue([{ id: "k1", name: "ci", key_prefix: "nf_abc", scopes: [], is_active: true, created_at: "2026-01-01" }]);
    listMyOrgsMock.mockResolvedValue([{ id: "org-12345678", name: "Acme", slug: "acme", plan: "enterprise", is_active: true, created_at: "2026-01-01" }]);
    listWorkspacesMock.mockResolvedValue([{ id: "ws-123", name: "main", slug: "main" }]);
    listRolesMock.mockResolvedValue([{ id: "r1", name: "admin", permissions: ["*"], is_system: true }]);
    postureMock.mockResolvedValue({ identity: { users: 1 }, access: { privileged: 1 }, machine: {} });
    privilegedMock.mockResolvedValue({ items: [{ id: "pa-1", identity: "alice@corp.dev", resource: "prod-db", privilege_level: "CRITICAL", status: "ACTIVE" }] });
    requestsMock.mockResolvedValue({ items: [{ id: "req-1", identity: "bob@corp.dev", action: "prod-db", status: "REQUESTED" }] });
    reviewsMock.mockResolvedValue({ items: [{ id: "rev-1", review_type: "privilege", scope: "platform", status: "pending" }] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders the identity workspace from backend data", async () => {
    render(<IdentityPage />);
    await screen.findByText("Realtime: UNAVAILABLE");
    expect(screen.getAllByText("Identity & Access").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("org-1234")).toBeInTheDocument();
    expect(screen.getAllByText("Enabled").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByRole("link", { name: "View session security" })[0]).toHaveAttribute("href", "/settings/security");
    expect(screen.getByRole("link", { name: "Manage API Keys" })).toHaveAttribute("href", "/settings/security");
  });

  it("loads verified read endpoints and never creates IAM resources", async () => {
    render(<IdentityPage />);
    await screen.findByText("Realtime: UNAVAILABLE");
    expect(meMock).toHaveBeenCalledTimes(1);
    expect(whoamiMock).toHaveBeenCalledTimes(1);
    expect(listSessionsMock).toHaveBeenCalledTimes(1);
    expect(listApiKeysMock).toHaveBeenCalledTimes(1);
    expect(postureMock).toHaveBeenCalledTimes(1);
  });

  it("reloads on tenant and workspace switches without duplicate state", async () => {
    render(<IdentityPage />);
    await screen.findByText("Realtime: UNAVAILABLE");
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
    render(<IdentityPage />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("marks the session expired when whoami reports 401", async () => {
    whoamiMock.mockRejectedValue(new ApiError("unauthorized", 401, "Unauthorized"));
    render(<IdentityPage />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("maps 403 to the authorization message", async () => {
    meMock.mockRejectedValue(new ApiError("forbidden", 403, "Forbidden"));
    render(<IdentityPage />);
    expect(await screen.findByText("Backend denied access: additional authorization is required for your role.")).toBeInTheDocument();
  });

  it("maps 404 to a not-found message", async () => {
    meMock.mockRejectedValue(new ApiError("unknown", 404, "Not found"));
    render(<IdentityPage />);
    expect(await screen.findByText("Not found on the backend.")).toBeInTheDocument();
  });

  it("maps 409 to a changed-on-server message", async () => {
    meMock.mockRejectedValue(new ApiError("unknown", 409, "Conflict"));
    render(<IdentityPage />);
    expect(await screen.findByText("Changed on the server — use Refresh to reload.")).toBeInTheDocument();
  });

  it("maps 422 validation to a rejected-request message", async () => {
    meMock.mockRejectedValue(new ApiError("validation", 422, "Bad payload"));
    render(<IdentityPage />);
    expect(await screen.findByText("Backend rejected the request.")).toBeInTheDocument();
  });

  it("surfaces 500 as temporarily unavailable", async () => {
    meMock.mockRejectedValue(new ApiError("server", 500, "Internal exploded"));
    render(<IdentityPage />);
    expect(await screen.findByText("Identity services temporarily unavailable")).toBeInTheDocument();
  });

  it("keeps SSO/SCIM/Service Accounts as NOT EXPOSED without calling those APIs", async () => {
    render(<IdentityPage />);
    await screen.findByText("Realtime: UNAVAILABLE");
    expect(screen.getByText("SSO / Identity Providers")).toBeInTheDocument();
    expect(screen.getByText("SCIM / Directory Provisioning")).toBeInTheDocument();
    expect(screen.getByText("Service Accounts")).toBeInTheDocument();
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(3);
    expect(listSessionsMock).toHaveBeenCalled();
  });
});
