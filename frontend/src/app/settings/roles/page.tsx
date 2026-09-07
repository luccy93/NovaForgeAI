"use client";

/* eslint-disable react-hooks/set-state-in-effect, @typescript-eslint/no-explicit-any */

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { getToken, api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import type { Role } from "@/types/org";
import { ApiError } from "@/lib/api-client";

export default function RolesPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const [roles, setRoles] = useState<Role[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const email = user?.email ?? null;

  async function refresh() {
    if (!organizationId) { setLoading(false); return; }
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.listRoles(token, organizationId);
      setRoles(data);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        useAuthStore.getState().markExpired();
        window.location.href = "/auth/login";
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load roles");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
    const handler = () => void refresh();
    window.addEventListener("tenant:switched", handler as EventListener);
    return () => window.removeEventListener("tenant:switched", handler as EventListener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [organizationId]);

  const handleLogout = () => { logout("Signed out"); window.location.href = "/auth/login"; };

  if (!organizationId) {
    return (
      <Protected>
        <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
          <PageFrame eyebrow="Settings" title="Roles" crumbs={[{ label: "Settings", href: "/settings" }, { label: "Roles" }]}>
            <BrutalEmptyState title="No organization selected" description="Select an organization to view roles." />
          </PageFrame>
        </AppShell>
      </Protected>
    );
  }

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame eyebrow="Settings" title="Roles & permissions" description="Role presentation is read-only; backend remains authoritative. No second RBAC." crumbs={[{ label: "Settings", href: "/settings" }, { label: "Roles" }]}>
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={refresh} /></div> : null}
          {loading ? <BrutalSkeleton className="h-64" /> : roles.length === 0 ? <BrutalEmptyState title="No roles" description="No custom roles. System roles are implicit via membership." /> : (
            <BrutalCard eyebrow="Roles" title={`${roles.length} roles`}>
              <BrutalTable
                columns={[
                  { key: "name", header: "Role", render: (r: Role) => <span className="font-bold">{r.name}</span> },
                  { key: "perms", header: "Permissions", render: (r: Role) => <span className="font-mono text-xs break-words">{r.permissions.slice(0, 6).join(", ")}{r.permissions.length > 6 ? "…" : ""}</span> },
                  { key: "system", header: "System", render: (r: Role) => r.is_system ? <BrutalBadge tone="yellow">system</BrutalBadge> : <BrutalBadge tone="muted">custom</BrutalBadge> },
                ]}
                rows={roles as any}
              />
              <p className="mt-4 text-xs text-on-surface-variant">Permissions are UX hints only. Every protected operation still requires backend authorization. Hidden navigation ≠ access.</p>
            </BrutalCard>
          )}
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
