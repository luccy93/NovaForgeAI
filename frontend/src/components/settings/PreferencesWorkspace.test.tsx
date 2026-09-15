import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { PreferencesWorkspace } from "@/components/settings/PreferencesWorkspace";
import type { ApiUser, WhoAmI } from "@/types/api";

vi.mock("next/navigation", () => ({ usePathname: () => "/settings/preferences" }));

const BASE_PROPS = {
  me: null as ApiUser | null,
  whoami: null as WhoAmI | null,
  loading: false,
  error: null,
  onRetry: vi.fn(),
  organizationId: null,
  workspaceId: null,
  workspaceName: null,
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
  mfa_enabled: false,
  auth_method: "password",
  organizations: [{ organization_id: "org-abc", role: "admin" }],
  permissions: ["zero_trust:read"],
};

describe("PreferencesWorkspace", () => {
  it("shows loading skeleton when loading", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} loading />);
    expect(screen.getAllByRole("status").length).toBeGreaterThan(0);
    expect(screen.queryByText("User Experience")).toBeNull();
  });

  it("shows empty state when no data and no error", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} />);
    expect(screen.getByText("No preferences data.")).toBeInTheDocument();
  });

  it("renders user experience summary with backend values when me present", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} workspaceName="my-ws" />);
    expect(screen.getByText("User Experience")).toBeInTheDocument();
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Dark").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("my-ws").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Fixed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Permission-controlled")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("System automatic").length).toBeGreaterThanOrEqual(1);
  });

  it("shows em-dash in summary when workspace is unknown", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(1);
  });

  it("shows error banner with retry when error is set", () => {
    const onRetry = vi.fn();
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} error="Forbidden" onRetry={onRetry} />);
    expect(screen.getByText("Forbidden")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /retry/i })).toBeInTheDocument();
  });

  it("shows active badge when me.is_active is true", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows inactive badge when me.is_active is false", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={{ ...FULL_ME, is_active: false }} />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("shows profile fields from me", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("user-1234")).toBeInTheDocument();
    expect(screen.getByText("dev@corp.dev")).toBeInTheDocument();
    expect(screen.getByText("dev")).toBeInTheDocument();
    expect(screen.getAllByText("Dev End").length).toBeGreaterThanOrEqual(1);
  });

  it("shows em-dashes for profile fields when me is null", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} error="Forbidden" />);
    expect(screen.getByText("Backend-authoritative · GET /auth/me")).toBeInTheDocument();
    const dashRows = screen.getAllByText("—");
    expect(dashRows.length).toBeGreaterThanOrEqual(4);
  });

  it("shows appearance card with dark-only badge", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Dark only")).toBeInTheDocument();
    expect(screen.getByText("NovaForge currently uses a dark enterprise interface. The browser reduced-motion preference is honored automatically.")).toBeInTheDocument();
  });

  it("shows workspace card with context values", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} workspaceName="ws-1" organizationId="org-12345678" workspaceId="ws-abcdef123456" />);
    expect(screen.getAllByText("ws-1").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("org-1234")).toBeInTheDocument();
    expect(screen.getByText("ws-abcde")).toBeInTheDocument();
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(1);
  });

  it("shows dashboard fixed badge and not-supported rows", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getAllByText("Fixed").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Fixed enterprise grid")).toBeInTheDocument();
    expect(screen.getByText("Widget reordering")).toBeInTheDocument();
  });

  it("shows navigation permission filtering active badge when whoami provided", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} whoami={FULL_WHOAMI} />);
    expect(screen.getByText("Permission filtering active")).toBeInTheDocument();
  });

  it("shows unknown permission filter badge when whoami is null", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Permission filter · unknown")).toBeInTheDocument();
  });

  it("shows navigation preview labels from permission-filtered groups", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} whoami={FULL_WHOAMI} />);
    expect(screen.getByText("Preview")).toBeInTheDocument();
    expect(screen.getByText(/Command/)).toBeInTheDocument();
    expect(screen.getByText(/Knowledge & Data/)).toBeInTheDocument();
  });

  it("shows AI experience unavailable message and handoff", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getAllByText("Not available").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/AI PERSONALIZATION — Backend preference controls are not exposed/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open AI workspace" })).toHaveAttribute("href", "/ai");
  });

  it("shows accessibility system badge and motion documentation", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByText("System preference · automatic")).toBeInTheDocument();
  });

  it("shows notifications handoff card", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Notification delivery preferences are managed in the dedicated notifications workspace.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Manage notification preferences" })).toHaveAttribute("href", "/notifications");
  });

  it("shows profile settings and security handoff links", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByRole("link", { name: "Profile settings" })).toHaveAttribute("href", "/settings/profile");
    expect(screen.getByRole("link", { name: "Security" })).toHaveAttribute("href", "/settings/security");
    expect(screen.getByRole("link", { name: "Manage workspaces" })).toHaveAttribute("href", "/settings/workspaces");
    expect(screen.getByRole("link", { name: "Open dashboard" })).toHaveAttribute("href", "/dashboard");
  });

  it("does not render any save or mutation button", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.queryByRole("button", { name: /save/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /reset/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /apply/i })).toBeNull();
  });

  it("shows footer note about read-only behavior", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText(/This page is read-only/)).toBeInTheDocument();
  });

  it("renders notification heading without calling notification APIs", () => {
    render(<PreferencesWorkspace {...BASE_PROPS} me={FULL_ME} />);
    expect(screen.getByText("Separate workspace")).toBeInTheDocument();
  });
});
