"use client";

import { create } from "zustand";
import type { Organization, Workspace } from "@/types/org";

const ORG_KEY = "nf_org";
const WS_KEY = "nf_ws";

interface TenantState {
  organizationId: string | null;
  workspaceId: string | null;
  workspaceName: string | null;
  organizations: Organization[];
  workspaces: Workspace[];
  setContext: (organizationId: string | null, workspace: string | null) => void;
  setOrganizations: (orgs: Organization[]) => void;
  setWorkspaces: (workspaces: Workspace[]) => void;
  switchOrganization: (orgId: string | null) => void;
  switchWorkspace: (workspaceId: string | null, workspaceName?: string | null) => void;
  clear: () => void;
}

function loadInitial(): { organizationId: string | null; workspaceId: string | null } {
  if (typeof window === "undefined") return { organizationId: null, workspaceId: null };
  try {
    return {
      organizationId: localStorage.getItem(ORG_KEY),
      workspaceId: localStorage.getItem(WS_KEY),
    };
  } catch {
    return { organizationId: null, workspaceId: null };
  }
}

function persist(orgId: string | null, wsId: string | null) {
  if (typeof window === "undefined") return;
  try {
    if (orgId) localStorage.setItem(ORG_KEY, orgId);
    else localStorage.removeItem(ORG_KEY);
    if (wsId) localStorage.setItem(WS_KEY, wsId);
    else localStorage.removeItem(WS_KEY);
  } catch {}
}

function invalidateCaches(previousOrg: string | null, nextOrg: string | null) {
  if (previousOrg === nextOrg) return;
  // Clear any tenant-scoped caches. In a TanStack Query world this would be queryClient.clear().
  // For now, clear known prefixes and broadcast.
  if (typeof window !== "undefined") {
    try {
      // Remove any keys that contain previous tenant to prevent stale rendering
      for (let i = localStorage.length - 1; i >= 0; i--) {
        const key = localStorage.key(i);
        if (key && key.startsWith("nf_cache_")) localStorage.removeItem(key);
      }
    } catch {}
    // Close realtime connections will be handled by components via effect cleanup
    window.dispatchEvent(new CustomEvent("tenant:switched", { detail: { previousOrg, nextOrg } }));
  }
}

/**
 * Single tenant/workspace context. Cleared on logout, tenant change,
 * workspace change and session expiration to prevent cross-tenant
 * state leakage. Persists current selection in localStorage.
 */
export const useTenantStore = create<TenantState>((set, get) => {
  const initial = loadInitial();
  return {
    organizationId: initial.organizationId,
    workspaceId: initial.workspaceId,
    workspaceName: null,
    organizations: [],
    workspaces: [],
    setContext: (organizationId, workspace) => {
      const prevOrg = get().organizationId;
      const prevWs = get().workspaceId;
      // Workspace param may be id or name; normalize
      const wsId = workspace;
      if (prevOrg !== organizationId || prevWs !== wsId) {
        invalidateCaches(prevOrg, organizationId);
      }
      persist(organizationId, wsId);
      set({ organizationId, workspaceId: wsId, workspaceName: wsId });
    },
    setOrganizations: (organizations) => set({ organizations }),
    setWorkspaces: (workspaces) => set({ workspaces }),
    switchOrganization: (orgId) => {
      const prev = get().organizationId;
      if (prev === orgId) return;
      invalidateCaches(prev, orgId);
      persist(orgId, null);
      set({ organizationId: orgId, workspaceId: null, workspaceName: null, workspaces: [] });
    },
    switchWorkspace: (workspaceId, workspaceName = null) => {
      const prevWs = get().workspaceId;
      if (prevWs === workspaceId) return;
      // Workspace switch also needs cache invalidation for workspace-scoped data
      if (typeof window !== "undefined") {
        try {
          for (let i = localStorage.length - 1; i >= 0; i--) {
            const key = localStorage.key(i);
            if (key && key.startsWith("nf_cache_ws_")) localStorage.removeItem(key);
          }
        } catch {}
        window.dispatchEvent(new CustomEvent("workspace:switched", { detail: { previous: prevWs, next: workspaceId } }));
      }
      persist(get().organizationId, workspaceId);
      set({ workspaceId, workspaceName: workspaceName ?? workspaceId });
    },
    clear: () => {
      const prevOrg = get().organizationId;
      persist(null, null);
      if (typeof window !== "undefined") {
        try {
          for (let i = localStorage.length - 1; i >= 0; i--) {
            const key = localStorage.key(i);
            if (key && (key.startsWith("nf_cache_") || key === ORG_KEY || key === WS_KEY)) {
              // Keep token keys; clear only caches
              if (key.startsWith("nf_cache_")) localStorage.removeItem(key);
            }
          }
        } catch {}
      }
      // Also clear persisted org/ws
      try {
        localStorage.removeItem(ORG_KEY);
        localStorage.removeItem(WS_KEY);
      } catch {}
      if (prevOrg) invalidateCaches(prevOrg, null);
      set({ organizationId: null, workspaceId: null, workspaceName: null, organizations: [], workspaces: [] });
    },
  };
});
