"use client";

/* eslint-disable react-hooks/set-state-in-effect, @typescript-eslint/no-explicit-any */

import { useEffect, useMemo, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { BrutalSelect } from "@/components/ui/BrutalSelect";
import { BrutalTable } from "@/components/ui/BrutalTable";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalModal } from "@/components/ui/BrutalModal";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { getToken, api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import type { OrganizationMember } from "@/types/org";
import { ApiError } from "@/lib/api-client";

const ROLES = ["owner", "admin", "manager", "developer", "reviewer", "viewer", "guest"] as const;

export default function MembersPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const pushToast = useToastStore((s) => s.push);

  const [members, setMembers] = useState<OrganizationMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("member");
  const [inviteBusy, setInviteBusy] = useState(false);
  const [inviteResult, setInviteResult] = useState<{ token: string; email: string } | null>(null);
  const [page, setPage] = useState(1);
  const pageSize = 10;
  const [removeTarget, setRemoveTarget] = useState<OrganizationMember | null>(null);

  const email = user?.email ?? null;

  async function refresh() {
    if (!organizationId) { setLoading(false); return; }
    const token = getToken();
    if (!token) return;
    setLoading(true);
    setError("");
    try {
      const data = await api.listMembers(token, organizationId);
      setMembers(data);
      setPage(1);
    } catch (e) {
      if (e instanceof ApiError && e.kind === "unauthorized") {
        useAuthStore.getState().markExpired();
        window.location.href = "/auth/login";
        return;
      }
      setError(e instanceof Error ? e.message : "Failed to load members");
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

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return members;
    return members.filter((m) => m.email.toLowerCase().includes(q) || m.username.toLowerCase().includes(q) || m.role.toLowerCase().includes(q));
  }, [members, query]);

  const paginated = useMemo(() => {
    const start = (page - 1) * pageSize;
    return filtered.slice(start, start + pageSize);
  }, [filtered, page]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));

  async function handleInvite(e: React.FormEvent) {
    e.preventDefault();
    if (!organizationId) { pushToast("error", "Select an organization first"); return; }
    if (!inviteEmail.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(inviteEmail.trim())) { pushToast("error", "Enter a valid email"); return; }
    const token = getToken();
    if (!token) return;
    setInviteBusy(true);
    setInviteResult(null);
    try {
      const res = await api.inviteMember(token, organizationId, inviteEmail.trim(), inviteRole);
      setInviteResult({ token: res.token, email: res.email });
      pushToast("success", `Invite created for ${res.email}`);
      setInviteEmail("");
      await refresh();
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : "Invite failed");
    } finally {
      setInviteBusy(false);
    }
  }

  async function handleRemove() {
    if (!removeTarget || !organizationId) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.removeMember(token, organizationId, removeTarget.user_id);
      pushToast("success", "Member removed");
      setRemoveTarget(null);
      await refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Remove failed");
    }
  }

  async function handleRoleChange(member: OrganizationMember, newRole: string) {
    if (!organizationId) return;
    const token = getToken();
    if (!token) return;
    try {
      await api.updateMemberRole(token, organizationId, member.user_id, newRole);
      pushToast("success", `Role updated to ${newRole}`);
      await refresh();
    } catch (e) {
      pushToast("error", e instanceof Error ? e.message : "Role update failed");
    }
  }

  const handleLogout = () => { logout("Signed out"); window.location.href = "/auth/login"; };

  if (!organizationId) {
    return (
      <Protected>
        <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
          <PageFrame eyebrow="Settings" title="Members" crumbs={[{ label: "Settings", href: "/settings" }, { label: "Members" }]}>
            <BrutalEmptyState title="No organization selected" description="Select an organization to manage members." actions={<BrutalButton href="/settings/organization" variant="yellow" size="sm">Go to organization</BrutalButton>} />
          </PageFrame>
        </AppShell>
      </Protected>
    );
  }

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame eyebrow="Settings" title="Members" description="Organization members, roles and invitations. Backend remains authoritative." crumbs={[{ label: "Settings", href: "/settings" }, { label: "Members" }]}>
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={refresh} /></div> : null}

          <div className="grid gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <BrutalCard eyebrow="Members" title={`${filtered.length} members`} actions={<BrutalInput placeholder="Search email, username, role" value={query} onChange={(e) => { setQuery(e.target.value); setPage(1); }} aria-label="Search members" />}>
                {loading ? <BrutalSkeleton className="h-64" /> : filtered.length === 0 ? <BrutalEmptyState title="No members" description={query ? "No matching members" : "No members yet"} /> : (
                  <>
                    <BrutalTable
                      columns={[
                        { key: "email", header: "Email", render: (r: OrganizationMember) => <span className="font-mono text-xs">{r.email}</span> },
                        { key: "username", header: "Username", render: (r: OrganizationMember) => r.username },
                        { key: "role", header: "Role", render: (r: OrganizationMember) => <BrutalBadge tone={r.role === "owner" ? "yellow" : "default"}>{r.role}</BrutalBadge> },
                        {
                          key: "actions", header: "Actions", render: (r: OrganizationMember) => (
                            <div className="flex gap-2">
                              <BrutalSelect
                                aria-label={`Role for ${r.email}`}
                                value={r.role}
                                onChange={(e) => handleRoleChange(r, e.target.value)}
                                options={ROLES.map((role) => ({ value: role, label: role }))}
                                className="w-32"
                              />
                              <BrutalButton variant="ghost" size="sm" onClick={() => setRemoveTarget(r)}>Remove</BrutalButton>
                            </div>
                          ),
                        },
                      ]}
                      rows={paginated as any}
                    />
                    <div className="mt-4 flex items-center justify-between">
                      <p className="font-mono text-xs text-on-surface-variant">Page {page} of {totalPages}</p>
                      <div className="flex gap-2">
                        <BrutalButton variant="ghost" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}>Prev</BrutalButton>
                        <BrutalButton variant="ghost" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))}>Next</BrutalButton>
                      </div>
                    </div>
                  </>
                )}
              </BrutalCard>
            </div>
            <div>
              <BrutalCard eyebrow="Invite" title="Invite member">
                <form onSubmit={handleInvite} className="space-y-3">
                  <BrutalInput label="Email" type="email" placeholder="new@company.io" value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} />
                  <BrutalSelect label="Role" value={inviteRole} onChange={(e) => setInviteRole(e.target.value)} options={ROLES.map((r) => ({ value: r, label: r }))} />
                  <BrutalButton type="submit" variant="yellow" fullWidth disabled={inviteBusy}>{inviteBusy ? "Inviting…" : "Send invite"}</BrutalButton>
                  {inviteResult ? <div className="border border-primary-container bg-surface p-3"><p className="font-mono text-xs uppercase tracking-widest text-primary-container">Invite token — copy once</p><p className="mt-2 break-all font-mono text-xs text-on-surface">{inviteResult.token}</p><p className="mt-1 text-xs text-on-surface-variant">For {inviteResult.email} — share securely. It will not be shown again.</p></div> : null}
                  <p className="text-xs text-on-surface-variant">Backend does not send email; token is shown once for manual delivery. No fake pending-accept flow.</p>
                </form>
              </BrutalCard>
            </div>
          </div>

          <BrutalModal open={!!removeTarget} title="Remove member" onClose={() => setRemoveTarget(null)} actions={<><BrutalButton variant="ghost" onClick={() => setRemoveTarget(null)}>Cancel</BrutalButton><BrutalButton variant="yellow" onClick={handleRemove}>Remove</BrutalButton></>}>
            <p className="text-sm text-on-surface">Remove <strong>{removeTarget?.email}</strong> from this organization? This requires backend authorization.</p>
          </BrutalModal>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
