"use client";

/* eslint-disable react-hooks/set-state-in-effect, @typescript-eslint/no-explicit-any */

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { getToken, api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import type { Workspace } from "@/types/org";
import { ApiError } from "@/lib/api-client";

export default function WorkspacesPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaces = useTenantStore((s) => s.workspaces);
  const setWorkspaces = useTenantStore((s) => s.setWorkspaces);
  const switchWorkspace = useTenantStore((s) => s.switchWorkspace);
  const pushToast = useToastStore((s) => s.push);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Workspace | null>(null);

  const email = user?.email ?? null;

  async function refresh() {
    if (!organizationId) { setLoading(false); return; }
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const wss = await api.listWorkspaces(token, organizationId);
      setWorkspaces(wss);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        useAuthStore.getState().markExpired();
        window.location.href = "/auth/login";
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load workspaces");
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

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!organizationId) { pushToast("error", "Select an organization first"); return; }
    if (!name.trim() || !slug.trim()) { pushToast("error", "Name and slug required"); return; }
    if (!/^[a-z0-9-]+$/.test(slug.trim())) { pushToast("error", "Slug must be lowercase, numbers, hyphens"); return; }
    const token = getToken();
    if (!token) return;
    setBusy(true);
    try {
      await api.createWorkspace(token, organizationId, name.trim(), slug.trim());
      pushToast("success", "Workspace created");
      setName("");
      setSlug("");
      await refresh();
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteWorkspace(token, deleteTarget.id);
      pushToast("success", "Workspace deleted");
      setDeleteTarget(null);
      await refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Delete failed");
    }
  }

  const handleLogout = () => { logout("Signed out"); window.location.href = "/auth/login"; };

  if (!organizationId) {
    return (
      <Protected>
        <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
          <PageFrame eyebrow="Settings" title="Workspaces" crumbs={[{ label: "Settings", href: "/settings" }, { label: "Workspaces" }]}>
            <BrutalEmptyState title="No organization selected" description="Select an organization to manage workspaces." actions={<BrutalButton href="/settings/organization" variant="yellow" size="sm">Go to organization</BrutalButton>} />
          </PageFrame>
        </AppShell>
      </Protected>
    );
  }

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame eyebrow="Settings" title="Workspaces" description="Workspace list, creation and membership. All mutations require backend authorization." crumbs={[{ label: "Settings", href: "/settings" }, { label: "Workspaces" }]}>
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={refresh} /></div> : null}
          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <BrutalCard eyebrow="Workspaces" title={`${workspaces.length} workspaces`}>
                {loading ? <BrutalSkeleton className="h-64" /> : workspaces.length === 0 ? <BrutalEmptyState title="No workspaces" description="Create one to get started." /> : (
                  <BrutalTable
                    columns={[
                      { key: "name", header: "Name", render: (r: Workspace) => <span className="font-bold">{r.name}</span> },
                      { key: "slug", header: "Slug", render: (r: Workspace) => r.slug ?? "—" },
                      { key: "id", header: "ID", render: (r: Workspace) => <span className="font-mono text-xs">{r.id.slice(0, 8)}…</span> },
                      {
                        key: "actions", header: "Actions", render: (r: Workspace) => (
                          <div className="flex gap-2">
                            <BrutalButton variant="ghost" size="sm" onClick={() => { switchWorkspace(r.id, r.name); pushToast("success", `Switched to ${r.name}`); }}>Switch</BrutalButton>
                            <BrutalButton variant="ghost" size="sm" onClick={() => setDeleteTarget(r)}>Delete</BrutalButton>
                          </div>
                        ),
                      },
                    ]}
                    rows={workspaces as any}
                  />
                )}
              </BrutalCard>
            </div>
            <div>
              <BrutalCard eyebrow="Create" title="New workspace">
                <form onSubmit={handleCreate} className="space-y-3">
                  <BrutalInput label="Name" placeholder="Product" value={name} onChange={(e) => setName(e.target.value)} />
                  <BrutalInput label="Slug" placeholder="product" value={slug} onChange={(e) => setSlug(e.target.value)} />
                  <BrutalButton type="submit" variant="yellow" fullWidth disabled={busy}>{busy ? "Creating…" : "Create workspace"}</BrutalButton>
                  <p className="text-xs text-on-surface-variant">Only exposed where backend supports it. Destructive actions require confirmation.</p>
                </form>
              </BrutalCard>
              <div className="mt-6">
                <BrutalCard eyebrow="Context" title="Current workspace">
                  <p className="text-sm text-on-surface">{useTenantStore.getState().workspaceId ? `Active: ${useTenantStore.getState().workspaceId?.slice(0, 8)}…` : "No workspace selected"}</p>
                  <p className="mt-2 text-xs text-on-surface-variant">Switching clears workspace-scoped caches to prevent stale data.</p>
                </BrutalCard>
              </div>
            </div>
          </div>
          <BrutalModal open={!!deleteTarget} title="Delete workspace" onClose={() => setDeleteTarget(null)} actions={<><BrutalButton variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</BrutalButton><BrutalButton variant="yellow" onClick={handleDelete}>Delete</BrutalButton></>}>
            <p className="text-sm text-on-surface">Delete <strong>{deleteTarget?.name}</strong>? This is destructive and requires authorization.</p>
          </BrutalModal>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
