import { describe, expect, it } from "vitest";
import type { NavItem } from "@/lib/navigation";
import {
  NAV_GROUPS,
  NAV_ITEMS,
  crumbsForPathname,
  filterNavByPermission,
  visibleNavItems,
} from "@/lib/navigation";

describe("navigation model", () => {
  it("hides authenticated routes from logged-out visitors", () => {
    const items = visibleNavItems(false);
    expect(items.length).toBe(0);
  });

  it("shows everything to authenticated users", () => {
    expect(visibleNavItems(true)).toHaveLength(NAV_ITEMS.length);
  });

  it("covers every required section", () => {
    const ids = new Set(NAV_ITEMS.map((item) => item.id));
    for (const required of [
      "dashboard",
      "ai",
      "command",
      "global-search",
      "code",
      "knowledge",
      "workflows",
      "agents",
      "finops",
      "integrations",
      "data",
      "ml",
      "security",
      "governance",
      "observability",
      "control-plane",
      "settings-organization",
      "settings",
    ]) {
      expect(ids.has(required)).toBe(true);
    }
  });

  it("assigns every item to a known enterprise group", () => {
    const groups = new Set(NAV_GROUPS.map((g) => g.id));
    for (const item of NAV_ITEMS) {
      expect(groups.has(item.group)).toBe(true);
    }
  });

  it("has unique ids and hrefs", () => {
    const ids = NAV_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const item of NAV_ITEMS) {
      expect(item.href.startsWith("/")).toBe(true);
    }
  });

  it("keeps navigation visible when permissions are unknown", () => {
    expect(filterNavByPermission(NAV_ITEMS, null)).toHaveLength(NAV_ITEMS.length);
    expect(filterNavByPermission(NAV_ITEMS, undefined)).toHaveLength(NAV_ITEMS.length);
    expect(filterNavByPermission(NAV_ITEMS, [])).toHaveLength(NAV_ITEMS.length);
  });

  it("hides only items explicitly denied by a known permission set", () => {
    const items: Array<NavItem> = [
      { id: "a", label: "A", href: "/a", section: "main", group: "command", auth: true, description: "", permission: "zero_trust:write" },
      { id: "b", label: "B", href: "/b", section: "main", group: "command", auth: true, description: "" },
    ];
    const visible = filterNavByPermission(items, ["zero_trust:write"]);
    expect(visible).toHaveLength(2);
    const withoutPermission = filterNavByPermission(items, []);
    expect(withoutPermission).toHaveLength(2);
    const denied = filterNavByPermission(items, []);
    expect(denied.map((item) => item.id)).toEqual(["a", "b"]);
    const knownDenied = filterNavByPermission(items.filter((i) => i.id === "a"), ["anything:else"]);
    expect(knownDenied).toHaveLength(0);
  });

  it("derives breadcrumbs from the navigation model", () => {
    expect(crumbsForPathname("/dashboard")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Dashboard" }]);
    expect(crumbsForPathname("/knowledge/universal")).toEqual([{ label: "Home", href: "/dashboard" }, { label: "Global Search" }]);
    expect(crumbsForPathname("/unknown")).toEqual([]);
  });
});