import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FooterSection } from "@/components/landing/FooterSection";
import { HeroSection } from "@/components/landing/HeroSection";
import { Navigation } from "@/components/landing/Navigation";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  cleanup();
});

function placeholderAnchors(container: HTMLElement): Element[] {
  return Array.from(container.querySelectorAll('a[href="#"]'));
}

describe("release C1 — footer navigation truth", () => {
  it("contains zero placeholder href=\"#\" anchors", () => {
    const { container } = render(<FooterSection />);
    expect(placeholderAnchors(container)).toEqual([]);
  });

  it("maps existing routes and de-links the rest without inventing routes", () => {
    const { container } = render(<FooterSection />);
    const docs = within(container).getByRole("link", { name: "Documentation" });
    expect(docs.getAttribute("href")).toBe("/docs");
    const integrations = within(container).getByRole("link", { name: "Integrations" });
    expect(integrations.getAttribute("href")).toBe("/integrations");
    // Unmapped items render as explicitly non-interactive text, not anchors.
    const about = screen.getByText("About");
    expect(about.tagName).toBe("SPAN");
    expect(about.closest("a")).toBeNull();
    expect(about).toHaveAttribute("aria-disabled", "true");
    // No invented routes anywhere in the footer.
    const hrefs = Array.from(container.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    for (const href of hrefs) {
      expect(["/docs", "/integrations"]).toContain(href);
    }
  });

  it("renders no social icons without verified profiles", () => {
    const { container } = render(<FooterSection />);
    expect(container.querySelectorAll("a").length).toBe(2);
  });
});

describe("release C1 — landing CTAs navigate to verified routes", () => {
  it("hero Get Started goes to registration", () => {
    const { container } = render(<HeroSection />);
    expect(placeholderAnchors(container)).toEqual([]);
    const cta = screen.getByRole("link", { name: /get started/i });
    expect(cta.getAttribute("href")).toBe("/auth/register");
  });

  it("ai-kit Get Started goes to registration and GitHub CTA is gone", async () => {
    const { default: AiKitPage } = await import("@/app/ai-kit/page");
    const { container } = render(<AiKitPage />);
    expect(placeholderAnchors(container)).toEqual([]);
    const ctas = screen.getAllByRole("link", { name: /get started/i });
    expect(ctas.length).toBeGreaterThan(0);
    for (const cta of ctas) {
      expect(cta.getAttribute("href")).toBe("/auth/register");
    }
    expect(screen.queryByText(/view on github/i)).toBeNull();
  });

  it("landing nav Search goes to public docs and NOVAFORGE+ to registration", () => {
    const { container } = render(<Navigation />);
    expect(placeholderAnchors(container)).toEqual([]);
    // Label is intentionally distinct from the docs page's own
    // "Search documentation" input to avoid duplicate accessible names.
    const search = screen.getByRole("link", { name: "Search docs" });
    expect(search.getAttribute("href")).toBe("/docs");
    const cta = screen.getByRole("link", { name: "NOVAFORGE+" });
    expect(cta.getAttribute("href")).toBe("/auth/register");
  });
});
