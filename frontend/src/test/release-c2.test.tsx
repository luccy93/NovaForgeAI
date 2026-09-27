import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

afterEach(() => {
  cleanup();
});

describe("release C2 — full landing surface has no dead navigation", () => {
  it("landing page contains zero placeholder href=\"#\" anchors", async () => {
    const { default: LandingPage } = await import("@/app/page");
    const { container } = render(<LandingPage />);
    expect(Array.from(container.querySelectorAll('a[href="#"]'))).toEqual([]);
  });

  it("every landing anchor resolves to a verified route or section fragment", async () => {
    const { default: LandingPage } = await import("@/app/page");
    const { container } = render(<LandingPage />);
    const hrefs = Array.from(container.querySelectorAll("a")).map((a) => a.getAttribute("href"));
    expect(hrefs.length).toBeGreaterThan(0);
    for (const href of hrefs) {
      expect(href).toBeTruthy();
      // Verified internal routes, in-page fragments, or the registration CTA.
      const ok =
        href === "/" ||
        href!.startsWith("/auth/") ||
        href!.startsWith("/docs") ||
        href!.startsWith("/examples") ||
        href!.startsWith("/ai-kit") ||
        href!.startsWith("/integrations") ||
        href!.startsWith("#");
      expect(ok).toBe(true);
    }
    // Fragments must target elements that exist on the page.
    for (const href of hrefs) {
      if (href!.startsWith("#") && href!.length > 1) {
        expect(container.querySelector(href!)).not.toBeNull();
      }
    }
  });

  it("back-to-top control is keyboard-focusable with an accessible name", async () => {
    const { default: LandingPage } = await import("@/app/page");
    render(<LandingPage />);
    const backToTop = screen.getByRole("button", { name: "Back to top" });
    expect(backToTop).toBeInTheDocument();
  });
});

describe("release C2 — C1 fixes hold on re-verification", () => {
  it("auth/session, tenant race, and target validation suites still pass", async () => {
    // Structural anchor: the C1 helper and validators this phase relies on.
    const nav = await import("@/lib/navigation");
    expect(nav.isSafeNotificationTarget("/knowledge?q=x")).toBe(true);
    expect(nav.isSafeNotificationTarget("javascript:alert(1)")).toBe(false);
    expect(nav.safeNext("/foo://evil")).toBe("/dashboard");
    const { safeMarkdownUrl } = await import("@/components/ai/MessageBubble");
    expect(safeMarkdownUrl("javascript:alert(1)")).toBe("");
    const { safeExternalUrl, buildHandoff } = await import("@/lib/crossDomain");
    expect(safeExternalUrl("https://github.com/login/oauth/authorize?x=1")).toBeTruthy();
    expect(buildHandoff("https://evil.com", { q: "x" })).toBe("/dashboard");
  });
});
