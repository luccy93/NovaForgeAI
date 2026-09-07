"use client";

import { create } from "zustand";
import { api, clearAllTokens, getToken, setToken, setRefreshToken } from "@/lib/api";
import { isMfaChallenge } from "@/types/api";
import type { AuthStatus, SessionUser } from "@/types/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";

interface AuthState {
  status: AuthStatus | "mfa_required";
  user: SessionUser | null;
  mfaChallengeToken: string | null;
  hydrate: () => Promise<void>;
  login: (email: string, password: string) => Promise<"authenticated" | "mfa_required">;
  completeMfa: (code: string) => Promise<void>;
  register: (email: string, username: string, password: string) => Promise<void>;
  logout: (reason?: string) => void;
  markExpired: () => void;
  clearMfa: () => void;
}

function toSessionUser(raw: { id: string; email: string; username: string }): SessionUser {
  return {
    id: raw.id,
    email: raw.email,
    username: raw.username,
  };
}

let hydrating = false;

export const useAuthStore = create<AuthState>((set, get) => ({
  status: "loading",
  user: null,
  mfaChallengeToken: null,

  hydrate: async () => {
    if (hydrating) return;
    hydrating = true;
    const token = getToken();
    if (!token) {
      set({ status: "unauthenticated", user: null, mfaChallengeToken: null });
      hydrating = false;
      return;
    }
    try {
      const me = await api.me(token);
      set({ status: "authenticated", user: toSessionUser(me), mfaChallengeToken: null });
    } catch {
      clearAllTokens();
      useTenantStore.getState().clear();
      set({ status: "expired", user: null, mfaChallengeToken: null });
    } finally {
      hydrating = false;
    }
  },

  login: async (email, password) => {
    const res = await api.login(email, password);
    if (isMfaChallenge(res)) {
      set({ status: "mfa_required", mfaChallengeToken: res.challenge_token, user: null });
      return "mfa_required";
    }
    setToken(res.access_token);
    if (res.refresh_token) setRefreshToken(res.refresh_token);
    try {
      const me = await api.me(res.access_token);
      set({ status: "authenticated", user: toSessionUser(me), mfaChallengeToken: null });
    } catch {
      set({ status: "authenticated", user: null, mfaChallengeToken: null });
    }
    return "authenticated";
  },

  completeMfa: async (code: string) => {
    const challenge = get().mfaChallengeToken;
    if (!challenge) throw new Error("No MFA challenge pending");
    const res = await api.mfaChallenge(challenge, code);
    setToken(res.access_token);
    if (res.refresh_token) setRefreshToken(res.refresh_token);
    const me = await api.me(res.access_token);
    set({ status: "authenticated", user: toSessionUser(me), mfaChallengeToken: null });
  },

  register: async (email, username, password) => {
    const tokens = await api.register(email, username, password);
    setToken(tokens.access_token);
    if (tokens.refresh_token) setRefreshToken(tokens.refresh_token);
    try {
      const me = await api.me(tokens.access_token);
      set({ status: "authenticated", user: toSessionUser(me), mfaChallengeToken: null });
    } catch {
      set({ status: "authenticated", user: null, mfaChallengeToken: null });
    }
  },

  logout: (reason) => {
    clearAllTokens();
    useTenantStore.getState().clear();
    set({ status: "unauthenticated", user: null, mfaChallengeToken: null });
    if (reason) {
      useToastStore.getState().push("info", reason);
    }
  },

  markExpired: () => {
    clearAllTokens();
    useTenantStore.getState().clear();
    set({ status: "expired", user: null, mfaChallengeToken: null });
  },

  clearMfa: () => set({ mfaChallengeToken: null, status: "unauthenticated" }),
}));
