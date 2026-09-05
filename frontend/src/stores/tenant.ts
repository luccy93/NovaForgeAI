"use client";

import { create } from "zustand";

interface TenantState {
  organizationId: string | null;
  workspace: string | null;
  setContext: (organizationId: string | null, workspace: string | null) => void;
  clear: () => void;
}

/**
 * Single tenant/workspace context. Cleared on logout, tenant change,
 * workspace change and session expiration to prevent cross-tenant
 * state leakage.
 */
export const useTenantStore = create<TenantState>((set) => ({
  organizationId: null,
  workspace: null,
  setContext: (organizationId, workspace) => set({ organizationId, workspace }),
  clear: () => set({ organizationId: null, workspace: null }),
}));
