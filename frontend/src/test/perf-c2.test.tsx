import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("Perf C2 — heavy splits", () => {
  it("KnowledgeGraph is dynamically imported in graph page (ssr:false)", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\app\\knowledge\\graph\\page.tsx",
      "utf-8",
    );
    expect(content).toContain("dynamic(");
    expect(content).toContain("KnowledgeGraph");
    expect(content).toContain("ssr: false");
    expect(content).toContain("BrutalSkeleton");
  });

  it("AICoreScene remains client but with DPR cap and demand", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\three\\AICoreScene.tsx",
      "utf-8",
    );
    expect(content).toContain("dpr={[1, 1.5]}");
    expect(content).toContain('frameloop={reducedMotion ? "never" : "demand"}');
    expect(content).not.toContain("OrbitControls");
  });
});

describe("Perf C2 — bundle and config", () => {
  it("next.config has optimizePackageImports and removeConsole", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\next.config.ts",
      "utf-8",
    );
    expect(content).toContain("optimizePackageImports");
    expect(content).toContain("lucide-react");
    expect(content).toContain("framer-motion");
    expect(content).toContain("removeConsole");
  });

  it("types are server-safe (no use client)", async () => {
    const types = ["agents", "analytics", "data-platform", "knowledge", "ml", "observability", "security", "universal", "workflows"];
    for (const t of types) {
      const content = readFileSync(
        `C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\types\\${t}.ts`,
        "utf-8",
      );
      expect(content).not.toContain('"use client"');
    }
  });
});

describe("Perf C2 — highlight LRU", () => {
  it("highlight memo is capped at 100 and highlighter cache at 5", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\lib\\highlight.ts",
      "utf-8",
    );
    expect(content).toContain("MAX_MEMO_SIZE = 100");
    expect(content).toContain("memo.size >= MAX_MEMO_SIZE");
    expect(content).toContain("highlighterCache.size >= 5");
  });
});

describe("Perf C2 — dashboard memoization", () => {
  it("dashboard orgLabel/wsLabel use useMemo", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\app\\dashboard\\page.tsx",
      "utf-8",
    );
    expect(content).toContain("useMemo(() => (organizationId");
    expect(content).toContain("useMemo(() => (workspaceId");
  });
});

describe("Perf C2 — navigation throttle", () => {
  it("Navigation scroll handler is throttled via rAF", async () => {
    const content = readFileSync(
      "C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\landing\\Navigation.tsx",
      "utf-8",
    );
    expect(content).toContain("ticking");
    expect(content).toContain("requestAnimationFrame");
    expect(content).toContain("passive: true");
  });
});
