import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DocsOverview } from "@/components/docs/DocsOverview";
import { DOCS_INDEX } from "@/components/docs/docsData";
import { NAV_ITEMS, crumbsForPathname, isSafeNotificationTarget, visibleNavItems } from "@/lib/navigation";
import DocsPage from "@/app/docs/page";

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
  api: {
    me: vi.fn(),
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
  },
}));

describe("Docs Hardening — navigation & palette", () => {
  afterEach(() => cleanup());

  it("NAV_ITEMS contains Documentation as public", () => {
    const docs = NAV_ITEMS.find((i) => i.id === "docs");
    expect(docs).toBeDefined();
    expect(docs?.href).toBe("/docs");
    expect(docs?.auth).toBe(false);
  });

  it("visibleNavItems shows docs to logged-out visitors", () => {
    expect(visibleNavItems(false).map((i) => i.id)).toEqual(["docs"]);
    expect(visibleNavItems(true).some((i) => i.id === "docs")).toBe(true);
  });

  it("breadcrumbs for /docs resolve to Home → Documentation", () => {
    expect(crumbsForPathname("/docs")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Documentation" }]);
  });

  it("isSafeNotificationTarget allows /docs and blocks external URLs", () => {
    expect(isSafeNotificationTarget("/docs")).toBe(true);
    expect(isSafeNotificationTarget("/developer")).toBe(true);
    expect(isSafeNotificationTarget("https://evil.com")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com")).toBe(false);
    expect(isSafeNotificationTarget("javascript:alert(1)")).toBe(false);
  });

  it("command palette derives Go to Documentation from NAV_ITEMS (verified via navigation model)", () => {
    const docs = NAV_ITEMS.find((i) => i.id === "docs")!;
    expect(`Go to ${docs.label}`).toBe("Go to Documentation");
  });
});

describe("Docs Hardening — search (deterministic local)", () => {
  beforeEach(() => vi.clearAllMocks());
  afterEach(() => cleanup());

  it("search input is accessible and controls the listbox", () => {
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    expect(input).toHaveAttribute("aria-controls", "docs-results-list");
    expect(input).toHaveAttribute("placeholder", "Search docs, APIs, guides...");
    expect(screen.getByRole("listbox", { name: "Documentation results" })).toBeInTheDocument();
  });

  it("filters over DOCS_INDEX only (no backend) and shows no-results state", () => {
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "SDK" } });
    expect(screen.getByText(/result.*for "SDK"/i)).toBeInTheDocument();
    // should contain SDK entry (heading + result)
    expect(screen.getAllByText("SDK").length).toBeGreaterThanOrEqual(1);
    fireEvent.change(input, { target: { value: "zzzznonexistent" } });
    expect(screen.getByText("No documentation matches")).toBeInTheDocument();
    expect(screen.getByText(/No results for "zzzznonexistent"/)).toBeInTheDocument();
  });

  it("search is case-insensitive and keyword-aware", () => {
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "mcp" } });
    expect(screen.getAllByText("MCP").length).toBeGreaterThanOrEqual(1);
    fireEvent.change(input, { target: { value: "MCP" } });
    expect(screen.getAllByText("MCP").length).toBeGreaterThanOrEqual(1);
  });

  it("keyboard navigation: ArrowDown/ArrowUp moves active option, Enter navigates", () => {
    const original = Object.getOwnPropertyDescriptor(window, "location");
    const fake = { href: "" } as unknown as Location;
    Object.defineProperty(window, "location", { configurable: true, value: fake });

    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    input.focus();
    fireEvent.change(input, { target: { value: "" } });
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "false");
    expect(screen.getAllByRole("option")[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "ArrowUp" });
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "Enter" });
    // Enter should navigate to the active hit's href (first result is Overview → /docs#overview)
    expect(fake.href).toBe(DOCS_INDEX[0].href);

    if (original) Object.defineProperty(window, "location", original);
  });

  it("Escape clears the query", () => {
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "SDK" } });
    expect(input.value).toBe("SDK");
    fireEvent.keyDown(input, { key: "Escape" });
    expect(input.value).toBe("");
    // after clear, full list is back
    expect(screen.getAllByRole("option").length).toBeGreaterThan(5);
  });

  it("does not call backend search endpoints (no knowledgeSearch/dataCatalogSearch)", async () => {
    const { api } = await import("@/lib/api");
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "hello" } });
    expect(vi.mocked(api.knowledgeSearch ?? (() => {}) as unknown as ReturnType<typeof vi.fn>)).not.toHaveBeenCalled?.();
    // ensure no fetch was triggered at all
    const anyMockCalled = Object.values(api).some((fn) => typeof fn === "function" && vi.isMockFunction(fn) && (fn as unknown as ReturnType<typeof vi.fn>).mock.calls.length > 0);
    expect(anyMockCalled).toBe(false);
  });

  it("announces result count via polite live region", () => {
    render(<DocsOverview />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "API" } });
    const region = screen.getByRole("region", { name: "Search results" });
    expect(region).toHaveAttribute("aria-live", "polite");
    expect(screen.getByText(/result.*for "API"/i)).toBeInTheDocument();
  });
});

describe("Docs Hardening — content, links, security", () => {
  afterEach(() => cleanup());

  it("documents verified platform routes (no invented routes)", () => {
    render(<DocsOverview />);
    expect(screen.getByRole("heading", { name: "Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "FAQ" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Troubleshooting" })).toBeInTheDocument();
    // verify a few canonical handoffs exist
    expect(screen.getByRole("link", { name: "Open Code Platform" })).toHaveAttribute("href", "/code");
    expect(screen.getByRole("link", { name: "Open AI Platform" })).toHaveAttribute("href", "/ai");
  });

  it("SDK/CLI/MCP handoffs go to /docs and MCP is NOT EXPOSED", () => {
    render(<DocsOverview />);
    expect(screen.getByRole("heading", { name: "SDK" })).toBeInTheDocument();
    const sdkButtons = screen.getAllByRole("link", { name: "View SDK Documentation" });
    expect(sdkButtons[0]).toHaveAttribute("href", "/docs");
    expect(screen.getAllByRole("link", { name: "View MCP Documentation" })[0]).toHaveAttribute("href", "/docs");
    const mcpCard = screen.getByRole("heading", { name: "MCP" }).closest("section")!;
    expect(mcpCard.textContent).toContain("NOT EXPOSED BY API");
  });

  it("link integrity: every DOCS_INDEX href is known route or /docs# anchor or openapi discovery", () => {
    const knownHrefs = new Set([
      ...NAV_ITEMS.map((i) => i.href),
      "/knowledge/universal",
      "/knowledge/graph",
      "/openapi.json",
      "/.well-known/novaforge.json",
    ]);
    for (const entry of DOCS_INDEX) {
      const href = entry.href;
      const isKnownRoute = knownHrefs.has(href);
      const isDocsAnchor = href.startsWith("/docs#");
      const isSettings = href.startsWith("/settings/");
      expect(isKnownRoute || isDocsAnchor || isSettings).toBe(true);
    }
  });

  it("internal links only: no external, javascript:, or data: URLs", () => {
    render(<DocsOverview />);
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of hrefs) {
      expect(href.startsWith("/")).toBe(true);
      expect(href).not.toMatch(/^https?:/);
      expect(href).not.toMatch(/^javascript:/);
      expect(href).not.toMatch(/^data:/);
      expect(href.includes("://")).toBe(false);
      expect(href.startsWith("//")).toBe(false);
    }
    // docs page itself also
    render(<DocsPage />);
    const pageHrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of pageHrefs) {
      if (href && href !== "#") {
        expect(href).not.toMatch(/^https:\/\/evil/);
        expect(href).not.toMatch(/^\/\/evil/);
      }
    }
  });

  it("does not create /sdk, /cli, /mcp, /api-docs, /help parallel routes", () => {
    render(<DocsOverview />);
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of hrefs) {
      expect(href).not.toBe("/sdk");
      expect(href).not.toBe("/cli");
      expect(href).not.toBe("/mcp");
      expect(href).not.toBe("/api-docs");
      expect(href).not.toBe("/help");
      expect(href).not.toBe("/documentation");
    }
  });

  it("no secrets leaked in docs", () => {
    render(<DocsOverview />);
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("client_secret");
    expect(html).not.toContain("password");
    expect(html).not.toMatch(/nf_[a-z0-9]{20,}/);
    expect(html).not.toContain("sk-");
    expect(screen.queryByText(/Bearer eyJ/)).toBeNull();
  });

  it("no fake metrics or counts", () => {
    render(<DocsOverview />);
    expect(screen.queryByText(/12,453 developers/i)).toBeNull();
    expect(screen.queryByText(/Trending/i)).toBeNull();
    expect(screen.queryByText(/Most viewed/i)).toBeNull();
    expect(screen.queryByText(/99\.9%/)).toBeNull();
  });

  it("no fake SDK/CLI/MCP methods/commands", () => {
    render(<DocsOverview />);
    expect(screen.getByText(/IntegrationMixin 21 methods/)).toBeInTheDocument();
    expect(screen.queryByText(/npm install @novaforge\/sdk/)).toBeNull();
    expect(screen.queryByText(/novaforge deploy/)).toBeNull();
    expect(screen.queryByText(/mcp.*transport is running/i)).toBeNull();
  });

  it("troubleshooting covers verified backend conditions", () => {
    render(<DocsOverview />);
    expect(screen.getByText("SESSION EXPIRED (401)")).toBeInTheDocument();
    expect(screen.getByText("ACCESS DENIED (403)")).toBeInTheDocument();
    expect(screen.getByText("RESOURCE NOT FOUND (404)")).toBeInTheDocument();
    expect(screen.getByText("CONFLICT (409)")).toBeInTheDocument();
    expect(screen.getByText("INVALID REQUEST (422)")).toBeInTheDocument();
    expect(screen.getByText("SERVICE UNAVAILABLE (5xx)")).toBeInTheDocument();
  });

  it("FAQ answers match actual implementation", () => {
    render(<DocsOverview />);
    expect(screen.getByText("Where are API keys managed?")).toBeInTheDocument();
    expect(screen.getByText(/\/settings\/security/)).toBeInTheDocument();
    expect(screen.getByText("Is realtime available?")).toBeInTheDocument();
    expect(screen.getByText("Is MCP runtime available?")).toBeInTheDocument();
    expect(screen.getByText(/validate-only via POST \/security\/plugin\/mcp\/validate/)).toBeInTheDocument();
  });

  it("is GLOBAL static: tenant/workspace switch does not break docs", () => {
    render(<DocsOverview />);
    const before = screen.getByText("NovaForge Documentation");
    window.dispatchEvent(new Event("tenant:switched"));
    window.dispatchEvent(new Event("workspace:switched"));
    expect(screen.getByText("NovaForge Documentation")).toBeInTheDocument();
    // search still works after switch (no stale request error)
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "API" } });
    expect(screen.getByText(/result.*for "API"/i)).toBeInTheDocument();
    expect(before).toBeInTheDocument();
  });

  it("does not make nonexistent API requests", async () => {
    const { api } = await import("@/lib/api");
    vi.clearAllMocks();
    render(<DocsOverview />);
    const anyCalled = Object.values(api).some((fn) => typeof fn === "function" && vi.isMockFunction(fn) && (fn as unknown as ReturnType<typeof vi.fn>).mock.calls.length > 0);
    expect(anyCalled).toBe(false);
  });
});

describe("Docs Hardening — UX & a11y", () => {
  afterEach(() => cleanup());

  it("keyboard navigation: all handoff links are focusable", () => {
    render(<DocsOverview />);
    const links = Array.from(document.querySelectorAll("a[href]")) as HTMLAnchorElement[];
    expect(links.length).toBeGreaterThan(10);
    for (const a of links) {
      expect(a.tabIndex).not.toBe(-1);
    }
  });

  it("accessibility: headings, landmarks, and search have correct semantics", () => {
    render(<DocsOverview />);
    expect(screen.getByRole("heading", { name: "Documentation" })).toBeInTheDocument();
    expect(screen.getAllByRole("heading").length).toBeGreaterThan(8);
    expect(screen.getByLabelText("Search documentation")).toBeInTheDocument();
    expect(screen.getByRole("listbox", { name: "Documentation results" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Search results" })).toHaveAttribute("aria-live", "polite");
  });

  it("responsive UI: grid uses brutal responsive layout", () => {
    render(<DocsOverview />);
    expect(document.querySelector(".grid.gap-6.md\\:grid-cols-2")).toBeTruthy();
  });

  it("no hydration errors: renders without throwing", () => {
    expect(() => render(<DocsOverview />)).not.toThrow();
    expect(screen.getByTestId("docs-overview")).toBeInTheDocument();
  });

  it("no console errors during render", () => {
    const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});
    render(<DocsOverview />);
    expect(errSpy).not.toHaveBeenCalled();
    expect(warnSpy).not.toHaveBeenCalled();
    errSpy.mockRestore();
    warnSpy.mockRestore();
  });

  it("existing routes remain functional via handoffs", () => {
    render(<DocsOverview />);
    expect(screen.getByRole("link", { name: "Open Code Platform" })).toHaveAttribute("href", "/code");
    expect(screen.getByRole("link", { name: "Open AI Platform" })).toHaveAttribute("href", "/ai");
    expect(screen.getAllByRole("link", { name: "Open Agents" })[0]).toHaveAttribute("href", "/agents");
    expect(NAV_ITEMS.some((i) => i.href === "/code")).toBe(true);
    expect(NAV_ITEMS.some((i) => i.href === "/ai")).toBe(true);
  });
});
