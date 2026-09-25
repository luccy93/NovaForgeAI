import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { AiWorkspace } from "@/components/ai/AiWorkspace";
import * as apiModule from "@/lib/api";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/ai",
  useSearchParams: () => new URLSearchParams(),
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
      listConversations: vi.fn(),
    },
    streamChatResponse: vi.fn(),
  };
});

const SRC = "C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src";

function walkTsx(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...walkTsx(full));
    } else if (/\.tsx$/.test(entry) && !/\.test\.tsx$/.test(entry)) {
      out.push(full);
    }
  }
  return out;
}

const PAGE_SHELLS = [
  "app/ml/page.tsx",
  "app/finops/page.tsx",
  "app/workflows/page.tsx",
  "app/ai/page.tsx",
  "app/dashboard/page.tsx",
  "app/admin/page.tsx",
  "app/integrations/page.tsx",
  "app/governance/page.tsx",
  "app/command/page.tsx",
  "app/observability/page.tsx",
  "app/agents/page.tsx",
  "app/developer/page.tsx",
  "app/notifications/page.tsx",
  "app/code/page.tsx",
  "app/knowledge/universal/page.tsx",
  "app/security/page.tsx",
  "app/analytics/page.tsx",
  "app/knowledge/page.tsx",
  "app/knowledge/graph/page.tsx",
  "app/data/page.tsx",
];

describe("security C2 — page shells use unified expiry + logout", () => {
  it("every page shell routes 401 through handleSessionExpired", () => {
    for (const rel of PAGE_SHELLS) {
      const content = readFileSync(`${SRC}/${rel}`, "utf-8");
      expect(content).toContain("handleSessionExpired()");
    }
  });

  it("every page shell logs out through the auth store", () => {
    for (const rel of PAGE_SHELLS) {
      const content = readFileSync(`${SRC}/${rel}`, "utf-8");
      expect(content).toContain("useAuthStore.getState().logout()");
    }
  });

  it("command center and palette use handleSessionExpired", () => {
    for (const rel of ["components/command/CommandCenter.tsx", "components/navigation/CommandPalette.tsx"]) {
      const content = readFileSync(`${SRC}/${rel}`, "utf-8");
      expect(content).toContain("handleSessionExpired()");
    }
  });
});

describe("security C2 — no residual ad-hoc token wipe", () => {
  it("no bare clearToken() statement remains in app/components", () => {
    const offenders: string[] = [];
    for (const full of [...walkTsx(`${SRC}/app`), ...walkTsx(`${SRC}/components`)]) {
      const content = readFileSync(full, "utf-8");
      if (/^\s*clearToken\(\);$/m.test(content)) offenders.push(full);
    }
    expect(offenders).toEqual([]);
  });
});

describe("security C2 — tenant-switch race suppression", () => {
  beforeEach(() => {
    localStorage.clear();
    useTenantStore.setState({
      organizationId: "org-1",
      workspaceId: "ws-1",
      workspaceName: "WS",
      organizations: [{ id: "org-1", name: "Org", slug: "org" } as never],
      workspaces: [{ id: "ws-1", name: "WS" } as never],
    });
    vi.clearAllMocks();
  });
  afterEach(() => {
    cleanup();
    localStorage.clear();
    useTenantStore.getState().clear();
  });

  function avatar(id: string, title: string) {
    return { id, title, message_count: 1, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
  }

  it("stale Tenant A conversation list never overwrites Tenant B", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    let resolveFirst!: (v: unknown) => void;
    const firstFlight = new Promise((resolve) => {
      resolveFirst = resolve;
    });
    mocked.listConversations.mockReturnValueOnce(firstFlight).mockResolvedValue([]);
    render(<AiWorkspace />);
    // Switch context while the first request is still in flight.
    act(() => {
      useTenantStore.getState().switchOrganization("org-2");
    });
    // Tenant A response arrives late.
    resolveFirst([avatar("c-stale", "Stale Tenant A conversation")]);
    // Second (Tenant B) load settles.
    await waitFor(() => expect(mocked.listConversations).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText("No conversations yet")).toBeInTheDocument());
    expect(screen.queryByText("Stale Tenant A conversation")).toBeNull();
  });

  it("workspace switch clears workspace cache but keeps tenant cache", () => {
    localStorage.setItem("nf_cache_tenant", "keep");
    localStorage.setItem("nf_cache_ws_old", "stale-ws");
    useTenantStore.setState({
      organizationId: "org-1",
      workspaceId: "ws-old",
      workspaces: [{ id: "ws-new", name: "New" } as never, { id: "ws-old", name: "Old" } as never],
      organizations: [],
    });
    useTenantStore.getState().switchWorkspace("ws-new", "New");
    expect(localStorage.getItem("nf_cache_ws_old")).toBeNull();
    expect(localStorage.getItem("nf_cache_tenant")).toBe("keep");
    localStorage.removeItem("nf_cache_tenant");
  });
});

describe("security C2 — navigation and handoff integrity", () => {
  it("safeNext still blocks open redirects", async () => {
    const { safeNext } = await import("@/lib/navigation");
    expect(safeNext("/foo://evil")).toBe("/dashboard");
    expect(safeNext("//evil.com")).toBe("/dashboard");
    expect(safeNext("/dashboard")).toBe("/dashboard");
  });

  it("buildHandoff still fail-closed without secrets", async () => {
    const { buildHandoff } = await import("@/lib/crossDomain");
    expect(buildHandoff("https://evil.com", { q: "x" })).toBe("/dashboard");
    expect(buildHandoff("/knowledge", { q: "t" })).not.toMatch(/token|secret/i);
  });

  it("crumbs still resolve nested settings and documents", async () => {
    const { crumbsForPathname } = await import("@/lib/navigation");
    expect(crumbsForPathname("/settings/workspaces")[2]).toEqual({ label: "Workspaces" });
    expect(crumbsForPathname("/knowledge/document/abc")[2]).toEqual({ label: "Document" });
    expect(crumbsForPathname("/dashboard")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Dashboard" }]);
  });
});
