"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { CommandCenter } from "@/components/command/CommandCenter";
import { api, getToken } from "@/lib/api";
import type { ApiUser } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import { handleSessionExpired, useAuthStore } from "@/stores/auth";

export default function CommandPage() {
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
        <PageFrame
          eyebrow="GLOBAL COMMAND"
          title="Command Center"
          description="Navigation, discovery and actions across the platform. Global search covers the tenant-scoped knowledge base and data catalog."
          crumbs={[{ label: "Command Center" }]}
        >
          <CommandCenter />
        </PageFrame>
      </AppShell>
    </Protected>
  );
}