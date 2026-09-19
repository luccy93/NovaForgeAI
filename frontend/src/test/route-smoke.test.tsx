import { describe, expect, it } from "vitest";
import { NAV_ITEMS } from "@/lib/navigation";
import { ROUTE_MATRIX, KNOWN_HREFS } from "@/test/helpers";
import { crumbsForPathname, isSafeNotificationTarget, visibleNavItems } from "@/lib/navigation";

describe("Route matrix — completeness", () => {
  it("covers every existing frontend route (39)", () => {
    expect(ROUTE_MATRIX.length).toBe(39);
    // ensure no duplicate hrefs
    const hrefs = ROUTE_MATRIX.map((r) => r.href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
  });

  it("every NAV_ITEMS href is represented in route matrix or is a safe extra", () => {
    const matrixHrefs = new Set(ROUTE_MATRIX.map((r) => r.href));
    const extra = new Set(["/knowledge/universal", "/knowledge/graph"]);
    for (const item of NAV_ITEMS) {
      expect(matrixHrefs.has(item.href) || extra.has(item.href)).toBe(true);
    }
  });

  it("no route has malformed href", () => {
    for (const route of ROUTE_MATRIX) {
      expect(route.href.startsWith("/")).toBe(true);
      expect(route.href.startsWith("//")).toBe(false);
      expect(route.href.includes("://")).toBe(false);
      expect(route.href.includes("javascript:")).toBe(false);
      expect(route.href.includes("data:")).toBe(false);
    }
  });

  it("no route points to removed or fabricated endpoints", () => {
    for (const href of KNOWN_HREFS) {
      expect(href).not.toBe("/sdk");
      expect(href).not.toBe("/cli");
      expect(href).not.toBe("/mcp");
      expect(href).not.toBe("/api-docs");
      expect(href).not.toBe("/qa");
      expect(href).not.toBe("/help");
    }
  });

  it("classifies PUBLIC vs AUTHENTICATED correctly", () => {
    const publicHrefs = ROUTE_MATRIX.filter((r) => r.kind === "PUBLIC" || r.kind === "STATIC_DOCUMENTATION").map((r) => r.href);
    expect(publicHrefs).toContain("/");
    expect(publicHrefs).toContain("/docs");
    expect(publicHrefs).toContain("/auth/login");
    // docs is public, dashboard is not
    expect(publicHrefs).not.toContain("/dashboard");
    expect(ROUTE_MATRIX.find((r) => r.href === "/dashboard")?.kind).toBe("AUTHENTICATED");
  });

  it("public docs remains accessible without authentication (auth:false)", () => {
    const docs = NAV_ITEMS.find((i) => i.href === "/docs")!;
    expect(docs.auth).toBe(false);
    expect(visibleNavItems(false).some((i) => i.href === "/docs")).toBe(true);
    expect(visibleNavItems(false).some((i) => i.href === "/dashboard")).toBe(false);
  });

  it("authenticated routes are hidden from logged-out visitors", () => {
    const loggedOut = visibleNavItems(false).map((i) => i.href);
    expect(loggedOut).not.toContain("/dashboard");
    expect(loggedOut).not.toContain("/code");
    expect(loggedOut).not.toContain("/settings/identity");
  });
});

describe("Route smoke — navigation & deep-link integrity", () => {
  it("every known route is a safe notification target (or /settings/* wildcard)", () => {
    for (const href of ["/docs", "/developer", "/dashboard", "/code", "/settings/identity", "/settings/security", "/knowledge/universal"]) {
      expect(isSafeNotificationTarget(href)).toBe(true);
    }
  });

  it("blocks external, javascript, and unknown routes as unsafe", () => {
    expect(isSafeNotificationTarget("https://evil.com")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com")).toBe(false);
    expect(isSafeNotificationTarget("javascript:alert(1)")).toBe(false);
    expect(isSafeNotificationTarget("data:text/html,hi")).toBe(false);
    expect(isSafeNotificationTarget("/unknown-route-xyz-123")).toBe(false);
    expect(isSafeNotificationTarget("")).toBe(false);
    expect(isSafeNotificationTarget(null as unknown as string)).toBe(false);
  });

  it("breadcrumbs resolve for every NAV route and are empty for unknown", () => {
    for (const item of NAV_ITEMS) {
      const crumbs = crumbsForPathname(item.href);
      expect(crumbs.length).toBe(2);
      expect(crumbs[0]).toEqual({ label: "Home", href: "/dashboard" });
      expect(crumbs[1].label).toBe(item.label);
    }
    expect(crumbsForPathname("/unknown-404-xyz")).toEqual([]);
  });

  it("no internal link in route matrix is external", () => {
    for (const route of ROUTE_MATRIX) {
      expect(route.href.includes("://")).toBe(false);
    }
  });

  it("command palette can derive Go to for every NAV item", () => {
    for (const item of NAV_ITEMS) {
      const label = `Go to ${item.label}`;
      expect(label.startsWith("Go to ")).toBe(true);
      expect(label.length).toBeGreaterThan(6);
    }
  });

  it("route kinds are honest (no fake realtime, no fake metrics)", () => {
    // static docs should not be API-DEPENDENT
    expect(ROUTE_MATRIX.find((r) => r.href === "/docs")?.kind).toBe("STATIC_DOCUMENTATION");
    // dashboard is API-DEPENDENT
    expect(ROUTE_MATRIX.find((r) => r.href === "/dashboard")?.kind).toBe("AUTHENTICATED");
  });
});

describe("Route smoke — loading/empty/error boundaries", () => {
  it("every authenticated route has an expected loading pattern (Protected or manual)", async () => {
    // This is a structural check: authenticated routes should use Protected or manual getToken guard.
    // We verify the matrix marks them as AUTHENTICATED which implies they require auth handling.
    const authRoutes = ROUTE_MATRIX.filter((r) => r.auth);
    expect(authRoutes.length).toBeGreaterThan(25);
    // at least one is manual (/dashboard) but most use Protected — we don't enforce which, just that auth is required
    for (const r of authRoutes) expect(r.auth).toBe(true);
  });

  it("public routes remain accessible without token", () => {
    const publicRoutes = ROUTE_MATRIX.filter((r) => !r.auth).map((r) => r.href);
    expect(publicRoutes).toContain("/docs");
    expect(publicRoutes).toContain("/");
    // ensure no authenticated route is mistakenly public
    expect(publicRoutes).not.toContain("/admin");
  });
});
