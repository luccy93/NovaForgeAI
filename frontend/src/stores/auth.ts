"use client";

import { create } from "zustand";
import { api, clearToken, getToken, setToken } from "@/lib/api";
import type { AuthStatus, SessionUser } from "@/types/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";

interface AuthState {
  status: AuthStatus;
  user: SessionUser | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: (reason?: string) => void;
  markExpired: () => void;
}

function toSessionUser(raw: { id: string; email: string; username: string }): SessionUser {
  return {
    id: raw.id,
    email: raw.email,
    username: raw.username,
  };
}

export const useAuthStore = create<AuthState>((set) => ({
  status: "loading",
  user: null,

  hydrate: async () => {
    const token = getToken();
    if (!token) {
      set({ status: "unauthenticated", user: null });
      return;
    }
    try {
      const me = await api.me(token);
      set({ status: "authenticated", user: toSessionUser(me) });
    } catch {
      clearToken();
      useTenantStore.getState().clear();
      set({ status: "expired", user: null });
    }
  },

  login: async (email, password) => {
    const tokens = await api.login(email, password);
    setToken(tokens.access_token);
    const me = await api.me(tokens.access_token);
    set({ status: "authenticated", user: toSessionUser(me) });
  },

  register: async (email, username, password) => {
    const tokens = await api.register(email, username, password);
    setToken(tokens.access_token);
    const me = await api.me(tokens.access_token);
    set({ status: "authenticated", user: toSessionUser(me) });
  },

  logout: (reason) => {
    clearToken();
    useTenantStore.getState().clear();
    set({ status: "unauthenticated", user: null });
    if (reason) {
      useToastStore.getState().push("info", reason);
    }
  },

  markExpired: () => {
    clearToken();
    useTenantStore.getState().clear();
    set({ status: "expired", user: null });
  },
}));
