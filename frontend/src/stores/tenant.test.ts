import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTenantStore } from "@/stores/tenant";

describe("tenant store isolation", () => {
  beforeEach(() => {
    useTenantStore.getState().clear();
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("holds single organization and workspace context", () => {
    const store = useTenantStore.getState();
    store.setContext("org-1", "ws-1");
    expect(useTenantStore.getState().organizationId).toBe("org-1");
    expect(useTenantStore.getState().workspaceId).toBe("ws-1");
  });

  it("switching organization clears workspace and caches", () => {
    const store = useTenantStore.getState();
    store.setContext("org-A", "ws-A");
    localStorage.setItem("nf_cache_test", "stale");
    localStorage.setItem("nf_cache_ws_test", "stale-ws");
    const eventSpy = vi.fn();
    window.addEventListener("tenant:switched", eventSpy as EventListener);
    store.switchOrganization("org-B");
    expect(useTenantStore.getState().organizationId).toBe("org-B");
    expect(useTenantStore.getState().workspaceId).toBeNull();
    expect(localStorage.getItem("nf_cache_test")).toBeNull();
    expect(eventSpy).toHaveBeenCalled();
    window.removeEventListener("tenant:switched", eventSpy as EventListener);
  });

  it("switching workspace does not leak previous workspace data", () => {
    const store = useTenantStore.getState();
    store.setContext("org-1", "ws-1");
    localStorage.setItem("nf_cache_ws_data", "old");
    store.switchWorkspace("ws-2", "WS Two");
    expect(useTenantStore.getState().workspaceId).toBe("ws-2");
    expect(localStorage.getItem("nf_cache_ws_data")).toBeNull();
  });

  it("clear removes all tenant context", () => {
    const store = useTenantStore.getState();
    store.setOrganizations([{ id: "o1", name: "Org", slug: "org", plan: "free", is_active: true, created_at: new Date().toISOString() }]);
    store.setContext("org-1", "ws-1");
    store.clear();
    expect(useTenantStore.getState().organizationId).toBeNull();
    expect(useTenantStore.getState().workspaceId).toBeNull();
    expect(useTenantStore.getState().organizations).toEqual([]);
  });

  it("persists selection in localStorage", () => {
    const store = useTenantStore.getState();
    store.setContext("org-persist", "ws-persist");
    expect(localStorage.getItem("nf_org")).toBe("org-persist");
    expect(localStorage.getItem("nf_ws")).toBe("ws-persist");
  });
});
