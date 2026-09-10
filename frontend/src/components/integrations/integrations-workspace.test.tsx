import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { IntegrationsWorkspace } from "@/components/integrations/IntegrationsWorkspace";
import * as apiModule from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

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

const catalogResponse = {
  items: [{ key: "github", provider: "github", capabilities: ["execute", "sync", "health"], auth_kind: "bearer" }],
};

const connectionsResponse = {
  items: [
    {
      id: "conn-1",
      tenant: "t1",
      integration_id: "int-1",
      workspace: "",
      environment: "prod",
      endpoint_ref: "https://api.github.com",
      credential_id: null,
      scopes: [],
      status: "ACTIVE",
      health: "UNKNOWN",
      last_success_at: null,
      last_failure_at: null,
      consecutive_failures: 0,
    },
  ],
  total: 1,
};

const oauthResponse = { items: [], total: 0 };

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []): void {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    integrationsFiltered: vi.fn().mockResolvedValue(integrationsResponse),
    integrationConnectorsAvailable: vi.fn().mockResolvedValue(catalogResponse),
    integrationConnections: vi.fn().mockResolvedValue(connectionsResponse),
    integrationOAuthList: vi.fn().mockResolvedValue(oauthResponse),
    integrationVersions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  };
  Object.assign(api, defaults, overrides);
}

describe("IntegrationsWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and read-only notice without permissions", async () => {
    render(<IntegrationsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    expect(screen.getByText("Read-only view · no integration permissions")).toBeTruthy();
    expect(screen.getByText("github-prod")).toBeTruthy();
  });

  it("hides admin actions from non-admins", async () => {
    render(<IntegrationsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("github-prod")).toBeTruthy();
    });
    expect(screen.queryByText("Register")).toBeNull();
  });

  it("shows admin actions with settings:admin", async () => {
    installApiMock({}, ["organization:read", "settings:admin"]);
    render(<IntegrationsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Admin actions enabled")).toBeTruthy();
    });
    expect(screen.getByText("Register")).toBeTruthy();
  });

  it("never renders credential material, only metadata references", async () => {
    installApiMock({}, ["organization:read", "settings:admin"]);
    render(<IntegrationsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("github-prod")).toBeTruthy();
    });
    // No secret/token material anywhere in the workspace chrome
    expect(screen.queryByText(/access_token/i)).toBeNull();
    expect(screen.queryByText(/client_secret/i)).toBeNull();
  });
});
