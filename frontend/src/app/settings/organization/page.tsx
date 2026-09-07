"use client";

/* eslint-disable react-hooks/set-state-in-effect, @typescript-eslint/no-explicit-any */

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { getToken, api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import type { Organization } from "@/types/org";
import { ApiError } from "@/lib/api-client";

export default function OrganizationPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const switchOrganization = useTenantStore((s) => s.switchOrganization);
  const organizations = useTenantStore((s) => s.organizations);
  const setOrganizations = useTenantStore((s) => s.setOrganizations);
  const pushToast = useToastStore((s) => s.push);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Organization | null>(null);
  const [createName, setCreateName] = useState("");
  const [createSlug, setCreateSlug] = useState("");
  const [createDesc, setCreateDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Organization | null>(null);

  const email = user?.email ?? null;

  async function refreshOrgs() {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const orgs = await api.listMyOrganizations(token);
      setOrganizations(orgs);
      // Auto-select current or first
      const currentId = organizationId ?? orgs[0]?.id ?? null;
      if (currentId && orgs.find((o) => o.id === currentId)) {
        const fetched = await api.getOrganization(token, currentId);
        setSelected(fetched);
        if (!organizationId) switchOrganization(currentId);
      } else if (orgs[0]) {
        setSelected(orgs[0]);
      } else {
        setSelected(null);
      }
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        useAuthStore.getState().markExpired();
        window.location.href = "/auth/login";
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load organizations");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refreshOrgs();
    const handler = () => void refreshOrgs();
    window.addEventListener("tenant:switched", handler as EventListener);
    return () => window.removeEventListener("tenant:switched", handler as EventListener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!createName.trim() || !createSlug.trim()) {
      pushToast("error", "Name and slug are required");
      return;
    }
    if (!/^[a-z0-9-]+$/.test(createSlug.trim())) {
      pushToast("error", "Slug must be lowercase letters, numbers and hyphens only");
      return;
    }
    const token = getToken();
    if (!token) return;
    setBusy(true);
    try {
      const created = await api.createOrganization(token, createName.trim(), createSlug.trim(), createDesc.trim());
      pushToast("success", `Organization ${created.name} created`);
      setCreateName("");
      setCreateSlug("");
      setCreateDesc("");
      await refreshOrgs();
      switchOrganization(created.id);
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Create failed");
    } finally {
      setBusy(false);
    }
  }

  async function handleSwitch(org: Organization) {
    const token = getToken();
    if (!token) return;
    try {
      await api.getOrganization(token, org.id);
      switchOrganization(org.id);
      setSelected(org);
      pushToast("success", `Switched to ${org.name}`);
      // Invalidate and refetch dependent data
      window.dispatchEvent(new CustomEvent("tenant:switched", { detail: { nextOrg: org.id } }));
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Switch failed");
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.deleteOrganization(token, deleteTarget.id);
      pushToast("success", "Organization deleted");
      setDeleteTarget(null);
      await refreshOrgs();
      if (organizationId === deleteTarget.id) switchOrganization(null);
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Delete failed");
    }
  }

  const handleLogout = () => { logout("Signed out"); window.location.href = "/auth/login"; };

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame eyebrow="Settings" title="Organization" description="Organization identity, tenants and workspaces. Tenant is organization-scoped." crumbs={[{ label: "Settings", href: "/settings" }, { label: "Organization" }]}>
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={refreshOrgs} /></div> : null}
          {loading ? <BrutalSkeleton className="h-64" /> : (
            <>
              <div className="grid gap-6 lg:grid-cols-2">
                <BrutalCard eyebrow="Current" title={selected?.name ?? "No organization"}>
                  {selected ? (
                    <dl className="space-y-2 text-sm">
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">ID</dt><dd className="font-mono text-xs break-all text-on-surface">{selected.id}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Slug</dt><dd className="text-on-surface">{selected.slug}</dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Plan</dt><dd><BrutalBadge tone="yellow">{selected.plan}</BrutalBadge></dd></div>
                      <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Description</dt><dd className="text-on-surface">{selected.description || "—"}</dd></div>
                    </dl>
                  ) : (
                    <BrutalEmptyState title="No organization selected" description="Create or select an organization." />
                  )}
                </BrutalCard>
                <BrutalCard eyebrow="Create" title="New organization">
                  <form onSubmit={handleCreate} className="space-y-3">
                    <BrutalInput label="Name" placeholder="Acme Corp" value={createName} onChange={(e) => setCreateName(e.target.value)} />
                    <BrutalInput label="Slug" placeholder="acme-corp" value={createSlug} onChange={(e) => setCreateSlug(e.target.value)} />
                    <BrutalInput label="Description" placeholder="Optional" value={createDesc} onChange={(e) => setCreateDesc(e.target.value)} />
                    <BrutalButton type="submit" variant="yellow" disabled={busy}>{busy ? "Creating…" : "Create"}</BrutalButton>
                  </form>
                </BrutalCard>
              </div>

              <div className="mt-6">
                <BrutalCard eyebrow="Organizations" title="Your organizations">
                  {organizations.length === 0 ? (
                    <BrutalEmptyState title="No organizations" description="Create one above." />
                  ) : (
                    <BrutalTable
                      columns={[
                        { key: "name", header: "Name", render: (r: Organization) => <span className="font-bold">{r.name}</span> },
                        { key: "slug", header: "Slug", render: (r: Organization) => r.slug },
                        { key: "plan", header: "Plan", render: (r: Organization) => <BrutalBadge>{r.plan}</BrutalBadge> },
                        {
                          key: "actions", header: "Actions", render: (r: Organization) => (
                            <div className="flex gap-2">
                              <BrutalButton variant="ghost" size="sm" onClick={() => handleSwitch(r)}>Switch</BrutalButton>
                              <BrutalButton variant="ghost" size="sm" onClick={() => setDeleteTarget(r)}>Delete</BrutalButton>
                            </div>
                          ),
                        },
                      ]}
                      rows={organizations as any}
                      emptyMessage="No organizations"
                    />
                  )}
                </BrutalCard>
              </div>
            </>
          )}
          <BrutalModal open={!!deleteTarget} title="Delete organization" onClose={() => setDeleteTarget(null)} actions={<><BrutalButton variant="ghost" onClick={() => setDeleteTarget(null)}>Cancel</BrutalButton><BrutalButton variant="yellow" onClick={handleDelete}>Delete</BrutalButton></>}>
            <p className="text-sm text-on-surface">Delete <strong>{deleteTarget?.name}</strong>? This requires backend authorization and cannot be undone.</p>
          </BrutalModal>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
