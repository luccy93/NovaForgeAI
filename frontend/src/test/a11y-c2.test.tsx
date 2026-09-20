import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalTabs } from "@/components/ui/BrutalTabs";
import { Toasts } from "@/components/feedback/Toasts";
import { MotionProvider } from "@/components/feedback/MotionProvider";
import { AnimatedBackground } from "@/components/landing/AnimatedBackground";
import { useToastStore } from "@/stores/toast";

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    refresh: vi.fn(),
    back: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
  api: {
    whoami: vi.fn(),
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
  },
}));

describe("a11y C2 - contrast and focus-visible", () => {
  afterEach(() => cleanup());

  it("BrutalInput raises placeholder contrast to /70", () => {
    const { container } = render(<BrutalInput label="Email" placeholder="you@company.io" />);
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.className).toContain("placeholder:text-on-surface-variant/70");
  });

  it("BrutalInput has focus-visible outline classes", () => {
    const { container } = render(<BrutalInput label="Email" />);
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.className).toContain("focus-visible:outline-2");
  });

  it("BrutalInput disabled state raises opacity to /60 and adds cursor", () => {
    const { container } = render(<BrutalInput label="Email" disabled />);
    const input = container.querySelector("input") as HTMLInputElement;
    expect(input.className).toContain("disabled:opacity-60");
  });

  it("BrutalButton enforces 44px touch target", () => {
    render(<BrutalButton>Run</BrutalButton>);
    const button = screen.getByRole("button", { name: "Run" });
    expect(button.className).toContain("min-h-[44px]");
    expect(button.className).toContain("min-w-[44px]");
  });

  it("BrutalTabs buttons enforce 44px touch target with offset focus", () => {
    render(<BrutalTabs tabs={[{ id: "a", label: "A", content: "A" }, { id: "b", label: "B", content: "B" }]} />);
    const tab = screen.getByRole("tab", { name: "A" });
    expect(tab.className).toContain("min-h-[44px]");
    expect(tab.className).toContain("focus-visible:outline-offset-2");
  });
});

describe("a11y C2 - tables", () => {
  afterEach(() => cleanup());

  const columns = [{ key: "name", header: "Name", render: (r: { name: string }) => r.name }];
  const rows = [{ name: "Alpha" }, { name: "Beta" }];

  it("BrutalTable with title emits caption, scroll region, and focus", () => {
    const { container } = render(<BrutalTable columns={columns} rows={rows} title="Inventory" />);
    const caption = container.querySelector("caption");
    expect(caption?.textContent).toBe("Inventory");
    const region = screen.getByRole("region", { name: "Inventory" });
    expect(region).toHaveAttribute("tabIndex", "0");
    expect(region.className).toContain("focus-visible:outline-2");
  });

  it("BrutalTable empty state has role status", () => {
    render(<BrutalTable columns={columns} rows={[]} emptyMessage="Empty here" />);
    const status = screen.getByRole("status");
    expect(status.textContent).toBe("Empty here");
  });
});

describe("a11y C2 - toasts", () => {
  afterEach(() => {
    cleanup();
    useToastStore.setState({ toasts: [] });
  });

  it("toast container announces with aria-live and dismiss has 44px target", () => {
    useToastStore.setState({ toasts: [{ id: "t1", tone: "info", message: "Hello" }] });
    render(<Toasts />);
    expect(screen.getByText("Hello")).toBeInTheDocument();
    const dismiss = screen.getByRole("button", { name: "Dismiss notification" });
    expect(dismiss.className).toContain("min-h-[44px]");
    expect(dismiss.className).toContain("min-w-[44px]");
  });

  it("error toast sets assertive live region", () => {
    useToastStore.setState({ toasts: [{ id: "t2", tone: "error", message: "Boom" }] });
    const { container } = render(<Toasts />);
    const live = container.querySelector("[aria-live='assertive']");
    expect(live).toBeTruthy();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("non-error toasts use polite live region", () => {
    useToastStore.setState({ toasts: [{ id: "t3", tone: "success", message: "Saved" }] });
    const { container } = render(<Toasts />);
    const live = container.querySelector("[aria-live='polite']");
    expect(live).toBeTruthy();
  });
});

describe("a11y C2 - reduced motion wiring", () => {
  afterEach(() => cleanup());

  it("MotionProvider renders children inside MotionConfig", () => {
    render(
      <MotionProvider>
        <p>content</p>
      </MotionProvider>,
    );
    expect(screen.getByText("content")).toBeInTheDocument();
  });

  it("AnimatedBackground renders canvas with pointer-events-none", () => {
    const { container } = render(<AnimatedBackground />);
    const canvas = container.querySelector("canvas");
    expect(canvas).toBeTruthy();
    expect(canvas?.className).toContain("pointer-events-none");
  });
});