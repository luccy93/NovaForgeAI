import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { handleSessionExpired } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { safeExternalUrl } from "@/lib/crossDomain";
import { safeMarkdownUrl, MessageBubble } from "@/components/ai/MessageBubble";
import { safeNext } from "@/lib/navigation";
import { ApiError } from "@/lib/api-client";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/auth/register",
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
    api: {
      ...actual.api,
      register: vi.fn(),
      me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
    },
  };
});

function stubLocation() {
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
  return {
    get navigated() {
      return navigated;
    },
    restore() {
      if (original) Object.defineProperty(window, "location", original);
    },
  };
}

describe("security C1 — A: unified session expiry", () => {
  beforeEach(() => {
    localStorage.clear();
    useTenantStore.setState({
      organizationId: "org-1",
      workspaceId: "ws-1",
      workspaceName: "WS",
      organizations: [{ id: "org-1", name: "Org", slug: "org" } as never],
      workspaces: [{ id: "ws-1", name: "WS" } as never],
    });
  });
  afterEach(() => {
    cleanup();
    localStorage.clear();
    useTenantStore.getState().clear();
  });

  it("handleSessionExpired clears tokens, tenant, caches and redirects", () => {
    localStorage.setItem("nf_token", "tok");
    localStorage.setItem("nf_refresh", "ref");
    localStorage.setItem("nf_org", "org-1");
    localStorage.setItem("nf_ws", "ws-1");
    localStorage.setItem("nf_cache_dashboard", "stale");
    const loc = stubLocation();
    try {
      handleSessionExpired();
      expect(localStorage.getItem("nf_token")).toBeNull();
      expect(localStorage.getItem("nf_refresh")).toBeNull();
      expect(localStorage.getItem("nf_org")).toBeNull();
      expect(localStorage.getItem("nf_ws")).toBeNull();
      expect(localStorage.getItem("nf_cache_dashboard")).toBeNull();
      expect(useTenantStore.getState().organizationId).toBeNull();
      expect(useTenantStore.getState().workspaceId).toBeNull();
      expect(loc.navigated).toBe("/auth/login");
    } finally {
      loc.restore();
    }
  });

  it("no clearToken-only sessionExpired bodies remain in workspaces", async () => {
    const { readFileSync } = await import("node:fs");
    const base = "C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/";
    const files = [
      "components/agents/AgentWorkspace.tsx",
      "components/ai/AiWorkspace.tsx",
      "components/code/CodeWorkspace.tsx",
      "components/code/IntelligencePanel.tsx",
      "components/code/dev-utils.ts",
      "components/data/DataPlatformWorkspace.tsx",
      "components/finops/FinopsWorkspace.tsx",
      "components/governance/GovernanceWorkspace.tsx",
      "components/integrations/IntegrationsWorkspace.tsx",
      "components/knowledge/KnowledgeWorkspace.tsx",
      "components/knowledge/KnowledgeGraph.tsx",
      "components/ml/MLPlatformWorkspace.tsx",
      "components/observability/ObservabilityWorkspace.tsx",
      "components/observability/OperationsIntelligence.tsx",
      "components/security/SecurityWorkspace.tsx",
      "components/universal/UniversalSearch.tsx",
      "components/workflows/WorkflowWorkspace.tsx",
      "app/dashboard/page.tsx",
    ];
    for (const f of files) {
      const content = readFileSync(base + f, "utf-8");
      expect(content).not.toContain("clearToken();\n  window.location.href");
      expect(content).toContain("handleSessionExpired()");
    }
  });
});

describe("security C1 — A: register 409 is generic", () => {
  afterEach(() => cleanup());

  it("never renders backend account-exists message on 409", async () => {
    const { default: RegisterPage } = await import("@/app/auth/register/page");
    const { default: apiModule } = await import("@/lib/api").then((m) => ({ default: m.api }));
    (apiModule.register as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("server", 409, "An account with that email or username already exists"),
    );
    render(<RegisterPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "a@b.io" } });
    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "ab" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "password123" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await waitFor(() =>
      expect(screen.getByText("Unable to create the account. Please verify your information and try again.")).toBeInTheDocument(),
    );
    expect(screen.queryByText(/already exists/i)).toBeNull();
    expect(document.body.innerHTML).not.toContain("already exists");
  });
});

describe("security C1 — B: OAuth authorize_url gate", () => {
  it("safeExternalUrl allows http/https only", () => {
    expect(safeExternalUrl("https://github.com/login/oauth/authorize?x=1")).toBe("https://github.com/login/oauth/authorize?x=1");
    expect(safeExternalUrl("http://localhost:8080/cb")).toBe("http://localhost:8080/cb");
    expect(safeExternalUrl("javascript:alert(1)")).toBeNull();
    expect(safeExternalUrl("data:text/html,<h1>hi</h1>")).toBeNull();
    expect(safeExternalUrl("vbscript:msgbox(1)")).toBeNull();
    expect(safeExternalUrl("//evil.com/path")).toBeNull();
    expect(safeExternalUrl("not a url")).toBeNull();
    expect(safeExternalUrl(null)).toBeNull();
    expect(safeExternalUrl("")).toBeNull();
  });

  it("IntegrationsWorkspace gates the authorize anchor", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync(
      "C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/integrations/IntegrationsWorkspace.tsx",
      "utf-8",
    );
    expect(content).toContain("safeExternalUrl(oauthStartResult.authorize_url)");
    expect(content).toContain("Provider URL blocked");
  });
});

describe("security C1 — C: AI markdown link allowlist", () => {
  afterEach(() => cleanup());

  it("safeMarkdownUrl blocks dangerous schemes", () => {
    expect(safeMarkdownUrl("https://example.com/x")).toBe("https://example.com/x");
    expect(safeMarkdownUrl("http://example.com")).toBe("http://example.com");
    expect(safeMarkdownUrl("mailto:a@b.io")).toBe("mailto:a@b.io");
    expect(safeMarkdownUrl("/knowledge")).toBe("/knowledge");
    expect(safeMarkdownUrl("javascript:alert(1)")).toBe("");
    expect(safeMarkdownUrl("JaVaScRiPt:alert(1)")).toBe("");
    expect(safeMarkdownUrl("data:text/html,<h1>hi</h1>")).toBe("");
    expect(safeMarkdownUrl("vbscript:msgbox(1)")).toBe("");
  });

  it("MessageBubble renders javascript: links inert", () => {
    const { container } = render(
      <MessageBubble
        message={{ id: "m1", role: "assistant", content: "[click me](javascript:alert(1))", created_at: new Date().toISOString() } as never}
      />,
    );
    expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
    expect(container.innerHTML).not.toContain("javascript:alert");
  });

  it("MessageBubble keeps https links working", () => {
    const { container } = render(
      <MessageBubble
        message={{ id: "m2", role: "assistant", content: "[docs](https://example.com/a)", created_at: new Date().toISOString() } as never}
      />,
    );
    const anchor = container.querySelector('a[href="https://example.com/a"]');
    expect(anchor).toBeTruthy();
  });
});

describe("security C1 — D: safeNext blocks ://", () => {
  it("redirects sneaky scheme URLs to dashboard", () => {
    expect(safeNext("/foo://evil")).toBe("/dashboard");
    expect(safeNext("https://evil.com")).toBe("/dashboard");
    expect(safeNext("//evil.com")).toBe("/dashboard");
    expect(safeNext("javascript:alert(1)")).toBe("/dashboard");
    expect(safeNext("/dashboard")).toBe("/dashboard");
    expect(safeNext("/knowledge?q=x")).toBe("/knowledge?q=x");
    expect(safeNext(null)).toBe("/dashboard");
  });
});

describe("security C1 — E: buildHandoff fail-closed, no secrets", () => {
  it("never embeds tokens or secrets in handoff URLs", async () => {
    const { buildHandoff } = await import("@/lib/crossDomain");
    const href = buildHandoff("/knowledge", { q: "test" });
    expect(href).not.toMatch(/nf_token|bearer|secret|api_key|password/i);
    expect(buildHandoff("https://evil.com", { token: "abc" })).toBe("/dashboard");
  });
});
