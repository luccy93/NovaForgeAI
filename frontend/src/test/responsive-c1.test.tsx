import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalDrawer } from "@/components/ui/BrutalDrawer";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSelect } from "@/components/ui/BrutalSelect";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

describe("responsive C1 — AppShell / header", () => {
  afterEach(() => cleanup());
  it("AppShell main has min-w-0 and flex-1 without blank overflow-hidden", async () => {
    const { AppShell } = await import("@/components/layout/AppShell");
    const { container } = render(
      <AppShell email="a@b.io" workspaceLabel="WS test" onLogout={() => {}}>
        <div>content</div>
      </AppShell>,
    );
    const main = container.querySelector("main#main-content") as HTMLElement;
    expect(main.className).toContain("min-w-0");
    expect(main.className).toContain("flex-1");
  });

  it("TopHeader is flex-wrap with min-h-16 and balanced gaps", async () => {
    const { TopHeader } = await import("@/components/layout/TopHeader");
    const { container } = render(<TopHeader email="a@b.io" workspaceLabel="WS" onMenu={() => {}} onLogout={() => {}} />);
    const header = container.querySelector("header") as HTMLElement;
    expect(header.className).toContain("flex-wrap");
    expect(header.className).toContain("min-h-16");
  });

  it("OrgSwitcher is visible at 320 (no hidden md:block) and truncates", async () => {
    const { OrgSwitcher } = await import("@/components/layout/OrgSwitcher");
    // Provide orgs via store
    const { useTenantStore } = await import("@/stores/tenant");
    useTenantStore.setState({ organizations: [{ id: "o1", name: "Very Long Organization Name That Should Truncate At Mobile Width To Avoid Overflow", slug: "long-org" } as never], organizationId: "o1", workspaces: [], workspaceId: null });
    const { container } = render(<OrgSwitcher />);
    const sel = container.querySelector("select") as HTMLSelectElement;
    expect(sel).toBeTruthy();
    expect(sel.className).not.toContain("hidden");
    expect(sel.className).toContain("truncate");
    expect(sel.className).toContain("max-w-[140px]");
  });

  it("WorkspaceSwitcher truncates and is visible at narrow widths", async () => {
    const { WorkspaceSwitcher } = await import("@/components/layout/WorkspaceSwitcher");
    const { useTenantStore } = await import("@/stores/tenant");
    useTenantStore.setState({ organizationId: "o1", workspaces: [{ id: "w1", name: "Extremely Long Workspace Name For Wrapping Test At 320px" } as never], workspaceId: "w1" });
    const { container } = render(<WorkspaceSwitcher />);
    const sel = container.querySelector("select") as HTMLSelectElement;
    expect(sel).toBeTruthy();
    expect(sel.className).not.toContain("hidden");
    expect(sel.className).toContain("truncate");
  });

  it("NotificationBell is visible at 320 with 44px target", async () => {
    const { NotificationBell } = await import("@/components/notifications/NotificationBell");
    const { container } = render(<NotificationBell />);
    const bell = container.querySelector('a[href="/notifications"]') as HTMLElement;
    expect(bell).toBeTruthy();
    expect(bell.className).not.toContain("hidden");
    expect(bell.className).toContain("min-h-[44px]");
  });
});

describe("responsive C1 — dialogs / drawers", () => {
  afterEach(() => cleanup());
  it("BrutalModal constrains to viewport with responsive padding and break-words", () => {
    const { container } = render(<BrutalModal open title="Very Long Dialog Title That Must Wrap Without Causing Viewport Overflow At 320px Width For Testing" onClose={() => {}}>body</BrutalModal>);
    const html = container.innerHTML;
    expect(html).toContain("max-w-[calc(100vw-16px)]");
    expect(html).toContain("max-h-[85vh]");
    expect(html).toContain("p-4");
    expect(html).toContain("break-words");
  });

  it("BrutalDrawer constrains to 85vw on mobile", () => {
    const { container } = render(<BrutalDrawer open title="Navigate" onClose={() => {}}>content</BrutalDrawer>);
    const html = container.innerHTML;
    expect(html).toContain("max-w-[85vw]");
    expect(html).toContain("sm:max-w-sm");
  });
});

describe("responsive C1 — tables / cards / forms", () => {
  afterEach(() => cleanup());
  it("BrutalTable scroll region is bounded and cells break words", () => {
    const cols = [{ key: "a", header: "Name", render: (r: { a: string }) => r.a }];
    const rows = [{ a: "A very long value that should wrap inside table cell without viewport overflow at 320px: " + "x".repeat(80) }];
    const { container } = render(<BrutalTable columns={cols} rows={rows} title="Test table" />);
    const region = container.querySelector('[role="region"]') as HTMLElement;
    expect(region).toBeTruthy();
    expect(region.className).toContain("overflow-x-auto");
    expect(region.getAttribute("tabIndex")).toBe("0");
    const table = container.querySelector("table") as HTMLElement;
    expect(table.className).toContain("min-w-[640px]");
    const td = container.querySelector("td") as HTMLElement;
    expect(td.className).toContain("break-words");
  });

  it("BrutalCard has responsive padding and break-words", () => {
    const { container } = render(<BrutalCard title="Extremely Long Card Title That Must Wrap At Mobile Without Overflow" eyebrow="Long eyebrow label">content with loooooooooooooooooooooooooooooooooooooooooooooooooooooooooongword</BrutalCard>);
    const section = container.querySelector("section") as HTMLElement;
    expect(section.className).toContain("p-4");
    expect(section.className).toContain("sm:p-6");
    expect(section.className).toContain("break-words");
    expect(section.className).toContain("min-w-0");
  });

  it("BrutalInput error wraps with break-words", () => {
    const { container } = render(<BrutalInput label="Email" error="A very long validation error message that must wrap at mobile widths without clipping or causing overflow: please check the format and try again" />);
    const err = container.querySelector('[role="alert"]') as HTMLElement;
    expect(err.className).toContain("break-words");
  });

  it("BrutalSelect error wraps", () => {
    const { container } = render(<BrutalSelect label="Org" error="Another long error that must wrap" options={[{ value: "a", label: "A" }]} />);
    const err = container.querySelector('[role="alert"]') as HTMLElement;
    expect(err.className).toContain("break-words");
  });
});

describe("responsive C1 — command palette", () => {
  afterEach(() => cleanup());
  it("CommandPalette is responsive with viewport calc max-width", async () => {
    const { CommandPalette } = await import("@/components/navigation/CommandPalette");
    const { container } = render(<CommandPalette open onClose={() => {}} />);
    const dialog = container.querySelector('[role="dialog"][aria-label="Command palette"]') as HTMLElement;
    expect(dialog).toBeTruthy();
    expect(dialog.className).toContain("max-w-[calc(100vw-16px)]");
    expect(dialog.className).toContain("sm:max-w-xl");
  });
});

describe("responsive C1 — no blanket overflow-x-hidden", () => {
  it("AppShell does not use blanket overflow-x-hidden on body/main", async () => {
    const src = await import("node:fs").then((m) => m.readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\layout\\AppShell.tsx", "utf-8"));
    // Should have min-w-0 but not blanket overflow-x-hidden on outer
    expect(src).not.toContain("overflow-x-hidden");
    const { AppShell } = await import("@/components/layout/AppShell");
    const { container } = render(<AppShell email={null} workspaceLabel={null} onLogout={() => {}}><div>child</div></AppShell>);
    expect(container.innerHTML).not.toContain("overflow-x-hidden");
  });
});
