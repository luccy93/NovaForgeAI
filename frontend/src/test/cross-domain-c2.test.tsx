import { describe, expect, it, vi } from "vitest";
import { crumbsForPathname, isSafeNotificationTarget } from "@/lib/navigation";
import { buildHandoff } from "@/lib/crossDomain";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/settings/workspaces",
  useSearchParams: () => new URLSearchParams({ topic: "security:alert", ref: "notif-123" }),
}));

describe("cross-domain C2 — breadcrumbs", () => {
  it("handles nested settings routes", () => {
    expect(crumbsForPathname("/settings/workspaces")).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "Settings", href: "/settings" },
      { label: "Workspaces" },
    ]);
    expect(crumbsForPathname("/settings/members")).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "Settings", href: "/settings" },
      { label: "Members" },
    ]);
    expect(crumbsForPathname("/settings/security")).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "Settings", href: "/settings" },
      { label: "Security" },
    ]);
  });

  it("handles knowledge document deep link", () => {
    expect(crumbsForPathname("/knowledge/document/abc-123")).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "Knowledge", href: "/knowledge" },
      { label: "Document" },
    ]);
    expect(crumbsForPathname("/knowledge/graph")).toEqual([
      { label: "Home", href: "/dashboard" },
      { label: "Knowledge", href: "/knowledge" },
      { label: "Graph" },
    ]);
  });

  it("still returns flat for canonical routes", () => {
    expect(crumbsForPathname("/dashboard")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Dashboard" }]);
    expect(crumbsForPathname("/unknown")).toEqual([]);
  });
});

describe("cross-domain C2 — safe targets extended", () => {
  it("allows knowledge document prefix", () => {
    expect(isSafeNotificationTarget("/knowledge/document/abc-123")).toBe(true);
    expect(isSafeNotificationTarget("/knowledge/document/xyz")).toBe(true);
    expect(isSafeNotificationTarget("/knowledge/document/")).toBe(true);
  });

  it("still blocks external for document", () => {
    expect(isSafeNotificationTarget("https://evil.com/knowledge/document/abc")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com/knowledge/document/abc")).toBe(false);
  });
});

describe("cross-domain C2 — handoffs with context", () => {
  it("Data→Knowledge preserves dataset name as q", () => {
    expect(buildHandoff("/knowledge", { q: "my dataset" })).toBe("/knowledge?q=my+dataset");
    expect(buildHandoff("/knowledge", { q: "sales+events" })).toBe("/knowledge?q=sales%2Bevents");
  });

  it("buildHandoff never leaks secrets", () => {
    const href = buildHandoff("/knowledge", { q: "test", token: undefined });
    expect(href).not.toContain("token");
    expect(href.toLowerCase()).not.toContain("secret");
  });

  it("Analytics bare handoffs remain canonical", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/analytics/ExecutiveAnalytics.tsx", "utf-8");
    // Analytics should still have linkHref="/finops" etc. bare (no query) where target doesn't support
    expect(content).toContain('linkHref="/finops"');
    expect(content).toContain('linkHref="/governance"');
  });
});

describe("cross-domain C2 — notification AI handoff", () => {
  it("AI page consumes topic param", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/ai/page.tsx", "utf-8");
    expect(content).toContain("useSearchParams");
    expect(content).toContain("searchParams.get");
    expect(content).toContain("Referred from notification");
  });
});

describe("cross-domain C2 — wrapper handles secret safety", () => {
  it("buildHandoff ignores empty values", () => {
    expect(buildHandoff("/knowledge", { q: "" })).toBe("/knowledge");
    expect(buildHandoff("/knowledge", { q: null as unknown as string })).toBe("/knowledge");
  });

  it("buildHandoff encodes special characters", () => {
    expect(buildHandoff("/knowledge", { q: "a/b c" })).toBe("/knowledge?q=a%2Fb+c");
  });
});
