import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { IntegrationsWorkspace } from "@/components/integrations/IntegrationsWorkspace";
import { PlatformExtensionsOverview } from "@/components/integrations/PlatformExtensionsOverview";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useToastStore } from "@/stores/toast";

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "test-token"),
  clearToken: vi.fn(),
  api: {
    whoami: vi.fn(),
    integrationsFiltered: vi.fn(),
    integrationConnectorsAvailable: vi.fn(),
    integrationConnections: vi.fn(),
    integrationOAuthList: vi.fn(),
    integrationVersions: vi.fn(),
    integrationWebhooks: vi.fn(),
    integrationPolicies: vi.fn(),
    integrationWebhookDeliveries: vi.fn(),
    integrationWebhookInboundList: vi.fn(),
    integrationConnectorSyncs: vi.fn(),
    integrationOAuthStart: vi.fn(),
  },
}));

const integrationsResponse = {
  items: [
    {
      id: "int-1",
      tenant: "t1",
      name: "github-prod",
      type: "connector",
      provider: "github",
      version: "1.0.0",
      workspace: "",
      environment: "prod",
      region: "",
      capabilities: ["execute", "sync", "health"],
      status: "ACTIVE",
      health: "UNKNOWN",
      config: {},
      owner: "",
    },
  ],
  total: 1,
};

const connectionsResponse = { items: [], total: 0 };
const oauthResponse = { items: [], total: 0 };
const webhooksResponse = { items: [], total: 0 };
const policiesResponse = { items: [], total: 0 };
const catalogResponse = { items: [] };

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []): void {
  const mock = api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    integrationsFiltered: vi.fn().mockResolvedValue(integrationsResponse),
    integrationConnectorsAvailable: vi.fn().mockResolvedValue(catalogResponse),
    integrationConnections: vi.fn().mockResolvedValue(connectionsResponse),
    integrationOAuthList: vi.fn().mockResolvedValue(oauthResponse),
    integrationVersions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    integrationWebhooks: vi.fn().mockResolvedValue(webhooksResponse),
    integrationPolicies: vi.fn().mockResolvedValue(policiesResponse),
    integrationWebhookDeliveries: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    integrationWebhookInboundList: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    integrationConnectorSyncs: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    integrationOAuthStart: vi.fn().mockResolvedValue({ id: "oa-1", authorize_url: "https://github.com/login/oauth/authorize?client_id=x" }),
  };
  Object.assign(mock, defaults, overrides);
}

const ADMIN = ["organization:read", "settings:admin"];

function forgetLocation(): { restore: () => void; read: () => string } {
  const original = Object.getOwnPropertyDescriptor(window, "location");
  const fake = { href: "" } as Location;
  Object.defineProperty(window, "location", { configurable: true, value: fake });
  return {
    read: () => fake.href,
    restore: () => {
      if (original) Object.defineProperty(window, "location", original);
    },
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function startOAuthFlow() {
  fireEvent.click(await screen.findByText("github-prod"));
  fireEvent.click(screen.getByRole("tab", { name: "OAuth" }));
  fireEvent.click(screen.getByRole("button", { name: "Start flow" }));
  fireEvent.change(screen.getByLabelText("Provider"), { target: { value: "github" } });
  fireEvent.change(screen.getByLabelText("Client ID"), { target: { value: "client-1" } });
  fireEvent.change(screen.getByLabelText("Redirect URI (https)"), { target: { value: "https://app.example.com/oauth/callback" } });
  fireEvent.change(screen.getByLabelText("Authorization endpoint (https)"), { target: { value: "https://github.com/login/oauth/authorize" } });
}

describe("IntegrationsWorkspace hardening", () => {
  beforeEach(() => {
    installApiMock();
    vi.mocked(getToken).mockReturnValue("test-token");
    vi.mocked(clearToken).mockClear();
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    cleanup();
  });

  it("redirects to login when the session expires during load", async () => {
    installApiMock({
      whoami: vi.fn().mockRejectedValue(new ApiError("unauthorized", 401, "Token expired")),
    });
    const location = forgetLocation();
    render(<IntegrationsWorkspace />);
    await waitFor(() => expect(clearToken).toHaveBeenCalled());
    await waitFor(() => expect(location.read()).toBe("/auth/login"));
    location.restore();
  });

  it("maps a 500 error to the canonical extension message instead of raw body text", async () => {
    installApiMock(
      {
        integrationOAuthStart: vi.fn().mockRejectedValue(new ApiError("server", 500, "Internal failure: client_secret leaked")),
      },
      ADMIN,
    );
    render(<IntegrationsWorkspace />);
    await startOAuthFlow();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => {
      expect(useToastStore.getState().toasts.some((t) => t.message === "Extension service temporarily unavailable")).toBe(true);
    });
    const messages = useToastStore.getState().toasts.map((t) => t.message).join(" ");
    expect(messages).not.toContain("client_secret leaked");
  });

  it("maps a 422 error to the canonical backend rejection message", async () => {
    installApiMock(
      {
        integrationOAuthStart: vi.fn().mockRejectedValue(new ApiError("validation", 422, "unprocessable entity")),
      },
      ADMIN,
    );
    render(<IntegrationsWorkspace />);
    await startOAuthFlow();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => {
      expect(useToastStore.getState().toasts.some((t) => t.message === "Backend rejected the request.")).toBe(true);
    });
  });

  it("maps a 404 error to the canonical not-found message", async () => {
    installApiMock(
      {
        integrationOAuthStart: vi.fn().mockRejectedValue(new ApiError("server", 404, "no such oauth")),
      },
      ADMIN,
    );
    render(<IntegrationsWorkspace />);
    await startOAuthFlow();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => {
      expect(useToastStore.getState().toasts.some((t) => t.message === "Not found on the backend.")).toBe(true);
    });
  });

  it("exposes the provider authorization URL as a user-initiated noopener link, never auto-navigates", async () => {
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    installApiMock({}, ADMIN);
    render(<IntegrationsWorkspace />);
    await startOAuthFlow();
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    const anchor = await screen.findByRole("link", { name: "Open provider authorization" });
    expect(anchor.getAttribute("href")).toMatch(/^https:\/\/github\.com\/login\/oauth\/authorize/);
    expect(anchor.getAttribute("target")).toBe("_blank");
    expect(anchor.getAttribute("rel")).toContain("noreferrer");
    expect(openSpy).not.toHaveBeenCalled();
    openSpy.mockRestore();
  });

  it("never renders token or signing-secret material, only reference metadata", async () => {
    installApiMock(
      {
        integrationOAuthList: vi.fn().mockResolvedValue({
          items: [
            { id: "oa-1", provider: "github", client_id: "client-1", token_ref: "tr_abc123", expires_at: null, status: "ACTIVE" },
          ],
          total: 1,
        }),
      },
      ADMIN,
    );
    render(<IntegrationsWorkspace />);
    fireEvent.click(await screen.findByText("github-prod"));
    fireEvent.click(screen.getByRole("tab", { name: "OAuth" }));
    await waitFor(() => {
      expect(screen.getByText("tr_abc123")).toBeTruthy();
    });
    expect(screen.queryByText(/access_token/i)).toBeNull();
    expect(screen.queryByText(/refresh_token/i)).toBeNull();
    expect(screen.queryByText(/client_secret/i)).toBeNull();
    expect(screen.queryByText(/signing_secret/i)).toBeNull();
  });

  it("keeps the OAuth callback code input as a one-time password field", async () => {
    installApiMock({}, ADMIN);
    render(<IntegrationsWorkspace />);
    fireEvent.click(await screen.findByText("github-prod"));
    fireEvent.click(screen.getByRole("tab", { name: "OAuth" }));
    fireEvent.click(screen.getByRole("button", { name: "Finish callback" }));
    const codeInput = screen.getByLabelText("Code (one-time)") as HTMLInputElement;
    expect(codeInput.type).toBe("password");
    expect(codeInput.getAttribute("autoComplete")).toBe("off");
  });

  it("exposes only the canonical integration tab set — no plugin or marketplace surface", async () => {
    installApiMock({}, ADMIN);
    render(<IntegrationsWorkspace />);
    await screen.findByText("github-prod");
    const tabs = ["Registry", "Connectors", "Connections", "OAuth", "Webhooks", "Policies", "Health", "Advanced"];
    for (const name of tabs) {
      expect(screen.getByRole("tab", { name })).toBeTruthy();
    }
    expect(screen.queryByRole("tab", { name: "Plugins" })).toBeNull();
    expect(screen.queryByRole("tab", { name: "Marketplace" })).toBeNull();
  });
});

describe("PlatformExtensionsOverview hardening", () => {
  beforeEach(() => {
    installApiMock();
    vi.mocked(getToken).mockReturnValue("test-token");
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    cleanup();
  });

  it("drops stale in-flight results after a tenant switch", async () => {
    const tenantA = deferred<unknown>();
    installApiMock({
      integrationsFiltered: vi.fn().mockImplementationOnce(() => tenantA.promise).mockResolvedValue({ items: [], total: 11 }),
    });
    render(<PlatformExtensionsOverview />);
    window.dispatchEvent(new Event("tenant:switched"));
    await waitFor(() => {
      expect(screen.getByText("11")).toBeTruthy();
    });
    tenantA.resolve({ items: [], total: 7 });
    await waitFor(() => {
      expect(screen.queryByText("7")).toBeNull();
      expect(screen.getByText("11")).toBeTruthy();
    });
  });

  it("maps a 500 error to the canonical extension message", async () => {
    installApiMock({
      integrationsFiltered: vi.fn().mockRejectedValue(new ApiError("server", 500, "internal boom")),
    });
    render(<PlatformExtensionsOverview />);
    expect(await screen.findByText("Extension service temporarily unavailable")).toBeTruthy();
  });

  it("maps a 422 error to the canonical backend rejection message", async () => {
    installApiMock({
      integrationsFiltered: vi.fn().mockRejectedValue(new ApiError("validation", 422, "unprocessable")),
    });
    render(<PlatformExtensionsOverview />);
    expect(await screen.findByText("Backend rejected the request.")).toBeTruthy();
  });

  it("marks unavailable surfaces as NOT EXPOSED BY API and never fabricates metrics", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Integration Registry");
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/99\.9\s*%/)).toBeNull();
    expect(screen.queryByText(/uptime\s*[:=]/i)).toBeNull();
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
  });

  it("keeps all cross-domain handoffs internal", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Platform Navigation");
    const internalOnly = ["/integrations", "/workflows", "/knowledge", "/ai", "/code", "/data", "/security", "/governance", "/admin", "/command"];
    const links = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    for (const path of internalOnly) {
      expect(links).toContain(path);
    }
    for (const href of links ?? []) {
      expect(href ?? "").not.toMatch(/^https?:/);
    }
  });
});