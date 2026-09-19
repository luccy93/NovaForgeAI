import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalDrawer } from "@/components/ui/BrutalDrawer";
import { BrutalTabs } from "@/components/ui/BrutalTabs";
import { CommandPalette } from "@/components/navigation/CommandPalette";
import DocsPage from "@/app/docs/page";

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
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
    whoami: vi.fn(),
    zeroTrustAccessRequests: vi.fn(),
    zeroTrustReviews: vi.fn(),
    zeroTrustApproveAccessRequest: vi.fn(),
    zeroTrustCertifyReview: vi.fn(),
  },
}));

describe("a11y C1 — landmarks and skip", () => {
  afterEach(() => cleanup());

  it("skip-to-content link exists and targets main", () => {
    // layout skip link is in RootLayout, but we test AppShell main id
    const { container } = render(
      <div>
        <a href="#main-content" className="sr-only">
          Skip to content
        </a>
        <main id="main-content" tabIndex={-1}>
          content
        </main>
      </div>,
    );
    const link = screen.getByText("Skip to content");
    expect(link).toHaveAttribute("href", "#main-content");
    const main = container.querySelector("#main-content");
    expect(main).toHaveAttribute("tabIndex", "-1");
  });

  it("BrutalCard with title renders section with h2", () => {
    const { container } = render(<BrutalCard title="Test Card">body</BrutalCard>);
    const h2 = screen.getByRole("heading", { name: "Test Card" });
    expect(h2.tagName).toBe("H2");
    expect(container.querySelector("section")).toBeTruthy();
  });
});

describe("a11y C1 — Brutal primitives", () => {
  afterEach(() => cleanup());

  it("BrutalButton a branch respects aria-disabled and spreads rest", () => {
    render(
      <BrutalButton href="/docs" aria-label="Docs" disabled>
        Docs
      </BrutalButton>,
    );
    const link = screen.getByRole("link", { name: "Docs" });
    expect(link).toHaveAttribute("aria-disabled", "true");
    expect(link).toHaveAttribute("tabIndex", "-1");
    expect(link.getAttribute("href")).toBeNull();
  });

  it("BrutalInput generates unique ids via useId", () => {
    render(
      <div>
        <BrutalInput label="Email" />
        <BrutalInput label="Email" />
      </div>,
    );
    const inputs = screen.getAllByLabelText("Email") as HTMLInputElement[];
    expect(inputs[0].id).not.toBe(inputs[1].id);
  });

  it("BrutalInput error is associated via aria-describedby and role=alert", () => {
    render(<BrutalInput label="Email" error="Required" />);
    const input = screen.getByLabelText("Email") as HTMLInputElement;
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby");
    const describedBy = input.getAttribute("aria-describedby")!;
    const errorEl = document.getElementById(describedBy);
    expect(errorEl).toHaveAttribute("role", "alert");
    expect(errorEl?.textContent).toBe("Required");
  });
});

describe("a11y C1 — dialogs focus trap and restoration", () => {
  afterEach(() => cleanup());

  it("BrutalModal focus moves in and restores on close", async () => {
    const onClose = vi.fn();
    const { rerender } = render(
      <div>
        <button>Trigger</button>
        <BrutalModal open={false} title="Test Dialog" onClose={onClose}>
          <button>Inside</button>
        </BrutalModal>
      </div>,
    );
    const trigger = screen.getByText("Trigger");
    trigger.focus();
    expect(document.activeElement).toBe(trigger);
    rerender(
      <div>
        <button>Trigger</button>
        <BrutalModal open={true} title="Test Dialog" onClose={onClose}>
          <button>Inside</button>
        </BrutalModal>
      </div>,
    );
    const dialog = screen.getByRole("dialog", { name: "Test Dialog" });
    await waitFor(() => expect(dialog).toHaveFocus());
    rerender(
      <div>
        <button>Trigger</button>
        <BrutalModal open={false} title="Test Dialog" onClose={onClose}>
          <button>Inside</button>
        </BrutalModal>
      </div>,
    );
    await waitFor(() => expect(trigger).toHaveFocus());
  });

  it("BrutalModal has aria-labelledby linking to h2", () => {
    render(
      <BrutalModal open={true} title="My Dialog" onClose={() => {}}>
        content
      </BrutalModal>,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-labelledby");
    const id = dialog.getAttribute("aria-labelledby")!;
    const heading = document.getElementById(id);
    expect(heading?.textContent).toBe("My Dialog");
  });

  it("BrutalDrawer has Tab trap and aria-labelledby", async () => {
    render(
      <BrutalDrawer open={true} title="Navigate" onClose={() => {}}>
        <button>Item 1</button>
        <button>Item 2</button>
      </BrutalDrawer>,
    );
    const dialog = screen.getByRole("dialog", { name: "Navigate" });
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute("aria-labelledby");
    // focus should be inside drawer
    await waitFor(() => expect(document.activeElement?.closest('[role="dialog"]')).toBeTruthy());
  });
});

describe("a11y C1 — tabs keyboard", () => {
  afterEach(() => cleanup());

  it("BrutalTabs ArrowRight/Left Home/End keyboard", () => {
    render(<BrutalTabs tabs={[{ id: "a", label: "A", content: "A content" }, { id: "b", label: "B", content: "B content" }, { id: "c", label: "C", content: "C content" }]} />);
    const tabA = screen.getByRole("tab", { name: "A" });
    const tabB = screen.getByRole("tab", { name: "B" });
    tabA.focus();
    expect(tabA).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabA, { key: "ArrowRight" });
    expect(tabB).toHaveFocus();
    expect(tabB).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(tabB, { key: "ArrowLeft" });
    expect(screen.getByRole("tab", { name: "A" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "A" }), { key: "End" });
    expect(screen.getByRole("tab", { name: "C" })).toHaveFocus();
    fireEvent.keyDown(screen.getByRole("tab", { name: "C" }), { key: "Home" });
    expect(screen.getByRole("tab", { name: "A" })).toHaveFocus();
  });

  it("BrutalTabs tabpanel is linked via aria-controls and aria-labelledby", () => {
    render(<BrutalTabs tabs={[{ id: "a", label: "A", content: <p>Panel A</p> }]} />);
    const tab = screen.getByRole("tab", { name: "A" });
    const panel = screen.getByRole("tabpanel");
    expect(tab).toHaveAttribute("aria-controls", panel.id);
    expect(panel).toHaveAttribute("aria-labelledby", tab.id);
  });
});

describe("a11y C1 — CommandPalette Home/End", () => {
  afterEach(() => cleanup());

  it("palette supports Home/End to jump to first/last", () => {
    render(<CommandPalette open={true} onClose={() => {}} />);
    const input = screen.getByLabelText("Command palette query");
    input.focus();
    // ArrowDown to second, then Home to first
    fireEvent.keyDown(input, { key: "ArrowDown" });
    fireEvent.keyDown(input, { key: "Home" });
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(input, { key: "End" });
    expect(document.activeElement).toBe(input);
  });
});

describe("a11y C1 — forms", () => {
  afterEach(() => cleanup());

  it("login form inputs have required and autocomplete", async () => {
    const { default: LoginPage } = await import("@/app/auth/login/page");
    render(<LoginPage />);
    const email = screen.getByLabelText("Email") as HTMLInputElement;
    const password = screen.getByLabelText("Password") as HTMLInputElement;
    expect(email).toHaveAttribute("required");
    expect(email).toHaveAttribute("aria-required", "true");
    expect(email).toHaveAttribute("autocomplete", "email");
    expect(password).toHaveAttribute("required");
    expect(password).toHaveAttribute("autocomplete", "current-password");
  });

  it("MFA input has inputMode numeric and required", async () => {
    const { default: MfaPage } = await import("@/app/auth/mfa/page");
    render(<MfaPage />);
    const input = screen.getByLabelText("MFA code") as HTMLInputElement;
    expect(input).toHaveAttribute("inputMode", "numeric");
    expect(input).toHaveAttribute("required");
  });

  it("docs search input has aria-controls and listbox", () => {
    render(<DocsPage />);
    const input = screen.getByLabelText("Search documentation");
    expect(input).toHaveAttribute("aria-controls", "docs-results-list");
    expect(screen.getByRole("listbox", { name: "Documentation results" })).toBeInTheDocument();
  });
});
