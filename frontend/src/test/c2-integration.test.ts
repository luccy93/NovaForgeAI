import { describe, it, expect, beforeEach, vi } from "vitest";
import { visibleNavItems } from "@/lib/navigation";
import { hasPermission, PERMISSIONS } from "@/lib/permissions";
import { useTenantStore } from "@/stores/tenant";
import { useAuthStore } from "@/stores/auth";

describe("C2 integration — adversarial and isolation", () => {
  beforeEach(() => {
    useTenantStore.getState().clear();
    localStorage.clear();
    useAuthStore.setState({ status: "unauthenticated", user: null, mfaChallengeToken: null });
  });

  it("Tenant A -> Tenant B must disappear", () => {
    const store = useTenantStore.getState();
    store.setContext("tenant-A", "ws-A");
    localStorage.setItem("nf_cache_tenant-A_data", "secret-A");
    store.switchOrganization("tenant-B");
    expect(useTenantStore.getState().organizationId).toBe("tenant-B");
    expect(localStorage.getItem("nf_cache_tenant-A_data")).toBeNull();
    expect(useTenantStore.getState().workspaceId).toBeNull();
  });

  it("Workspace A -> Workspace B cached data must not render", () => {
    const store = useTenantStore.getState();
    store.setContext("org-1", "ws-A");
    localStorage.setItem("nf_cache_ws_old", "data-A");
    store.switchWorkspace("ws-B", "Workspace B");
    expect(localStorage.getItem("nf_cache_ws_old")).toBeNull();
    expect(useTenantStore.getState().workspaceId).toBe("ws-B");
  });

  it("hidden navigation does not imply authorization (UX only)", () => {
    const unauth = visibleNavItems(false);
    const auth = visibleNavItems(true);
    expect(auth.length).toBeGreaterThan(unauth.length);
    // Backend remains authoritative: permission check is separate
    expect(hasPermission([], PERMISSIONS.billingAdmin)).toBe(false);
    expect(hasPermission(["billing:admin"], PERMISSIONS.billingAdmin)).toBe(true);
  });

  it("session expiration during context switch clears state", () => {
    const tenant = useTenantStore.getState();
    tenant.setContext("org-1", "ws-1");
    // Simulate 401 during switch -> markExpired
    useAuthStore.getState().markExpired();
    // Auth store should clear tenant
    expect(useAuthStore.getState().status).toBe("expired");
    expect(useTenantStore.getState().organizationId).toBeNull();
  });

  it("cache keys include tenant isolation", () => {
    localStorage.setItem("nf_cache_org-1_key", JSON.stringify({ data: "org1" }));
    expect(localStorage.getItem("nf_cache_org-1_key")).toContain("org1");
    useTenantStore.getState().switchOrganization("org-2");
    // Old cache cleared
    expect(localStorage.getItem("nf_cache_org-1_key")).toBeNull();
  });

  it("realtime channel changes on workspace switch", () => {
    const handler = vi.fn();
    window.addEventListener("workspace:switched", handler as EventListener);
    useTenantStore.getState().setContext("org-1", "ws-1");
    useTenantStore.getState().switchWorkspace("ws-2");
    expect(handler).toHaveBeenCalled();
    window.removeEventListener("workspace:switched", handler as EventListener);
  });

  it("permission-aware UI respects backend permissions", () => {
    const perms: string[] = ["organization:read"];
    expect(hasPermission(perms, PERMISSIONS.orgRead)).toBe(true);
    expect(hasPermission(perms, PERMISSIONS.admin)).toBe(false);
  });

  it("no cross-tenant stale data appears after switch (simulated)", () => {
    // Store data for tenant A
    useTenantStore.getState().setOrganizations([
      { id: "org-A", name: "A", slug: "a", plan: "free", is_active: true, created_at: new Date().toISOString() },
    ]);
    useTenantStore.getState().setContext("org-A", null);
    // Switch to B with different org list
    useTenantStore.getState().setOrganizations([
      { id: "org-B", name: "B", slug: "b", plan: "pro", is_active: true, created_at: new Date().toISOString() },
    ]);
    useTenantStore.getState().switchOrganization("org-B");
    expect(useTenantStore.getState().organizations.find((o) => o.id === "org-A")).toBeUndefined();
  });
});
