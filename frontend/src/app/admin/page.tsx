"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { AdminControlPlane } from "@/components/admin/AdminControlPlane";
import { api, getToken } from "@/lib/api";
import type { ApiUser } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import { handleSessionExpired, useAuthStore } from "@/stores/auth";
import { PERMISSIONS } from "@/types/auth";

export default function AdminPage() {
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
    <Protected requiredPermissions={[PERMISSIONS.admin, PERMISSIONS.opsAdmin]}>
      <AppShell
        email={email}
        workspaceLabel={wsLabel ?? orgLabel ?? (email ? "Workspace" : null)}
        onLogout={logout}
      >
        <PageFrame
          eyebrow="Administration"
          title="Control plane"
          description="Authenticated administrative overview. Management actions remain in their authoritative Settings and platform workspaces."
          crumbs={[{ label: "Administration" }]}
        >
          <AdminControlPlane />
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
