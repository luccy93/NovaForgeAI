import { describe, expect, it } from "vitest";

describe("visual C2 — containers and typography", () => {
  it("Data page uses 1400 container", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/data/page.tsx", "utf-8");
    expect(content).toContain("max-w-[1400px]");
    expect(content).not.toContain("max-w-[1600px]");
  });

  it("Dashboard uses 1400 container", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/dashboard/page.tsx", "utf-8");
    expect(content).toContain("max-w-[1400px]");
  });

  it("Data page H1 hierarchy uses 2xl bold with eyebrow 11px", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/data/page.tsx", "utf-8");
    expect(content).toContain('text-[11px]');
    expect(content).toContain('text-2xl font-bold');
    expect(content).toContain('<h1');
  });

  it("Dashboard H1 hierarchy uses Dashboard title", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/dashboard/page.tsx", "utf-8");
    expect(content).toContain('<h1');
    expect(content).toContain('Dashboard');
    expect(content).toContain('text-[11px]');
  });
});

describe("visual C2 — auth pages", () => {
  it("register uses responsive p-4 sm:p-8 and break-words", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/auth/register/page.tsx", "utf-8");
    expect(content).toContain("p-4 sm:p-8");
    expect(content).toContain("break-words");
    expect(content).toContain("text-on-primary");
  });

  it("login uses on-primary token", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/auth/login/page.tsx", "utf-8");
    expect(content).toContain("text-on-primary");
  });
});

describe("visual C2 — dark theme and landing", () => {
  it("landing 3D DPR and reduced motion still preserved", async () => {
    const { readFileSync } = await import("node:fs");
    const aicore = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/three/AICoreScene.tsx", "utf-8");
    expect(aicore).toContain("dpr={[1, 1.5]}");
    expect(aicore).toContain('frameloop={reducedMotion ? "never" : "demand"}');
    const bg = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/landing/AnimatedBackground.tsx", "utf-8");
    expect(bg).toContain("prefers-reduced-motion");
  });

  it("no new bg-white leaks in data page", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/data/page.tsx", "utf-8");
    expect(content).not.toMatch(/bg-white(?!\/)/);
  });
});

describe("visual C2 — responsive preserved", () => {
  it("TopHeader still flex-wrap min-h-16", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/layout/TopHeader.tsx", "utf-8");
    expect(content).toContain("flex-wrap");
    expect(content).toContain("min-h-16");
  });

  it("BrutalCard still responsive p-4 sm:p-6", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/ui/BrutalCard.tsx", "utf-8");
    expect(content).toContain("p-4 sm:p-6");
  });
});
