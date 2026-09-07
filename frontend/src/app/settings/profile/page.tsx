"use client";

import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { useAuthStore } from "@/stores/auth";
import { getToken } from "@/lib/api";
import { api } from "@/lib/api";
import type { ApiUser, WhoAmI } from "@/types/api";
import { ApiError } from "@/lib/api-client";

export default function ProfilePage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const [me, setMe] = useState<ApiUser | null>(null);
  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    (async () => {
      try {
        const [m, w] = await Promise.all([api.me(token), api.whoami(token).catch(() => null)]);
        setMe(m);
        if (w) setWhoami(w as WhoAmI);
      } catch (e) {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          useAuthStore.getState().markExpired();
        } else {
          setError(e instanceof Error ? e.message : "Failed to load profile");
        }
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const email = me?.email ?? user?.email ?? null;

  const handleLogout = () => {
    logout("Signed out");
    window.location.href = "/auth/login";
  };

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={whoami?.organizations?.[0] ? "Workspace" : null} onLogout={handleLogout}>
        <PageFrame
          eyebrow="Settings"
          title="Profile"
          description="Your NovaForge identity and account metadata."
          crumbs={[{ label: "Home", href: "/" }, { label: "Settings", href: "/settings/profile" }, { label: "Profile" }]}
        >
          {error ? <div className="mb-6"><BrutalErrorState description={error} onRetry={() => window.location.reload()} /></div> : null}
          <div className="grid gap-6 md:grid-cols-2">
            <BrutalCard eyebrow="Identity" title={me?.username ?? user?.username ?? "—"}>
              {loading ? <BrutalSkeleton className="h-32" /> : me ? (
                <dl className="space-y-3 text-sm">
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">User ID</dt><dd className="font-mono text-on-surface break-all">{me.id}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Email</dt><dd className="text-on-surface">{me.email}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Username</dt><dd className="text-on-surface">{me.username}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Full name</dt><dd className="text-on-surface">{me.full_name || "—"}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Status</dt><dd><BrutalBadge tone={me.is_active ? "yellow" : "error"}>{me.is_active ? "Active" : "Inactive"}</BrutalBadge></dd></div>
                </dl>
              ) : (
                <p className="text-on-surface-variant">No profile data.</p>
              )}
            </BrutalCard>
            <BrutalCard eyebrow="Membership" title="Organizations & permissions">
              {loading ? <BrutalSkeleton className="h-32" /> : whoami ? (
                <div className="space-y-3 text-sm">
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">MFA</dt><dd><BrutalBadge tone={whoami.mfa_enabled ? "yellow" : "muted"}>{whoami.mfa_enabled ? "Enabled" : "Disabled"}</BrutalBadge></dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Superuser</dt><dd className="text-on-surface">{whoami.is_superuser ? "Yes" : "No"}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Organizations</dt><dd className="text-on-surface">{whoami.organizations.length ? whoami.organizations.map((o) => `${o.organization_id.slice(0, 8)} (${o.role})`).join(", ") : "—"}</dd></div>
                  <div><dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Permissions</dt><dd className="font-mono text-xs text-on-surface break-words">{whoami.permissions.slice(0, 8).join(", ") || "—"}</dd></div>
                </div>
              ) : (
                <p className="text-on-surface-variant">Membership details unavailable.</p>
              )}
            </BrutalCard>
          </div>
          <div className="mt-6">
            <BrutalCard eyebrow="Security" title="Manage your account">
              <p className="text-sm text-on-surface-variant">Update password, review sessions and manage two-factor authentication in <a href="/settings/security" className="text-primary-container underline">Security settings</a>.</p>
            </BrutalCard>
          </div>
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
