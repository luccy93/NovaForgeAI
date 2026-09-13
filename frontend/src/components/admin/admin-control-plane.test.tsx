import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AdminControlPlane } from "@/components/admin/AdminControlPlane";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

const overviewResponse = {
  total_organizations: 7,
  total_users: 11,
  total_repositories: 13,
  active_subscriptions: 5,
  total_agent_runs: 17,
};

const adminOrgsResponse = [
  {
    id: "org-global-1",
    name: "Acme Global",
    slug: "acme-global",
    plan: "enterprise",
    is_active: true,
    member_count: 4,
    repository_count: 6,
    created_at: "2026-08-01T10:00:00Z",
  },
];

const adminUsersResponse = [
  {
    id: "user-global-1",
    email: "owner@example.com",
    username: "owner",
    is_active: true,
    is_superuser: true,
    created_at: "2026-07-01T10:00:00Z",
    last_login_at: "2026-09-10T10:00:00Z",
  },
];

const auditResponse = [
  {
    id: "audit-1",
    organization_id: "org-1",
    user_id: "user-1",
    action: "member.invited",
    resource_type: "member",
    resource_id: "user-2",
    details: {},
    ip_address: "203.0.113.10",
    created_at: "2026-09-11T10:00:00Z",
  },
];

const eventsResponse = [
  {
    id: "event-1",
    organization_id: "org-1",
    user_id: "user-1",
    event_type: "access",
    event_name: "access.requested",
    properties: {},
    created_at: "2026-09-12T10:00:00Z",
  },
];

const globalFlagsResponse = [
  { name: "audit_logs", default: true, overridden: false, enabled: true },
];

const meResponse = {
  id: "user-1",
  email: "ops@example.com",
  username: "ops",
  is_active: true,
};

const whoamiResponse = {
  permissions: ["organization:read"],
  user: { id: "user-1", email: "ops@example.com", username: "ops" },
  mfa_enabled: true,
};

const myOrgsResponse = [
  {
    id: "org-1",
    name: "Acme Tenant",
    slug: "acme-tenant",
    plan: "team",
    is_active: true,
    created_at: "2026-08-02T10:00:00Z",
  },
];

const sessionsResponse = [
  {
    id: "sess-1234567890",
    ip_address: "198.51.100.20",
    user_agent: "test-browser",
    created_at: "2026-09-12T09:00:00Z",
    expires_at: "2026-09-19T09:00:00Z",
    is_current: true,
  },
];

const apiKeysResponse = [
  {
    id: "key-1",
    name: "deploy-key",
    key_prefix: "nf_testprefix",
    scopes: ["read"],
    is_active: true,
    last_used_at: "2026-09-12T08:00:00Z",
    expires_at: null,
    created_at: "2026-09-01T10:00:00Z",
  },
];

const tenantFlagsResponse = [
  { id: "flag-1", name: "team_workspaces", enabled: false, config: {}, organization_id: "org-1" },
];

const postureResponse = {
  identity: { mfa: true, sessions: 2 },
  access: { privileged: 1 },
  machine: { agents: 0 },
};

const privilegedResponse = {
  items: [
    { id: "priv-1", identity: "ops@example.com", resource: "billing", status: "ACTIVE", privilege_level: "HIGH" },
  ],
};

const accessRequestsResponse = {
  items: [
    { id: "req-1", identity: "ops@example.com", resource: "billing", action: "READ", status: "PENDING" },
  ],
};

const governanceResponse = {
  snapshot_id: "snap-1",
  total_policies: 9,
  active_policies: 8,
  violations_24h: 1,
  open_exceptions: 0,
  verified_controls: 12,
  failing_controls: 1,
  computed_at: "2026-09-12T10:00:00Z",
};

const secopsResponse = {
  tenant: "org-1",
  alerts: { total: 2, by_status: { OPEN: 2 }, by_severity: { HIGH: 2 } },
  findings: { total: 1 },
  cases: { total: 0 },
  indicators: { total: 3 },
};

function installApiMock(overrides: Record<string, unknown> = {}) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    adminOverview: vi.fn().mockResolvedValue(overviewResponse),
    adminOrganizations: vi.fn().mockResolvedValue(adminOrgsResponse),
    adminUsers: vi.fn().mockResolvedValue(adminUsersResponse),
    adminAuditLog: vi.fn().mockResolvedValue(auditResponse),
    adminAnalyticsEvents: vi.fn().mockResolvedValue(eventsResponse),
    adminFeatureFlags: vi.fn().mockResolvedValue(globalFlagsResponse),
    me: vi.fn().mockResolvedValue(meResponse),
    whoami: vi.fn().mockResolvedValue(whoamiResponse),
    listMyOrganizations: vi.fn().mockResolvedValue(myOrgsResponse),
    listSessions: vi.fn().mockResolvedValue(sessionsResponse),
    listApiKeys: vi.fn().mockResolvedValue(apiKeysResponse),
    featureFlags: vi.fn().mockResolvedValue(tenantFlagsResponse),
    zeroTrustPosture: vi.fn().mockResolvedValue(postureResponse),
    zeroTrustPrivilegedAccess: vi.fn().mockResolvedValue(privilegedResponse),
    zeroTrustAccessRequests: vi.fn().mockResolvedValue(accessRequestsResponse),
    governancePosture: vi.fn().mockResolvedValue(governanceResponse),
    secOpsDashboard: vi.fn().mockResolvedValue(secopsResponse),
  };
  Object.assign(api, defaults, overrides);
}

describe("AdminControlPlane (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge with manual refresh and AI handoff", async () => {
    render(<AdminControlPlane />);
    expect(screen.getByText("Loading control plane…")).toBeTruthy();
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(await screen.findByRole("button", { name: "Refresh" })).toBeTruthy();
    const link = screen.getByRole("link", { name: "Ask AI about administration" });
    expect(link.getAttribute("href")).toBe("/ai");
  });

  it("renders global overview counts without inventing MRR", async () => {
    render(<AdminControlPlane />);
    expect(await screen.findByText("Global administration")).toBeTruthy();
    expect(await screen.findByText("MRR is not exposed by the backend and is omitted.")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("11")).toBeTruthy();
    expect(screen.getByText("MRR is not exposed by the backend and is omitted.")).toBeTruthy();
    expect(screen.getByText("ops@example.com")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Manage organization" }).getAttribute("href")).toBe("/settings/organization");
  });

  it("renders global and tenant organizations without inventing tenants", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Organizations" }));
    expect(await screen.findByText("Acme Global")).toBeTruthy();
    expect(screen.getByText("Acme Tenant")).toBeTruthy();
    expect(screen.getByText(/No independent tenant inventory endpoint exists/)).toBeTruthy();
  });

  it("renders global user metadata without secrets", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Users" }));
    expect(await screen.findByText("owner@example.com")).toBeTruthy();
    expect(screen.queryByLabelText(/password/i)).toBeNull();
    expect(screen.queryByText(/nf_full_secret_value/)).toBeNull();
  });

  it("renders audit activity from backend events only", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Audit" }));
    expect((await screen.findAllByText("member.invited")).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("access.requested")).toBeTruthy();
    expect(screen.getByText(/203\.0\.113\.10/)).toBeTruthy();
  });

  it("renders session and API-key metadata without secret values", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Access" }));
    expect(await screen.findByText(/sess-123/)).toBeTruthy();
    expect(screen.getByText("deploy-key")).toBeTruthy();
    expect(screen.getByText("nf_testprefix")).toBeTruthy();
    expect(screen.getByText(/Secret values are never shown/)).toBeTruthy();
    expect(screen.queryByText(/nf_full_secret_value/)).toBeNull();
    expect(screen.getByText("PENDING")).toBeTruthy();
  });

  it("summarizes security posture and links to authoritative workspaces", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Security" }));
    expect(await screen.findByText("Operations summary")).toBeTruthy();
    expect(await screen.findByText(/Risk values are backend-reported only/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open Security workspace" }).getAttribute("href")).toBe("/security");
    expect(screen.getByRole("link", { name: "Open Governance workspace" }).getAttribute("href")).toBe("/governance");
  });

  it("renders feature flags as read-only", async () => {
    const { getByRole } = render(<AdminControlPlane />);
    fireEvent.click(getByRole("tab", { name: "Flags" }));
    expect(await screen.findByText("audit_logs")).toBeTruthy();
    expect(screen.getByText("team_workspaces")).toBeTruthy();
    expect(screen.getByText(/Flag changes are unavailable in C1/)).toBeTruthy();
  });

  it("shows empty states when backend returns no data", async () => {
    installApiMock({
      adminOverview: vi.fn().mockResolvedValue(null),
      adminOrganizations: vi.fn().mockResolvedValue([]),
      adminUsers: vi.fn().mockResolvedValue([]),
      adminAuditLog: vi.fn().mockResolvedValue([]),
      adminAnalyticsEvents: vi.fn().mockResolvedValue([]),
      adminFeatureFlags: vi.fn().mockResolvedValue([]),
      listMyOrganizations: vi.fn().mockResolvedValue([]),
      listSessions: vi.fn().mockResolvedValue([]),
      listApiKeys: vi.fn().mockResolvedValue([]),
      featureFlags: vi.fn().mockResolvedValue([]),
      zeroTrustPosture: vi.fn().mockResolvedValue(null),
      zeroTrustPrivilegedAccess: vi.fn().mockResolvedValue({ items: [] }),
      zeroTrustAccessRequests: vi.fn().mockResolvedValue({ items: [] }),
      governancePosture: vi.fn().mockResolvedValue(null),
      secOpsDashboard: vi.fn().mockResolvedValue(null),
    });
    const { getByRole } = render(<AdminControlPlane />);
    expect(await screen.findByText("No overview")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Organizations" }));
    expect(await screen.findAllByText("No organizations")).not.toHaveLength(0);
  });

  it("shows an error when a global read fails", async () => {
    installApiMock({
      adminOverview: vi.fn().mockRejectedValue(new ApiError("server", 500, "admin plane down")),
    });
    render(<AdminControlPlane />);
    expect(await screen.findByText("admin plane down")).toBeTruthy();
  });

  it("requires backend superuser authorization for global sections", async () => {
    const forbidden = new ApiError("forbidden", 403, "Admin access required");
    installApiMock({
      adminOverview: vi.fn().mockRejectedValue(forbidden),
      adminOrganizations: vi.fn().mockRejectedValue(forbidden),
      adminUsers: vi.fn().mockRejectedValue(forbidden),
      adminAuditLog: vi.fn().mockRejectedValue(forbidden),
      adminAnalyticsEvents: vi.fn().mockRejectedValue(forbidden),
      adminFeatureFlags: vi.fn().mockRejectedValue(forbidden),
    });
    render(<AdminControlPlane />);
    expect(await screen.findAllByText("Admin access required")).not.toHaveLength(0);
  });

  it("refetches under the new scope on tenant switch without leaking state", async () => {
    render(<AdminControlPlane />);
    expect(await screen.findByText("Global administration")).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });
});
