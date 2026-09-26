import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import { apiRequest } from "@/lib/api-client";
import { handleSessionExpired } from "@/stores/auth";

const pushMock = vi.hoisted(() => ({ push: vi.fn() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock.push, replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/components/landing/Navigation", () => ({
  Navigation: () => <nav data-testid="nav-mock" />,
}));

vi.mock("@/components/landing/FooterSection", () => ({
  FooterSection: () => <footer data-testid="footer-mock" />,
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
      login: vi.fn(),
      register: vi.fn(),
      me: vi.fn(),
      mfaChallenge: vi.fn(),
      listMyOrganizations: vi.fn().mockResolvedValue([]),
      getOrganization: vi.fn(),
      listWorkspaces: vi.fn().mockResolvedValue([]),
      requestPasswordReset: vi.fn(),
      confirmPasswordReset: vi.fn(),
      verifyEmail: vi.fn(),
      whoami: vi.fn(),
      listSessions: vi.fn(),
      listApiKeys: vi.fn(),
      revokeSession: vi.fn(),
      createApiKey: vi.fn(),
      createOrganization: vi.fn(),
      listMembers: vi.fn(),
      inviteMember: vi.fn(),
      updateMemberRole: vi.fn(),
      integrationsFiltered: vi.fn(),
      integrationConnectorsAvailable: vi.fn(),
      integrationConnections: vi.fn(),
      integrationOAuthList: vi.fn(),
      integrationWebhooks: vi.fn(),
      integrationPolicies: vi.fn(),
      integrationWebhookCreate: vi.fn(),
      dataDatasets: vi.fn(),
      dataSources: vi.fn(),
      dataSchemas: vi.fn(),
      dataPipelines: vi.fn(),
      dataJobs: vi.fn(),
      dataDatasetCreate: vi.fn(),
      knowledgeListSources: vi.fn(),
      knowledgeFreshnessStats: vi.fn(),
      knowledgeUsageStats: vi.fn(),
      knowledgeSearch: vi.fn(),
      notificationsUnreadCount: vi.fn().mockResolvedValue({ count: 0 }),
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

describe("e2e C1 — auth flows", () => {
  it("login success navigates to dashboard", async () => {
    const { default: LoginPage } = await import("@/app/auth/login/page");
    api().login.mockResolvedValue({ access_token: "tok", refresh_token: "ref" });
    api().me.mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(pushMock.push).toHaveBeenCalledWith("/dashboard"));
  });

  it("login honors a safe ?next= target", async () => {
    const { default: LoginPage } = await import("@/app/auth/login/page");
    window.history.replaceState({}, "", "/auth/login?next=/ml");
    api().login.mockResolvedValue({ access_token: "tok" });
    api().me.mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(pushMock.push).toHaveBeenCalledWith("/ml"));
  });

  it("login mfa challenge navigates to the MFA page", async () => {
    const { default: LoginPage } = await import("@/app/auth/login/page");
    api().login.mockResolvedValue({ mfa_required: true, challenge_token: "ch", mfa_methods: ["totp"], expires_in: 300 });
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(pushMock.push).toHaveBeenCalledWith("/auth/mfa"));
  });

  it("register success shows confirmation", async () => {
    const { default: RegisterPage } = await import("@/app/auth/register/page");
    api().register.mockResolvedValue({ access_token: "tok" });
    api().me.mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true });
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "ab" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() => expect(screen.getByText(/account created/i)).toBeInTheDocument());
  });

  it("MFA submit navigates to dashboard on valid code", async () => {
    const { default: MfaPage } = await import("@/app/auth/mfa/page");
    useAuthStore.setState({ status: "unauthenticated", user: null, mfaChallengeToken: "ch-token" });
    api().mfaChallenge.mockResolvedValue({ access_token: "tok" });
    api().me.mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true });
    render(<MfaPage />);
    fireEvent.change(screen.getByLabelText("MFA code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /verify/i }));
    await waitFor(() => expect(pushMock.push).toHaveBeenCalledWith("/dashboard"));
  });

  it("forgot-password shows enumeration-safe confirmation", async () => {
    const { default: ForgotPasswordPage } = await import("@/app/auth/forgot-password/page");
    api().requestPasswordReset.mockResolvedValue({});
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.click(screen.getByRole("button", { name: /send reset link/i }));
    await waitFor(() => expect(screen.getByText(/if the email exists/i)).toBeInTheDocument());
  });

  it("reset-password success shows confirmation", async () => {
    const { default: ResetPasswordPage } = await import("@/app/auth/reset-password/page");
    api().confirmPasswordReset.mockResolvedValue({});
    render(<ResetPasswordPage />);
    fireEvent.change(screen.getByLabelText("Reset token"), { target: { value: "tok-123" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "newpassword1" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "newpassword1" } });
    fireEvent.click(screen.getByRole("button", { name: /update password/i }));
    await waitFor(() => expect(screen.getByText(/password updated/i)).toBeInTheDocument());
  });

  it("verify page confirms a valid token", async () => {
    const { default: VerifyPage } = await import("@/app/auth/verify/page");
    window.history.replaceState({}, "", "/auth/verify?token=abc-123");
    api().verifyEmail.mockResolvedValue({});
    render(<VerifyPage />);
    await waitFor(() => expect(screen.getByText(/email verified/i)).toBeInTheDocument());
  });
});

describe("e2e C1 — settings mutations", () => {
  it("security page revokes a session and refetches the list", async () => {
    resetStores(true);
    const { default: SecurityPage } = await import("@/app/settings/security/page");
    api().whoami.mockResolvedValue({ permissions: [], mfa_enabled: false });
    api().listSessions.mockResolvedValue([
      { id: "sess-1", is_current: false, ip_address: "1.2.3.4", user_agent: "test" },
    ]);
    api().listApiKeys.mockResolvedValue([]);
    api().revokeSession.mockResolvedValue({});
    render(<SecurityPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Revoke" })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Revoke" }));
    await waitFor(() => expect(api().revokeSession).toHaveBeenCalledWith("test-token", "sess-1"));
    expect(api().listSessions.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("security page creates an API key shown exactly once", async () => {
    resetStores(true);
    const { default: SecurityPage } = await import("@/app/settings/security/page");
    api().whoami.mockResolvedValue({ permissions: [], mfa_enabled: false });
    api().listSessions.mockResolvedValue([]);
    api().listApiKeys.mockResolvedValue([]);
    api().createApiKey.mockResolvedValue({ id: "k1", full_key: "sk-test-only-once-123" });
    render(<SecurityPage />);
    await waitFor(() => expect(screen.getByLabelText("New API key name")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("New API key name"), { target: { value: "ci-key" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(screen.getByText("sk-test-only-once-123")).toBeInTheDocument());
    expect(api().listApiKeys.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("organization page creates then switches organization", async () => {
    resetStores(true);
    const { default: OrganizationPage } = await import("@/app/settings/organization/page");
    const org = { id: "org-1", name: "Org", slug: "org" };
    api().listMyOrganizations.mockResolvedValue([org]);
    api().getOrganization.mockResolvedValue(org);
    api().createOrganization.mockResolvedValue({ id: "org-2", name: "New Org", slug: "new-org" });
    render(<OrganizationPage />);
    await waitFor(() => expect(screen.getByLabelText("Name")).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New Org" } });
    fireEvent.change(screen.getByLabelText("Slug"), { target: { value: "new-org" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => expect(api().createOrganization).toHaveBeenCalledWith("test-token", "New Org", "new-org", ""));
    expect(api().listMyOrganizations.mock.calls.length).toBeGreaterThanOrEqual(2);
    await waitFor(() => expect(useTenantStore.getState().organizationId).toBe("org-2"));
  });

  it("members page invites a member and updates a role", async () => {
    resetStores(true);
    const { default: MembersPage } = await import("@/app/settings/members/page");
    const member = { user_id: "u9", email: "member@co.io", username: "member", role: "member" };
    api().listMembers.mockResolvedValue([member]);
    api().inviteMember.mockResolvedValue({ token: "inv-1", email: "new@co.io" });
    api().updateMemberRole.mockResolvedValue({});
    render(<MembersPage />);
    await waitFor(() => expect(screen.getByText("member@co.io")).toBeInTheDocument());
    const inviteForm = screen.getByLabelText("Email");
    fireEvent.change(inviteForm, { target: { value: "new@co.io" } });
    fireEvent.click(screen.getByRole("button", { name: /send invite/i }));
    await waitFor(() => expect(api().inviteMember).toHaveBeenCalledWith("test-token", "org-1", "new@co.io", "member"));
    const roleSelect = screen.getByLabelText("Role for member@co.io") as HTMLSelectElement;
    fireEvent.change(roleSelect, { target: { value: "admin" } });
    await waitFor(() => expect(api().updateMemberRole).toHaveBeenCalledWith("test-token", "org-1", "u9", "admin"));
  });
});

describe("e2e C1 — domain mutations", () => {
  it("integrations webhook create refetches the list", async () => {
    resetStores(true);
    const { IntegrationsWorkspace } = await import("@/components/integrations/IntegrationsWorkspace");
    api().whoami.mockResolvedValue({ permissions: ["settings:admin"], user: { id: "u1", email: "a@b.io", username: "ab" } });
    api().integrationsFiltered.mockResolvedValue({ items: [], total: 0 });
    api().integrationConnectorsAvailable.mockResolvedValue({ items: [] });
    api().integrationConnections.mockResolvedValue({ items: [], total: 0 });
    api().integrationOAuthList.mockResolvedValue({ items: [], total: 0 });
    api().integrationWebhooks.mockResolvedValue({ items: [], total: 0 });
    api().integrationPolicies.mockResolvedValue({ items: [], total: 0 });
    api().integrationWebhookCreate.mockResolvedValue({ id: "wh-new" });
    render(<IntegrationsWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "Webhooks" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /^register$/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /^register$/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "deploy-events" } });
    fireEvent.change(within(dialog).getByLabelText("URL (http/https only)"), { target: { value: "https://hooks.example.com/deploy" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^register$/i }));
    await waitFor(() =>
      expect(api().integrationWebhookCreate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ name: "deploy-events", url: "https://hooks.example.com/deploy" }),
      ),
    );
    expect(api().integrationWebhooks.mock.calls.length).toBeGreaterThanOrEqual(2);
  });

  it("data dataset create refetches the list", async () => {
    resetStores(true);
    const { DataPlatformWorkspace } = await import("@/components/data/DataPlatformWorkspace");
    api().whoami.mockResolvedValue({ permissions: ["data:write"], user: { id: "u1", email: "a@b.io", username: "ab" } });
    api().dataDatasets.mockResolvedValue({ items: [{ id: "ds-1", name: "events" }], total: 1 });
    api().dataSources.mockResolvedValue({ items: [], total: 0 });
    api().dataSchemas.mockResolvedValue({ items: [], total: 0 });
    api().dataPipelines.mockResolvedValue({ items: [], total: 0 });
    api().dataJobs.mockResolvedValue({ items: [], total: 0 });
    api().dataDatasetCreate.mockResolvedValue({ id: "ds-2", name: "clicks" });
    render(<DataPlatformWorkspace />);
    fireEvent.click(screen.getByRole("tab", { name: "Datasets" }));
    await waitFor(() => expect(screen.getByRole("button", { name: /new dataset/i })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /new dataset/i }));
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "clicks" } });
    fireEvent.click(within(dialog).getByRole("button", { name: /^create$/i }));
    await waitFor(() =>
      expect(api().dataDatasetCreate).toHaveBeenCalledWith("test-token", expect.objectContaining({ name: "clicks" })),
    );
    expect(api().dataDatasets.mock.calls.length).toBeGreaterThanOrEqual(2);
  });
});

describe("e2e C1 — error and session edges", () => {
  it("api-client preserves 404 status without a dedicated mapping", async () => {
    const realFetch = global.fetch;
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      headers: new Headers(),
      json: () => Promise.resolve({ detail: "no such thing" }),
    }) as unknown as typeof fetch;
    try {
      await expect(apiRequest("/missing", { token: "t" })).rejects.toMatchObject({ status: 404 });
    } finally {
      global.fetch = realFetch;
    }
  });

  it("handleSessionExpired honors a custom redirect target", () => {
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
    try {
      act(() => {
        handleSessionExpired("/custom-landing");
      });
      expect(navigated).toBe("/custom-landing");
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("aborted knowledge search pushes no toast and shows no error", async () => {
    resetStores(true);
    const { KnowledgeWorkspace } = await import("@/components/knowledge/KnowledgeWorkspace");
    api().knowledgeListSources.mockResolvedValue({ items: [] });
    api().knowledgeFreshnessStats.mockResolvedValue(null);
    api().knowledgeUsageStats.mockResolvedValue(null);
    let resolveSearch!: (v: unknown) => void;
    api().knowledgeSearch.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveSearch = resolve;
      }),
    );
    const { unmount } = render(<KnowledgeWorkspace />);
    const input = await screen.findByLabelText("Knowledge search");
    fireEvent.change(input, { target: { value: "aborted-query" } });
    fireEvent.click(screen.getByRole("button", { name: /^search$/i }));
    unmount();
    await act(async () => {
      resolveSearch({ items: [], total: 0 });
    });
    expect(useToastStore.getState().toasts).toEqual([]);
  });
});
