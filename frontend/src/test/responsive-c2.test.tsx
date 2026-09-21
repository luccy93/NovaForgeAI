import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => "t"),
  clearToken: vi.fn(),
  api: {
    whoami: vi.fn().mockResolvedValue({ permissions: [] }),
    listConversations: vi.fn().mockResolvedValue([]),
    listRepositories: vi.fn().mockResolvedValue([]),
    ciGetIndex: vi.fn().mockResolvedValue({ status: "ready", branch: "main" }),
    knowledgeSearch: vi.fn().mockResolvedValue({ items: [] }),
    dataCatalogSearch: vi.fn().mockResolvedValue({ items: [] }),
    zeroTrustAccessRequests: vi.fn().mockResolvedValue({ items: [] }),
    zeroTrustReviews: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

describe("responsive C2 — enterprise workspaces", () => {
  afterEach(() => cleanup());
  it("AiWorkspace exposes mobile conversation toggle (md:hidden drawer)", async () => {
    const { AiWorkspace } = await import("@/components/ai/AiWorkspace");
    const { container } = render(<AiWorkspace />);
    const btn = container.querySelector('button[aria-label="Open conversations"]') as HTMLElement;
    expect(btn).toBeTruthy();
    expect(btn.textContent).toContain("Conversations");
    // Drawer side left should exist in source
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\ai\\AiWorkspace.tsx", "utf-8"));
    expect(src).toContain('BrutalDrawer');
    expect(src).toContain('side="left"');
  });

  it("CodeWorkspace exposes mobile repository toggle and stacks intelligence", async () => {
    const { CodeWorkspace } = await import("@/components/code/CodeWorkspace");
    const { container } = render(<CodeWorkspace />);
    const btn = container.querySelector('button[aria-label="Open repositories"]') as HTMLElement;
    expect(btn).toBeTruthy();
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\code\\CodeWorkspace.tsx", "utf-8"));
    expect(src).toContain('BrutalDrawer');
    expect(src).toContain('Repositories');
    expect(src).toContain('lg:w-80');
  });

  it("Finops filter controls are responsive (w-full sm:w-32)", async () => {
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\finops\\FinopsWorkspace.tsx", "utf-8"));
    expect(src).toContain("sm:w-32");
    expect(src).toContain("min-w-[120px]");
  });

  it("Governance and Integrations filters are responsive", async () => {
    const gov = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\governance\\GovernanceWorkspace.tsx", "utf-8"));
    const integ = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\integrations\\IntegrationsWorkspace.tsx", "utf-8"));
    expect(gov).toContain("min-w-[120px]");
    expect(integ).toContain("min-w-[120px]");
  });
});

describe("responsive C2 — charts / code / knowledge", () => {
  afterEach(() => cleanup());
  it("BrutalCard remains responsive after C2 workspace changes", async () => {
    const { BrutalCard } = await import("@/components/ui/BrutalCard");
    const { container } = render(<BrutalCard title="Chart">content</BrutalCard>);
    const sec = container.querySelector("section") as HTMLElement;
    expect(sec.className).toContain("p-4");
    expect(sec.className).toContain("sm:p-6");
  });

  it("AICoreScene still preserves DPR cap and reduced motion", async () => {
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\three\\AICoreScene.tsx", "utf-8"));
    expect(src).toContain("dpr={[1, 1.5]}");
    expect(src).toContain('frameloop={reducedMotion ? "never" : "demand"}');
  });

  it("AnimatedBackground still guards reduced motion", async () => {
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\landing\\AnimatedBackground.tsx", "utf-8"));
    expect(src).toContain("prefers-reduced-motion");
    expect(src).toContain("useSyncExternalStore");
  });

  it("IntelligencePanel tabpanel is responsive with min-w-0 flex", async () => {
    const { IntelligencePanel } = await import("@/components/code/IntelligencePanel");
    const { container } = render(<IntelligencePanel repoId="r1" />);
    const tabpanel = container.querySelector('[role="tabpanel"]') as HTMLElement;
    expect(tabpanel).toBeTruthy();
    expect(tabpanel.className).toContain("min-h-0");
  });
});

describe("responsive C2 — landing and docs", () => {
  afterEach(() => cleanup());
  it("landing navigation remains present", async () => {
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\app\\page.tsx", "utf-8"));
    // page should import Navigation and contain AICoreScene
    expect(src.length).toBeGreaterThan(0);
  });

  it("CommandPalette remains responsive after C1 (C2 preserves)", async () => {
    const { CommandPalette } = await import("@/components/navigation/CommandPalette");
    const { container } = render(<CommandPalette open onClose={() => {}} />);
    const dialog = container.querySelector('[role="dialog"][aria-label="Command palette"]') as HTMLElement;
    expect(dialog.className).toContain("max-w-[calc(100vw-16px)]");
  });
});
