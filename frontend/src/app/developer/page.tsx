"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { DeveloperPlatformOverview } from "@/components/developer/DeveloperPlatformOverview";
import { api, getToken } from "@/lib/api";
import type { ApiUser } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import { handleSessionExpired, useAuthStore } from "@/stores/auth";

export default function DeveloperPage() {
  const [user, setUser] = useState<ApiUser | null>(null);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let active = true;
    api
      .me(token)
      .then((me) => {
        if (active) setUser(me);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          handleSessionExpired();
        }
      });
    return () => {
      active = false;
    };
  }, []);

  function logout() {
    useAuthStore.getState().logout();
    window.location.href = "/";
  }

  const email = typeof user?.email === "string" ? user.email : null;
  const orgLabel = organizationId ? `Org ${organizationId.slice(0, 8)}` : null;
  const wsLabel = workspaceId ? `WS ${workspaceId.slice(0, 8)}` : email ? "Workspace" : null;

  return (
    <Protected>
      <AppShell
        email={email}
        workspaceLabel={wsLabel ?? orgLabel ?? (email ? "Workspace" : null)}
        onLogout={logout}
      >
        <div className="border-b border-outline bg-surface px-4 py-4 lg:px-6">
          <h1 className="font-mono text-xs uppercase tracking-widest text-primary-container">Developer Platform</h1>
          <p className="text-sm text-on-surface-variant">{email ?? "Authenticated"} {workspaceId ? `· ${wsLabel}` : ""}</p>
        </div>
        <div className="mx-auto flex w-full max-w-[1600px] flex-col gap-8 overflow-y-auto px-4 py-6 lg:px-6">
          <DeveloperPlatformOverview />
        </div>
      </AppShell>
    </Protected>
  );
}
