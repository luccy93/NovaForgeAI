import { describe, expect, it } from "vitest";
import { NAV_ITEMS, visibleNavItems } from "@/lib/navigation";

describe("navigation model", () => {
  it("hides authenticated routes from logged-out visitors", () => {
    const items = visibleNavItems(false);
    expect(items.length).toBeGreaterThan(0);
    expect(items.every((item) => !item.auth)).toBe(true);
  });

  it("shows everything to authenticated users", () => {
    expect(visibleNavItems(true)).toHaveLength(NAV_ITEMS.length);
  });

  it("covers every required section", () => {
    const ids = new Set(NAV_ITEMS.map((item) => item.id));
    for (const required of [
      "dashboard",
      "ai",
      "code",
      "knowledge",
      "workflows",
      "agents",
      "finops",
      "integrations",
      "security",
      "governance",
      "observability",
      "admin",
      "settings",
    ]) {
      expect(ids.has(required)).toBe(true);
    }
  });

  it("has unique ids and hrefs", () => {
    const ids = NAV_ITEMS.map((item) => item.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const item of NAV_ITEMS) {
      expect(item.href.startsWith("/")).toBe(true);
    }
  });
});
