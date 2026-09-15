"use client";

import type { ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import { NAV_GROUPS, filterNavByPermission, visibleNavItems } from "@/lib/navigation";
import type { ApiUser, WhoAmI } from "@/types/api";

export interface PreferencesWorkspaceProps {
  me: ApiUser | null;
  whoami: WhoAmI | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  organizationId: string | null;
  workspaceId: string | null;
  workspaceName: string | null;
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-outline-variant py-2 last:border-b-0">
      <dt className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">{label}</dt>
      <dd className="text-right text-sm font-bold text-on-surface">{children}</dd>
    </div>
  );
}

function SectionGrid({ children }: { children: ReactNode }) {
  return <div className="grid gap-6 md:grid-cols-2">{children}</div>;
}

export function PreferencesWorkspace({
  me,
  whoami,
  loading,
  error,
  onRetry,
  organizationId,
  workspaceId,
  workspaceName,
}: PreferencesWorkspaceProps) {
  const filteredItems = filterNavByPermission(visibleNavItems(true), whoami?.permissions ?? null);
  const filteredGroups = NAV_GROUPS.map(({ id, label }) => ({
    id,
    label,
    items: filteredItems.filter((item) => item.group === id),
  })).filter((group) => group.items.length > 0);

  if (loading) {
    return (
      <SectionGrid>
        <BrutalSkeleton className="h-44 md:col-span-2" />
        <BrutalSkeleton className="h-44" />
        <BrutalSkeleton className="h-44" />
      </SectionGrid>
    );
  }

  if (!me && !error) {
    return (
      <BrutalEmptyState
        title="No preferences data."
        description="Personalization is read from the backend. Nothing is stored in the browser."
      />
    );
  }

  return (
    <div className="space-y-6">
      {error ? (
        <BrutalErrorState title="Could not load preferences" description={error} onRetry={onRetry} />
      ) : null}

      <BrutalCard eyebrow="Overview" title="User Experience">
        <dl className="grid gap-x-6 gap-y-1 md:grid-cols-2">
          <Row label="Profile">{me ? (me.full_name?.trim() ? me.full_name : me.email) : "—"}</Row>
          <Row label="Appearance">Dark</Row>
          <Row label="Workspace">{workspaceName ?? organizationId ?? "—"}</Row>
          <Row label="Dashboard">Fixed</Row>
          <Row label="Navigation">Permission-controlled</Row>
          <Row label="AI Experience">Not available</Row>
          <Row label="Accessibility">System automatic</Row>
        </dl>
        <p className="mt-4 text-sm text-on-surface-variant">
          This page is read-only. No personalization preferences are persisted, and no preferences are
          stored in the browser.
        </p>
      </BrutalCard>

      <SectionGrid>
        <BrutalCard eyebrow="Backend-authoritative · GET /auth/me" title="Profile">
          <div className="mb-3">
            <BrutalBadge tone={me?.is_active ? "yellow" : "error"}>
              {me?.is_active ? "Active" : "Inactive"}
            </BrutalBadge>
          </div>
          <dl>
            <Row label="User ID">{me ? <span className="break-all font-mono text-xs">{me.id}</span> : "—"}</Row>
            <Row label="Email">{me?.email ?? "—"}</Row>
            <Row label="Username">{me?.username ?? "—"}</Row>
            <Row label="Full name">{me?.full_name || "—"}</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            Profile editing is not available — the backend does not expose a profile-update endpoint.
          </p>
          <div className="mt-4 flex gap-2">
            <BrutalButton href="/settings/profile" variant="default" size="sm">Profile settings</BrutalButton>
            <BrutalButton href="/settings/security" variant="default" size="sm">Security</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Platform-controlled" title="Appearance">
          <div className="mb-3">
            <BrutalBadge tone="default">Dark only</BrutalBadge>
          </div>
          <dl>
            <Row label="Theme">Dark</Row>
            <Row label="Theme switching">Not supported</Row>
            <Row label="System theme">Not supported</Row>
            <Row label="Custom themes">Not supported</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            NovaForge currently uses a dark enterprise interface. The browser reduced-motion preference is
            honored automatically.
          </p>
        </BrutalCard>

        <BrutalCard eyebrow="Current context" title="Workspace">
          <dl>
            <Row label="Current workspace">{workspaceName ?? "—"}</Row>
            <Row label="Workspace ID">
              {workspaceId ? <span className="font-mono text-xs">{workspaceId.slice(0, 8)}</span> : "—"}
            </Row>
            <Row label="Organization">
              {organizationId ? <span className="font-mono text-xs">{organizationId.slice(0, 8)}</span> : "—"}
            </Row>
            <Row label="Default landing">Not available</Row>
            <Row label="Default workspace">Not available</Row>
          </dl>
          <div className="mt-4">
            <BrutalButton href="/settings/workspaces" variant="default" size="sm">Manage workspaces</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Platform-controlled" title="Dashboard">
          <div className="mb-3">
            <BrutalBadge tone="default">Fixed</BrutalBadge>
          </div>
          <dl>
            <Row label="Layout">Fixed enterprise grid</Row>
            <Row label="Widget reordering">Not supported</Row>
            <Row label="Widget visibility">Not supported</Row>
            <Row label="Custom sections">Not supported</Row>
            <Row label="Persisted layout">Not available</Row>
          </dl>
          <div className="mt-4">
            <BrutalButton href="/dashboard" variant="default" size="sm">Open dashboard</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Platform-controlled" title="Navigation">
          <div className="mb-3">
            <BrutalBadge tone={whoami ? "yellow" : "muted"}>
              {whoami ? "Permission filtering active" : "Permission filter · unknown"}
            </BrutalBadge>
          </div>
          <dl>
            <Row label="Sidebar">Fixed desktop layout</Row>
            <Row label="Custom order">Not supported</Row>
            <Row label="Pin / hide">Not supported</Row>
            <Row label="Collapse">Not supported</Row>
            <Row label="Visible groups">{filteredGroups.length}</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            Your navigation is automatically filtered according to your permissions. Personalization cannot
            circumvent authorization.
          </p>
          <div className="mt-4">
            <p className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">Preview</p>
            <p className="mt-1 text-sm text-on-surface">
              {filteredGroups.map((group) => group.label).join(" · ") || "—"}
            </p>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Backend unavailable" title="AI Experience">
          <div className="mb-3">
            <BrutalBadge tone="muted">Not available</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">
            AI PERSONALIZATION — Backend preference controls are not exposed. Model selection and assistant
            behavior are governed by the workspace, not stored per user.
          </p>
          <div className="mt-4">
            <BrutalButton href="/ai" variant="default" size="sm">Open AI workspace</BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Platform-supported" title="Accessibility">
          <div className="mb-3">
            <BrutalBadge tone="muted">System</BrutalBadge>
          </div>
          <dl>
            <Row label="Reduced motion">System preference · automatic</Row>
            <Row label="Contrast">Fixed dark palette</Row>
            <Row label="Density">Fixed</Row>
            <Row label="Keyboard">Supported across controls</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            Accessibility preference controls are not currently available. Existing keyboard and
            reduced-motion behavior is preserved.
          </p>
        </BrutalCard>

        <BrutalCard eyebrow="Separate workspace" title="Notifications">
          <p className="text-sm text-on-surface-variant">
            Notification delivery preferences are managed in the dedicated notifications workspace.
          </p>
          <div className="mt-4">
            <BrutalButton href="/notifications" variant="default" size="sm">
              Manage notification preferences
            </BrutalButton>
          </div>
        </BrutalCard>
      </SectionGrid>
    </div>
  );
}