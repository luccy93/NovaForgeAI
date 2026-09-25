import { describe, expect, it } from "vitest";
import { isSafeNotificationTarget, NAV_ITEMS, visibleNavItems, filterNavByPermission, crumbsForPathname } from "@/lib/navigation";
import { buildHandoff, buildKnowledgeDocumentHref } from "@/lib/crossDomain";
import { useTenantStore } from "@/stores/tenant";

describe("cross-domain C1 — canonical routes", () => {
  it("all NAV_ITEMS hrefs are canonical and start with /", () => {
    for (const item of NAV_ITEMS) {
      expect(item.href.startsWith("/")).toBe(true);
      expect(item.href).not.toContain("://");
    }
  });

  it("visibleNavItems hides authenticated routes when logged out", () => {
    expect(visibleNavItems(false).map((i) => i.id)).toEqual(["docs"]);
    expect(visibleNavItems(true).length).toBe(NAV_ITEMS.length);
  });

  it("filterNavByPermission unknown never hides", () => {
    expect(filterNavByPermission(NAV_ITEMS, null).length).toBe(NAV_ITEMS.length);
    expect(filterNavByPermission(NAV_ITEMS, []).length).toBe(NAV_ITEMS.length);
    expect(filterNavByPermission(NAV_ITEMS, undefined).length).toBe(NAV_ITEMS.length);
  });

  it("crumbsForPathname returns Home → Label for canonical routes", () => {
    expect(crumbsForPathname("/dashboard")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Dashboard" }]);
    expect(crumbsForPathname("/knowledge/universal")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Global Search" }]);
    expect(crumbsForPathname("/unknown-route-xyz")).toEqual([]);
  });
});

describe("cross-domain C1 — safe notification targets", () => {
  it("allows known routes and settings wildcard", () => {
    expect(isSafeNotificationTarget("/docs")).toBe(true);
    expect(isSafeNotificationTarget("/settings/identity")).toBe(true);
    expect(isSafeNotificationTarget("/settings/workspaces")).toBe(true);
    expect(isSafeNotificationTarget("/admin")).toBe(true);
    expect(isSafeNotificationTarget("/knowledge/graph")).toBe(true);
  });

  it("blocks external, protocol-relative, and unknown", () => {
    expect(isSafeNotificationTarget("https://evil.com")).toBe(false);
    expect(isSafeNotificationTarget("//evil.com")).toBe(false);
    expect(isSafeNotificationTarget("javascript:alert(1)")).toBe(false);
    expect(isSafeNotificationTarget("data:text/html,hi")).toBe(false);
    expect(isSafeNotificationTarget("/unknown-route-xyz")).toBe(false);
    expect(isSafeNotificationTarget(null)).toBe(false);
    expect(isSafeNotificationTarget("")).toBe(false);
  });
});

describe("cross-domain C1 — buildHandoff helper", () => {
  it("builds bare href when no params", () => {
    expect(buildHandoff("/knowledge")).toBe("/knowledge");
    expect(buildHandoff("/ai")).toBe("/ai");
  });

  it("appends query params with encodeURIComponent", () => {
    expect(buildHandoff("/knowledge", { q: "hello world" })).toBe("/knowledge?q=hello+world");
    expect(buildHandoff("/ai", { ref: "notif-123", topic: "security:alert" })).toBe("/ai?ref=notif-123&topic=security%3Aalert");
  });

  it("fail-closed: unsafe href falls back to /dashboard without params", () => {
    expect(buildHandoff("https://evil.com", { q: "test" })).toBe("/dashboard");
    expect(buildHandoff("//evil.com/path", { q: "x" })).toBe("/dashboard");
    expect(buildHandoff("javascript:alert(1)")).toBe("/dashboard");
  });

  it("ignores undefined/null/empty params", () => {
    expect(buildHandoff("/knowledge", { q: undefined, empty: "", valid: "yes" })).toBe("/knowledge?valid=yes");
  });

  it("buildKnowledgeDocumentHref encodes id", () => {
    expect(buildKnowledgeDocumentHref("doc 123/abc")).toBe("/knowledge/document/doc%20123%2Fabc");
    expect(buildKnowledgeDocumentHref("simple-id")).toBe("/knowledge/document/simple-id");
  });

  it("never includes tokens or secrets", () => {
    const href = buildHandoff("/knowledge", { q: "test" });
    expect(href).not.toContain("nf_token");
    expect(href).not.toContain("bearer");
    expect(href.toLowerCase()).not.toContain("secret");
  });
});

describe("cross-domain C1 — tenant/workspace isolation", () => {
  it("clears nf_cache_* on organization switch", () => {
    localStorage.setItem("nf_cache_test", "stale");
    localStorage.setItem("nf_cache_dashboard_org-1", "stale2");
    useTenantStore.getState().switchOrganization("org-new");
    expect(localStorage.getItem("nf_cache_test")).toBeNull();
    expect(localStorage.getItem("nf_cache_dashboard_org-1")).toBeNull();
    // cleanup
    useTenantStore.getState().clear();
  });

  it("clears nf_cache_ws_* on workspace switch preserves tenant cache", () => {
    localStorage.setItem("nf_cache_tenant", "keep");
    localStorage.setItem("nf_cache_ws_old", "stale-ws");
    useTenantStore.setState({ organizationId: "org-1", workspaceId: "ws-old", workspaces: [{ id: "ws-new", name: "New WS" } as never, { id: "ws-old", name: "Old WS" } as never], organizations: [] });
    useTenantStore.getState().switchWorkspace("ws-new", "New WS");
    expect(localStorage.getItem("nf_cache_ws_old")).toBeNull();
    expect(localStorage.getItem("nf_cache_tenant")).toBe("keep");
    localStorage.removeItem("nf_cache_tenant");
    useTenantStore.getState().clear();
  });

  it("auth clear wipes tenant context", () => {
    useTenantStore.setState({ organizationId: "org-1", workspaceId: "ws-1", workspaces: [{ id: "ws-1", name: "WS" } as never], organizations: [{ id: "org-1", name: "Org", slug: "org" } as never] });
    localStorage.setItem("nf_cache_tenant-data", "stale");
    useTenantStore.getState().clear();
    expect(useTenantStore.getState().organizationId).toBeNull();
    expect(useTenantStore.getState().workspaceId).toBeNull();
    expect(localStorage.getItem("nf_cache_tenant-data")).toBeNull();
  });
});
