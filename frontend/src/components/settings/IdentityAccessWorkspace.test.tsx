import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { IdentityAccessWorkspace } from "@/components/settings/IdentityAccessWorkspace";
import type { ApiUser, WhoAmI } from "@/types/api";
import type { Organization, Workspace, Role } from "@/types/org";
import type { ZeroTrustPosture, PrivilegedAccessItem, AccessRequestItem } from "@/types/security";
import type { ZeroTrustReview } from "@/types/admin";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings/identity" }));

const BASE_PROPS = {
  me: null as ApiUser | null,
  whoami: null as WhoAmI | null,
  sessions: null as import("@/types/api").SessionOut[] | null,
  apiKeys: null as import("@/types/api").ApiKeyOut[] | null,
  organizations: null as Organization[] | null,
  workspaces: null as Workspace[] | null,
  roles: null as Role[] | null,
  posture: null as ZeroTrustPosture | null,
  privilegedAccess: null as PrivilegedAccessItem[] | null,
  accessRequests: null as AccessRequestItem[] | null,
  reviews: null as ZeroTrustReview[] | null,
  loading: false,
  error: null as string | null,
  onRetry: vi.fn(),
  organizationId: null as string | null,
  workspaceId: null as string | null,
  workspaceName: null as string | null,
};

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
  organizations: [{ organization_id: "org-abc", role: "admin" }],
  permissions: ["zero_trust:write"],
};

describe("IdentityAccessWorkspace", () => {
  it("shows loading skeleton when loading", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} loading />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(screen.queryByText("Identity & Access")).toBeNull();
  });

  it("shows empty state when no data and no error", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} />);
    expect(screen.getByText("No identity data.")).toBeInTheDocument();
  });

  it("renders identity summary with backend values when me present", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} whoami={FULL_WHOAMI} workspaceName="my-ws" />);
    expect(screen.getByText("Identity & Access")).toBeInTheDocument();
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
  });

  it("shows error banner with retry when error is set", () => {
    const onRetry = vi.fn();
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} error="Forbidden" onRetry={onRetry} />);
    expect(screen.getByText("Forbidden")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows active badge when me.is_active is true", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows inactive badge when me.is_active is false", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={{ ...FULL_ME, is_active: false }} />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("shows profile fields from me", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} whoami={FULL_WHOAMI} />);
    expect(screen.getByText("user-1234")).toBeInTheDocument();
    expect(screen.getByText("dev@corp.dev")).toBeInTheDocument();
    expect(screen.getByText("dev")).toBeInTheDocument();
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
  });

  it("shows authentication MFA enabled badge when whoami mfa_enabled true", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} whoami={FULL_WHOAMI} />);
    expect(screen.getAllByText("Enabled").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("View session security").length).toBeGreaterThanOrEqual(1);
  });

  it("shows authentication disabled when whoami mfa_enabled false", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} whoami={{ ...FULL_WHOAMI, mfa_enabled: false }} />);
    expect(screen.getAllByText("Disabled").length).toBeGreaterThanOrEqual(1);
  });

  it("shows sessions count and handoff", () => {
    render(
      <IdentityAccessWorkspace
        {...BASE_PROPS}
        me={FULL_ME}
        sessions={[{ id: "sess-1", ip_address: "1.2.3.4", user_agent: "Mozilla", created_at: "2026-01-01", expires_at: "2026-01-02", is_current: true }]}
      />,
    );
    expect(screen.getAllByText("Sessions").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("View session security").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/1\.2\.3\.4/)).toBeInTheDocument();
  });

  it("shows API keys count and never renders secret", () => {
    render(
      <IdentityAccessWorkspace
        {...BASE_PROPS}
        me={FULL_ME}
        apiKeys={[{ id: "k1", name: "ci-key", key_prefix: "nf_abc", scopes: ["read"], is_active: true, created_at: "2026-01-01" }]}
      />,
    );
    expect(screen.getAllByText("API Keys").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("ci-key")).toBeInTheDocument();
    expect(screen.getByText(/nf_abc/)).toBeInTheDocument();
    expect(screen.queryByText(/full_key/)).toBeNull();
    expect(screen.getByRole("link", { name: "Manage API Keys" })).toHaveAttribute("href", "/settings/security");
  });

  it("shows organization access counts and links", () => {
    const orgs: Organization[] = [{ id: "org-12345678", name: "Acme", slug: "acme", plan: "enterprise", is_active: true, created_at: "2026-01-01" }];
    const ws: Workspace[] = [{ id: "ws-123", name: "main", slug: "main" }];
    const roles: Role[] = [{ id: "r1", name: "admin", permissions: ["*"], is_system: true }];
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} organizations={orgs} workspaces={ws} roles={roles} organizationId="org-12345678" workspaceName="main" />);
    expect(screen.getByText("Organization Access")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage Members" })).toHaveAttribute("href", "/settings/members");
    expect(screen.getByRole("link", { name: "Manage Roles" })).toHaveAttribute("href", "/settings/roles");
    expect(screen.getByRole("link", { name: "Manage Workspaces" })).toHaveAttribute("href", "/settings/workspaces");
  });

  it("shows SSO NOT EXPOSED BY API", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("SSO / Identity Providers")).toBeInTheDocument();
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Enterprise identity-provider configuration is not currently available through the verified backend interface.")).toBeInTheDocument();
  });

  it("shows SCIM NOT EXPOSED BY API", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("SCIM / Directory Provisioning")).toBeInTheDocument();
    expect(screen.getByText("SCIM directory provisioning is not currently available through the verified backend interface.")).toBeInTheDocument();
  });

  it("shows Service Accounts NOT EXPOSED BY API", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Service Accounts")).toBeInTheDocument();
    expect(screen.getByText("Service account management is not currently available through the verified backend interface.")).toBeInTheDocument();
  });

  it("shows Zero Trust posture verbatim with field counts", () => {
    const posture: ZeroTrustPosture = { identity: { users: 1, groups: 2 }, access: { privileged: 1 }, machine: {} };
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} posture={posture} />);
    expect(screen.getByText("Access Posture")).toBeInTheDocument();
    // identity has 2 fields, access 1, machine 0
    expect(screen.getAllByText("2").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Open Security workspace")).toBeInTheDocument();
  });

  it("shows privileged access items", () => {
    const items: PrivilegedAccessItem[] = [{ id: "pa-1", identity: "alice@corp.dev", resource: "prod-db", privilege_level: "CRITICAL", status: "ACTIVE" }];
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} privilegedAccess={items} />);
    expect(screen.getAllByText("Privileged Access").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/alice@corp.dev/)).toBeInTheDocument();
    expect(screen.getAllByText(/prod-db/).length).toBeGreaterThanOrEqual(1);
  });

  it("shows access reviews and requests", () => {
    const reqs: AccessRequestItem[] = [{ id: "req-1", identity: "bob@corp.dev", action: "prod-db", status: "REQUESTED" }];
    const revs: ZeroTrustReview[] = [{ id: "rev-1", review_type: "privilege", scope: "platform", status: "pending" }];
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} accessRequests={reqs} reviews={revs} />);
    expect(screen.getByText("Access Reviews")).toBeInTheDocument();
    expect(screen.getByText(/bob@corp\.dev/)).toBeInTheDocument();
    expect(screen.getAllByText(/privilege/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("link", { name: "View access reviews" })).toHaveAttribute("href", "/admin");
  });

  it("does not render any save or mutation button", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /certify/i })).toBeNull();
  });

  it("shows footer note about read-only behavior and realtime unavailable", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText(/This page is read-only/)).toBeInTheDocument();
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Identity provider health is not exposed by the backend. No uptime or connectivity status is shown.")).toBeInTheDocument();
  });

  it("never renders secret material", () => {
    render(<IdentityAccessWorkspace {...BASE_PROPS} me={FULL_ME} />);
    const html = document.body.innerHTML;
    // copy contains the words "secret" in explanatory text, but no key material
    expect(html).not.toContain("full_key");
    expect(html).not.toContain("nf_secret");
  });
});
