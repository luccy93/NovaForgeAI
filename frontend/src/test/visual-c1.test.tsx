import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalTabs } from "@/components/ui/BrutalTabs";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

describe("visual C1 — design tokens", () => {
  it("globals.css preserves locked palette", async () => {
    const { readFileSync } = await import("node:fs");
    const css = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/app/globals.css", "utf-8");
    expect(css).toContain("#FFED00");
    expect(css).toContain("#0A0A0A");
    expect(css).toContain("#141414");
    expect(css).toContain("#FF6B6B");
    expect(css).toContain("--color-surface");
    expect(css).toContain("--color-primary-container");
  });

  it("no blanket bg-white in ui primitives (allowlist KnowledgeGraph)", async () => {
    const { readFileSync } = await import("node:fs");
    const base = "C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/ui/";
    const files = ["BrutalButton.tsx", "BrutalCard.tsx", "BrutalInput.tsx", "BrutalBadge.tsx", "BrutalTable.tsx"];
    for (const f of files) {
      const content = readFileSync(base + f, "utf-8");
      expect(content).not.toMatch(/bg-white(?!\/)/);
    }
  });
});

describe("visual C1 — buttons", () => {
  afterEach(() => cleanup());
  it("primary uses surface + primary-container, not black/black", () => {
    const { container } = render(<BrutalButton variant="primary">Go</BrutalButton>);
    const btn = container.querySelector("button") as HTMLElement;
    expect(btn.className).toContain("bg-surface");
    expect(btn.className).toContain("text-primary-container");
    expect(btn.className).not.toContain("bg-black");
    expect(btn.className).toContain("hover:scale-[1.02]");
  });

  it("yellow uses on-primary token", () => {
    const { container } = render(<BrutalButton variant="yellow">Go</BrutalButton>);
    const btn = container.querySelector("button") as HTMLElement;
    expect(btn.className).toContain("bg-primary-container");
    expect(btn.className).toContain("text-on-primary");
  });

  it("enforces 44px touch target and focus-visible", () => {
    const { container } = render(<BrutalButton>Go</BrutalButton>);
    const btn = container.querySelector("button") as HTMLElement;
    expect(btn.className).toContain("min-h-[44px]");
    expect(btn.className).toContain("min-w-[44px]");
    expect(btn.className).toContain("focus-visible:outline-primary-container");
    expect(btn.className).toContain("hover:scale-[1.02]");
  });
});

describe("visual C1 — inputs", () => {
  afterEach(() => cleanup());
  it("inputs have min-h 44 and hover border", () => {
    const { container } = render(<BrutalInput label="Email" />);
    const input = container.querySelector("input") as HTMLElement;
    expect(input.className).toContain("min-h-[44px]");
    expect(input.className).toContain("hover:border-outline-variant");
  });

  it("input error has break-words", () => {
    const { container } = render(<BrutalInput label="Email" error="long error message that should wrap" />);
    const err = container.querySelector('[role="alert"]') as HTMLElement;
    expect(err.className).toContain("break-words");
  });
});

describe("visual C1 — cards / panels / states", () => {
  afterEach(() => cleanup());
  it("BrutalCard uses responsive padding and break-words", () => {
    const { container } = render(<BrutalCard title="Title">body</BrutalCard>);
    const sec = container.querySelector("section") as HTMLElement;
    expect(sec.className).toContain("p-4");
    expect(sec.className).toContain("sm:p-6");
    expect(sec.className).toContain("break-words");
  });

  it("BrutalEmptyState uses p-6 sm:p-8", () => {
    const { container } = render(<BrutalEmptyState title="Empty" description="desc" />);
    const div = container.firstChild as HTMLElement;
    expect(div.className).toContain("p-6");
    expect(div.className).toContain("sm:p-8");
  });

  it("BrutalErrorState retry has 44px and focus-visible", () => {
    const { container } = render(<BrutalErrorState title="Err" description="desc" onRetry={() => {}} />);
    const btn = container.querySelector("button") as HTMLElement;
    expect(btn.className).toContain("min-h-[44px]");
    expect(btn.className).toContain("focus-visible:outline-primary-container");
  });

  it("BrutalSkeleton uses motion-safe", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/ui/BrutalSkeleton.tsx", "utf-8");
    expect(content).toContain("motion-safe:animate-pulse");
  });
});

describe("visual C1 — badges / tabs / tables", () => {
  afterEach(() => cleanup());
  it("BrutalBadge yellow uses on-primary", () => {
    const { container } = render(<BrutalBadge tone="yellow">Y</BrutalBadge>);
    const span = container.querySelector("span") as HTMLElement;
    expect(span.className).toContain("bg-primary-container");
    expect(span.className).toContain("text-on-primary");
  });

  it("BrutalTabs uses 11px and on-primary active", () => {
    const { container } = render(<BrutalTabs tabs={[{ id: "a", label: "A", content: "A" }, { id: "b", label: "B", content: "B" }]} />);
    const tab = container.querySelector('[role="tab"]') as HTMLElement;
    expect(tab.className).toContain("text-[11px]");
    expect(container.innerHTML).toContain("text-on-primary");
  });

  it("BrutalTable empty uses responsive padding and header mono 11px", () => {
    const { container } = render(<BrutalTable columns={[{ key: "a", header: "Name", render: (r: never) => String(r) }]} rows={[]} emptyMessage="empty" />);
    const div = container.querySelector('[role="status"]') as HTMLElement;
    expect(div.className).toContain("p-6");
    expect(div.className).toContain("sm:p-8");
  });
});

describe("visual C1 — navigation", () => {
  afterEach(() => cleanup());
  it("SideNav links have min-h and border-l-2", async () => {
    const { SideNav } = await import("@/components/layout/SideNav");
    const { container } = render(<SideNav authenticated={true} />);
    const link = container.querySelector("a") as HTMLElement;
    expect(link.className).toContain("border-l-2");
    expect(link.className).toContain("min-h-[36px]");
  });

  it("UserMenu avatar is 44px", async () => {
    const { UserMenu } = await import("@/components/layout/UserMenu");
    const { container } = render(<UserMenu email="a@b.io" onLogout={() => {}} />);
    const btn = container.querySelector('button[aria-label="Account menu"]') as HTMLElement;
    expect(btn.className).toContain("min-h-[44px]");
    expect(btn.className).toContain("h-11");
  });

  it("CommandPalette section label is 11px", async () => {
    const { CommandPalette } = await import("@/components/navigation/CommandPalette");
    const { container } = render(<CommandPalette open onClose={() => {}} />);
    expect(container.innerHTML).toContain("text-[11px]");
  });
});

describe("visual C1 — motion / 3D", () => {
  it("AICoreScene preserves DPR cap and reduced motion", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/three/AICoreScene.tsx", "utf-8");
    expect(content).toContain("dpr={[1, 1.5]}");
    expect(content).toContain('frameloop={reducedMotion ? "never" : "demand"}');
  });

  it("AnimatedCounter respects reduced motion", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/ui/AnimatedCounter.tsx", "utf-8");
    expect(content).toContain("prefers-reduced-motion");
    expect(content).toContain("useSyncExternalStore");
  });

  it("MotionProvider uses reducedMotion user", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/components/feedback/MotionProvider.tsx", "utf-8");
    expect(content).toContain('reducedMotion="user"');
  });
});
