import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { IdentityAccessWorkspace } from "@/components/settings/IdentityAccessWorkspace";
import { isSafeNotificationTarget, crumbsForPathname } from "@/lib/navigation";
import { hasPermission, hasAnyPermission } from "@/lib/permissions";
import type { ApiUser, WhoAmI } from "@/types/api";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings/identity" }));

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
  permissions: ["zero_trust:write", "organization:read"],
};

const BASE = {
  me: FULL_ME,
  whoami: FULL_WHOAMI,
  sessions: [{ id: "sess-1", ip_address: "1.1.1.1", user_agent: "Test", created_at: "2026-01-01", expires_at: "2026-01-02", is_current: true }],
  apiKeys: [{ id: "k1", name: "ci", key_prefix: "nf_abc", scopes: [], is_active: true, created_at: "2026-01-01" }],
  organizations: [{ id: "org-12345678", name: "Acme", slug: "acme", plan: "enterprise", is_active: true, created_at: "2026-01-01" }],
  workspaces: [{ id: "ws-123", name: "main", slug: "main" }],
  roles: [{ id: "r1", name: "admin", permissions: ["*"], is_system: true }],
  posture: { identity: { users: 1, groups: 2 }, access: { privileged: 1 }, machine: {} },
  privilegedAccess: [{ id: "pa-1", identity: "alice@corp.dev", resource: "prod-db", privilege_level: "CRITICAL", status: "ACTIVE" }],
  accessRequests: [{ id: "req-1", identity: "bob@corp.dev", action: "prod-db", status: "REQUESTED" }],
  reviews: [{ id: "rev-1", review_type: "privilege", scope: "platform", status: "pending" }],
  loading: false,
  error: null as string | null,
  onRetry: vi.fn(),
  organizationId: "org-12345678",
  workspaceId: "ws-abcdef123456",
  workspaceName: "main",
};

describe("Identity Access Hardening", () => {
  it("allows identity as safe notification target and blocks external URLs", () => {
    expect(isSafeNotificationTarget("/settings/identity")).toBe(true);
    expect(isSafeNotificationTarget("/settings/security")).toBe(true);
    expect(isSafeNotificationTarget("/settings/members")).toBe(true);
    expect(isSafeNotificationTarget("/admin")).toBe(true);
    expect(isSafeNotificationTarget("/security")).toBe(true);
    expect(isSafeNotificationTarget("https://evil.com/phish")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com")).toBe(false);
    expect(isSafeNotificationTarget("http://evil")).toBe(false);
    expect(isSafeNotificationTarget("/unknown-route-xyz")).toBe(false);
    expect(isSafeNotificationTarget(null)).toBe(false);
    expect(isSafeNotificationTarget("")).toBe(false);
  });

  it("derives breadcrumbs for identity via navigation model", () => {
    expect(crumbsForPathname("/settings/identity")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Identity & Access" }]);
    expect(crumbsForPathname("/settings/preferences")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Preferences" }]);
  });

  it("enforces server-authoritative permission checks (frontend UX only)", () => {
    expect(hasPermission(["zero_trust:write"], "zero_trust:write")).toBe(true);
    expect(hasPermission([], "zero_trust:write")).toBe(false);
    expect(hasPermission(["organization:read"], "zero_trust:write")).toBe(false);
    expect(hasAnyPermission(["zero_trust:write", "organization:read"], ["zero_trust:write"])).toBe(true);
    expect(hasAnyPermission([], ["zero_trust:write"])).toBe(false);
  });

  it("shows SSO/SCIM/Service Accounts as NOT EXPOSED with no controls", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const ssoHeading = screen.getByText("SSO / Identity Providers").closest("section")!;
    const scimHeading = screen.getByText("SCIM / Directory Provisioning").closest("section")!;
    const saHeading = screen.getByText("Service Accounts").closest("section")!;
    for (const section of [ssoHeading, scimHeading, saHeading]) {
      expect(section.textContent).toContain("NOT EXPOSED BY API");
      expect(section.querySelectorAll("button").length).toBe(0);
      expect(section.querySelectorAll("a").length).toBe(0);
    }
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(3);
  });

  it("never renders fake security scores or percentages", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("99.99%");
    expect(html).not.toContain("100%");
    // posture card explains that no score is calculated — ensure that explanation is present and no invented % remains
    expect(screen.getByText("Backend verbatim")).toBeInTheDocument();
    expect(screen.getByText("No security score is calculated here. Values are backend-reported only.")).toBeInTheDocument();
  });

  it("never shows fake provider health or uptime", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const html = document.body.innerHTML;
    expect(html).not.toContain("Healthy");
    expect(html).not.toContain("Connected");
    expect(html).not.toContain("99.9");
    expect(screen.getByText("Identity provider health is not exposed by the backend. No uptime or connectivity status is shown.")).toBeInTheDocument();
  });

  it("shows realtime as unavailable and no polling", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Tenant-scoped · server-authoritative")).toBeInTheDocument();
  });

  it("protects secrets: no tokens, password hashes, client secrets, or full_key", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("bearer");
    expect(html).not.toContain("authorization:");
    expect(html).not.toContain("client_secret");
    expect(html).not.toContain("full_key");
    expect(html).not.toContain("hashed_password");
    expect(html).not.toContain("mfa_secret");
    expect(screen.getByText("Only key metadata is shown. Secret values are never shown, stored, logged, or linked.")).toBeInTheDocument();
  });

  it("renders only known deep links (no external URLs)", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const links = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    const allowed = [
      "/settings/profile",
      "/settings/organization",
      "/settings/security",
      "/settings/members",
      "/settings/roles",
      "/settings/workspaces",
      "/security",
      "/admin",
    ];
    for (const href of links) {
      expect(href.startsWith("/")).toBe(true);
      expect(href.includes("://")).toBe(false);
      expect(href.startsWith("//")).toBe(false);
      // all hrefs should be in allowed list or start with /settings/
      const isAllowed = allowed.includes(href) || href.startsWith("/settings/");
      expect(isAllowed).toBe(true);
    }
  });

  it("does not duplicate canonical IAM controls (sessions, keys, members, roles)", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    // sessions card should have handoff, not revoke button
    expect(screen.queryByRole("button", { name: /revoke/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /rotate/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /delete.*key/i })).toBeNull();
    // privileged/requests should have no approve/certify buttons in read-only C1
    expect(screen.queryByRole("button", { name: /approve/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /certify/i })).toBeNull();
    // handoffs must exist instead
    expect(screen.getAllByRole("link", { name: "View session security" }).length).toBeGreaterThanOrEqual(1);
    expect(screen.getByRole("link", { name: "Manage API Keys" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage Members" })).toBeInTheDocument();
  });

  it("shows tenant isolation: workspace reflects current tenant, not previous", () => {
    const { rerender } = render(<IdentityAccessWorkspace {...BASE} organizationId="org-aaaaaaaa" workspaceId="ws-aaaaaaaa" workspaceName="ws-a" />);
    expect(screen.getByText("org-aaaa")).toBeInTheDocument();
    rerender(<IdentityAccessWorkspace {...BASE} organizationId="org-bbbbbbbb" workspaceId="ws-bbbbbbbb" workspaceName="ws-b" />);
    expect(screen.getByText("org-bbbb")).toBeInTheDocument();
    expect(screen.queryByText("org-aaaa")).toBeNull();
    expect(screen.getAllByText("ws-b").length).toBeGreaterThanOrEqual(1);
  });

  it("shows loading skeletons and empty state correctly", () => {
    const { rerender } = render(<IdentityAccessWorkspace {...BASE} loading />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    rerender(<IdentityAccessWorkspace {...BASE} me={null} whoami={null} sessions={null} apiKeys={null} organizations={null} workspaces={null} roles={null} posture={null} privilegedAccess={null} accessRequests={null} reviews={null} loading={false} error={null} />);
    expect(screen.getByText("No identity data.")).toBeInTheDocument();
  });

  it("shows error state with retry and preserves read-only handoffs", () => {
    const onRetry = vi.fn();
    render(<IdentityAccessWorkspace {...BASE} error="Backend denied access: additional authorization is required for your role." onRetry={onRetry} />);
    expect(screen.getByText("Backend denied access: additional authorization is required for your role.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "View session security" }).length).toBeGreaterThanOrEqual(1);
  });

  it("renders posture verbatim without inventing compliance certification", () => {
    const posture = { identity: { users: 5, groups: 3 }, access: { privileged: 2 }, machine: { agents: 1 } };
    render(<IdentityAccessWorkspace {...BASE} posture={posture} />);
    // identity has 2 fields, access 1, machine 1
    expect(screen.getByText("2")).toBeInTheDocument(); // at least one 2
    // should not contain invented compliance language
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("compliant");
    expect(html).not.toContain("certified");
  });

  it("has accessible headings and keyboard-navigable links", () => {
    render(<IdentityAccessWorkspace {...BASE} />);
    const headings = screen.getAllByRole("heading");
    expect(headings.length).toBeGreaterThan(5);
    const links = screen.getAllByRole("link");
    for (const link of links) {
      expect(link).toHaveAttribute("href");
      expect(link.getAttribute("href")!.startsWith("/")).toBe(true);
    }
  });

  it("uses responsive grid layout (md:grid-cols-2)", () => {
    const { container } = render(<IdentityAccessWorkspace {...BASE} />);
    const grids = container.querySelectorAll(".grid");
    expect(grids.length).toBeGreaterThan(0);
    // SectionGrid uses md:grid-cols-2
    const sectionGrid = container.querySelector(".md\\:grid-cols-2");
    expect(sectionGrid).not.toBeNull();
  });
});
