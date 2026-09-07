"use client";

import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { useAuthStore } from "@/stores/auth";
import { getToken } from "@/lib/api";

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const email = user?.email ?? (typeof window !== "undefined" ? null : null);

  const handleLogout = () => {
    const token = getToken();
    if (token) {
      // best-effort server side session cleanup is handled by security page
    }
    logout("Signed out");
    window.location.href = "/auth/login";
  };

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame
          eyebrow="Settings"
          title="Settings"
          description="Manage your account, organization and workspace."
          crumbs={[{ label: "Home", href: "/" }, { label: "Settings" }]}
        >
          <div className="grid gap-6 md:grid-cols-2">
            <BrutalCard eyebrow="Account" title="Profile & Security" actions={<BrutalButton href="/settings/profile" variant="ghost" size="sm">Open</BrutalButton>}>
              <p className="text-sm text-on-surface-variant">Identity, account metadata and active session.</p>
              <div className="mt-4 flex gap-2">
                <BrutalButton href="/settings/profile" variant="default" size="sm">Profile</BrutalButton>
                <BrutalButton href="/settings/security" variant="default" size="sm">Security</BrutalButton>
              </div>
            </BrutalCard>
            <BrutalCard eyebrow="Organization" title="Organization" actions={<BrutalButton href="/settings/organization" variant="ghost" size="sm">Open</BrutalButton>}>
              <p className="text-sm text-on-surface-variant">Organization identity, tenants and workspaces.</p>
              <div className="mt-4 flex gap-2">
                <BrutalButton href="/settings/organization" variant="default" size="sm">Overview</BrutalButton>
                <BrutalButton href="/settings/members" variant="default" size="sm">Members</BrutalButton>
              </div>
            </BrutalCard>
            <BrutalCard eyebrow="Access" title="Members & Roles" actions={<BrutalButton href="/settings/members" variant="ghost" size="sm">Open</BrutalButton>}>
              <p className="text-sm text-on-surface-variant">Members, invitations, roles and permissions.</p>
              <div className="mt-4 flex gap-2">
                <BrutalButton href="/settings/members" variant="default" size="sm">Members</BrutalButton>
                <BrutalButton href="/settings/roles" variant="default" size="sm">Roles</BrutalButton>
              </div>
            </BrutalCard>
            <BrutalCard eyebrow="Workspace" title="Workspaces" actions={<BrutalButton href="/settings/workspaces" variant="ghost" size="sm">Open</BrutalButton>}>
              <p className="text-sm text-on-surface-variant">Workspace list, creation and membership.</p>
              <div className="mt-4">
                <BrutalButton href="/settings/workspaces" variant="default" size="sm">Manage workspaces</BrutalButton>
              </div>
            </BrutalCard>
          </div>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
