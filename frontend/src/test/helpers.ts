import type { NavItem } from "@/lib/navigation";
import { NAV_ITEMS } from "@/lib/navigation";

export type RouteKind =
  | "PUBLIC"
  | "AUTHENTICATED"
  | "AUTH_CALLBACK"
  | "STATIC_DOCUMENTATION"
  | "ERROR_NOT_FOUND";

export interface RouteRecord {
  href: string;
  kind: RouteKind;
  auth: boolean;
  navItem?: NavItem;
}

export const ROUTE_MATRIX: RouteRecord[] = [
  { href: "/", kind: "PUBLIC", auth: false },
  { href: "/docs", kind: "STATIC_DOCUMENTATION", auth: false, navItem: NAV_ITEMS.find((i) => i.href === "/docs") },
  { href: "/examples", kind: "PUBLIC", auth: false },
  { href: "/ai-kit", kind: "PUBLIC", auth: false },
  { href: "/auth/login", kind: "PUBLIC", auth: false },
  { href: "/auth/register", kind: "PUBLIC", auth: false },
  { href: "/auth/forgot-password", kind: "PUBLIC", auth: false },
  { href: "/auth/reset-password", kind: "AUTH_CALLBACK", auth: false },
  { href: "/auth/verify", kind: "AUTH_CALLBACK", auth: false },
  { href: "/auth/mfa", kind: "AUTH_CALLBACK", auth: false },
  { href: "/dashboard", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/dashboard") },
  { href: "/analytics", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/analytics") },
  { href: "/notifications", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/notifications") },
  { href: "/ai", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/ai") },
  { href: "/command", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/command") },
  { href: "/knowledge", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/knowledge") },
  { href: "/knowledge/universal", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/knowledge/universal") },
  { href: "/knowledge/graph", kind: "AUTHENTICATED", auth: true },
  { href: "/code", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/code") },
  { href: "/developer", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/developer") },
  { href: "/agents", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/agents") },
  { href: "/workflows", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/workflows") },
  { href: "/ml", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/ml") },
  { href: "/observability", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/observability") },
  { href: "/integrations", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/integrations") },
  { href: "/finops", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/finops") },
  { href: "/security", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/security") },
  { href: "/governance", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/governance") },
  { href: "/data", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/data") },
  { href: "/admin", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/admin") },
  { href: "/settings", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/settings") },
  { href: "/settings/profile", kind: "AUTHENTICATED", auth: true },
  { href: "/settings/security", kind: "AUTHENTICATED", auth: true },
  { href: "/settings/preferences", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/settings/preferences") },
  { href: "/settings/identity", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/settings/identity") },
  { href: "/settings/organization", kind: "AUTHENTICATED", auth: true, navItem: NAV_ITEMS.find((i) => i.href === "/settings/organization") },
  { href: "/settings/workspaces", kind: "AUTHENTICATED", auth: true },
  { href: "/settings/members", kind: "AUTHENTICATED", auth: true },
  { href: "/settings/roles", kind: "AUTHENTICATED", auth: true },
];

export function deferred<T>() {
  let resolve!: (v: T) => void;
  let reject!: (e?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export function forgetLocation() {
  const original = Object.getOwnPropertyDescriptor(window, "location");
  const fake = { href: "", pathname: "/" } as unknown as Location;
  Object.defineProperty(window, "location", { configurable: true, value: fake });
  return {
    fake,
    read: () => fake.href,
    restore: () => {
      if (original) Object.defineProperty(window, "location", original);
    },
  };
}

export function installApiMock(overrides: Record<string, unknown> = {}) {
  // helper for tests that need a minimal api mock without touching real network
  // callers should vi.mock("@/lib/api") themselves; this just merges defaults
  return overrides;
}

export function safeNext(value: string | null): string {
  if (!value) return "/dashboard";
  if (!value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  if (value.includes("://")) return "/dashboard";
  return value;
}

export const KNOWN_HREFS = new Set(ROUTE_MATRIX.map((r) => r.href));
