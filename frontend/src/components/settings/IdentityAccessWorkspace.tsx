"use client";

import type { ReactNode } from "react";
import { BrutalBadge } from "@/components/ui/BrutalBadge";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalCard } from "@/components/ui/BrutalCard";
import { BrutalEmptyState } from "@/components/ui/BrutalEmptyState";
import { BrutalErrorState } from "@/components/ui/BrutalErrorState";
import { BrutalSkeleton } from "@/components/ui/BrutalSkeleton";
import type { ApiUser, WhoAmI, SessionOut, ApiKeyOut } from "@/types/api";
import type { Organization, Workspace, Role } from "@/types/org";
import type { ZeroTrustPosture, PrivilegedAccessItem, AccessRequestItem } from "@/types/security";
import type { ZeroTrustReview } from "@/types/admin";

export interface IdentityAccessWorkspaceProps {
  me: ApiUser | null;
  whoami: WhoAmI | null;
  sessions: SessionOut[] | null;
  apiKeys: ApiKeyOut[] | null;
  organizations: Organization[] | null;
  workspaces: Workspace[] | null;
  roles: Role[] | null;
  posture: ZeroTrustPosture | null;
  privilegedAccess: PrivilegedAccessItem[] | null;
  accessRequests: AccessRequestItem[] | null;
  reviews: ZeroTrustReview[] | null;
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

function objectFieldCount(value: unknown): number | null {
  if (value && typeof value === "object" && !Array.isArray(value)) return Object.keys(value as Record<string, unknown>).length;
  return null;
}

function shortId(value?: string | null): string {
  if (!value) return "—";
  return value.length > 12 ? `${value.slice(0, 8)}…` : value;
}

export function IdentityAccessWorkspace({
  me,
  whoami,
  sessions,
  apiKeys,
  organizations,
  workspaces,
  roles,
  posture,
  privilegedAccess,
  accessRequests,
  reviews,
  loading,
  error,
  onRetry,
  organizationId,
  workspaceId,
  workspaceName,
}: IdentityAccessWorkspaceProps) {
  if (loading) {
    return (
      <SectionGrid>
        <BrutalSkeleton className="h-44 md:col-span-2" />
        <BrutalSkeleton className="h-44" />
        <BrutalSkeleton className="h-44" />
        <BrutalSkeleton className="h-44" />
        <BrutalSkeleton className="h-44" />
      </SectionGrid>
    );
  }

  if (!me && !error) {
    return (
      <BrutalEmptyState
        title="No identity data."
        description="Identity and access visibility is read from the backend. Nothing is stored in the browser."
      />
    );
  }

  const mfaStatus = whoami ? (whoami.mfa_enabled ? "Enabled" : "Disabled") : "Unknown";
  const mfaTone = whoami?.mfa_enabled ? "yellow" : "muted";
  const sessionsCount = sessions ? String(sessions.length) : "—";
  const apiKeysCount = apiKeys ? String(apiKeys.length) : "—";
  const orgsCount = organizations ? String(organizations.length) : "—";
  const wsCount = workspaces ? String(workspaces.length) : "—";
  const rolesCount = roles ? String(roles.length) : "—";
  const privilegedCount = privilegedAccess ? String(privilegedAccess.length) : "—";
  const requestsCount = accessRequests ? String(accessRequests.length) : "—";
  const reviewsCount = reviews ? String(reviews.length) : "—";

  return (
    <div className="space-y-6">
      {error ? <BrutalErrorState title="Could not load identity" description={error} onRetry={onRetry} /> : null}

      <div className="flex flex-wrap items-center gap-2 border border-outline bg-surface-container px-4 py-3">
        <span className="inline-flex items-center gap-2 border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
          <span className="h-2 w-2 bg-muted" aria-hidden="true" />
          Realtime: UNAVAILABLE
        </span>
        <span className="font-mono text-xs uppercase tracking-widest text-on-surface-variant">
          Tenant-scoped · server-authoritative
        </span>
      </div>

      <BrutalCard eyebrow="Overview" title="Identity & Access">
        <dl className="grid gap-x-6 gap-y-1 md:grid-cols-2">
          <Row label="Identity">{me ? (me.full_name?.trim() ? me.full_name : me.email) : "—"}</Row>
          <Row label="Organization">{organizations?.[0]?.name ?? organizationId?.slice(0, 8) ?? "—"}</Row>
          <Row label="Workspace">{workspaceName ?? organizationId ?? "—"}</Row>
          <Row label="Authentication">{mfaStatus}</Row>
          <Row label="Sessions">{sessionsCount}</Row>
          <Row label="Access">{whoami?.permissions?.length ? `${whoami.permissions.length} permissions` : "—"}</Row>
          <Row label="Privileged access">{privilegedCount}</Row>
        </dl>
        <p className="mt-4 text-sm text-on-surface-variant">
          This page is read-only. Identity and access information is server-authoritative. No identity controls are persisted
          from this workspace.
        </p>
      </BrutalCard>

      <SectionGrid>
        <BrutalCard eyebrow="Backend-authoritative · GET /auth/me" title="Identity">
          <div className="mb-3">
            <BrutalBadge tone={me?.is_active ? "yellow" : "error"}>{me?.is_active ? "Active" : "Inactive"}</BrutalBadge>
          </div>
          <dl>
            <Row label="User ID">{me ? <span className="break-all font-mono text-xs">{me.id}</span> : "—"}</Row>
            <Row label="Email">{me?.email ?? "—"}</Row>
            <Row label="Username">{me?.username ?? "—"}</Row>
            <Row label="Full name">{me?.full_name || "—"}</Row>
            <Row label="Superuser">{whoami ? (whoami.is_superuser ? "Yes" : "No") : "—"}</Row>
            <Row label="Auth method">{whoami?.auth_method ?? "—"}</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            Tokens, password hashes and secrets are never shown. Authorization is enforced server-side.
          </p>
          <div className="mt-4 flex gap-2">
            <BrutalButton href="/settings/profile" variant="default" size="sm">
              Profile
            </BrutalButton>
            <BrutalButton href="/settings/organization" variant="default" size="sm">
              Organization
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Verified backend" title="Authentication">
          <div className="mb-3">
            <BrutalBadge tone={mfaTone as "yellow" | "muted"}>{mfaStatus}</BrutalBadge>
          </div>
          <dl>
            <Row label="MFA status">{mfaStatus}</Row>
            <Row label="MFA required">Unknown</Row>
            <Row label="Auth method">{whoami?.auth_method ?? "—"}</Row>
            <Row label="Policy">NOT EXPOSED BY API</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">
            MFA configuration and authentication policies are managed through the canonical security settings.
          </p>
          <div className="mt-4">
            <BrutalButton href="/settings/security" variant="default" size="sm">
              View session security
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Canonical · /settings/security" title="Sessions">
          <dl>
            <Row label="Active sessions">{sessionsCount}</Row>
            <Row label="Current session">{sessions?.find((s) => s.is_current)?.id ? shortId(sessions.find((s) => s.is_current)!.id) : "—"}</Row>
            <Row label="Revocation">Managed in security settings</Row>
          </dl>
          {sessions && sessions.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {sessions.slice(0, 3).map((s) => (
                <li key={s.id} className="border border-outline-variant bg-surface px-3 py-2 font-mono text-xs text-on-surface-variant">
                  <span className="font-bold text-on-surface">{shortId(s.id)}</span> · {s.ip_address ?? "unknown IP"} · {s.is_current ? "current" : "active"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-on-surface-variant">No session preview available.</p>
          )}
          <div className="mt-4">
            <BrutalButton href="/settings/security" variant="default" size="sm">
              View session security
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Canonical · /settings/security" title="API Keys">
          <dl>
            <Row label="API keys">{apiKeysCount}</Row>
            <Row label="Active keys">{apiKeys ? String(apiKeys.filter((k) => k.is_active).length) : "—"}</Row>
            <Row label="Secret material">Never shown</Row>
          </dl>
          {apiKeys && apiKeys.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {apiKeys.slice(0, 3).map((k) => (
                <li key={k.id} className="border border-outline-variant bg-surface px-3 py-2 font-mono text-xs text-on-surface-variant">
                  <span className="font-bold text-on-surface">{k.name}</span> · {k.key_prefix} · {k.is_active ? "active" : "inactive"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-on-surface-variant">No API key preview available.</p>
          )}
          <p className="mt-2 text-xs text-on-surface-variant">Only key metadata is shown. Secret values are never shown, stored, logged, or linked.</p>
          <div className="mt-4">
            <BrutalButton href="/settings/security" variant="default" size="sm">
              Manage API Keys
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Tenant-scoped" title="Organization Access">
          <dl>
            <Row label="Organizations">{orgsCount}</Row>
            <Row label="Workspaces">{wsCount}</Row>
            <Row label="Roles">{rolesCount}</Row>
            <Row label="Current org">{organizationId ? organizationId.slice(0, 8) : "—"}</Row>
            <Row label="Current workspace">{workspaceName ?? workspaceId?.slice(0, 8) ?? "—"}</Row>
          </dl>
          <p className="mt-4 text-sm text-on-surface-variant">Organization administration remains in its canonical settings pages.</p>
          <div className="mt-4 flex flex-wrap gap-2">
            <BrutalButton href="/settings/members" variant="default" size="sm">
              Manage Members
            </BrutalButton>
            <BrutalButton href="/settings/roles" variant="default" size="sm">
              Manage Roles
            </BrutalButton>
            <BrutalButton href="/settings/workspaces" variant="default" size="sm">
              Manage Workspaces
            </BrutalButton>
            <BrutalButton href="/settings/organization" variant="default" size="sm">
              Organization
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="NOT EXPOSED BY API" title="SSO / Identity Providers">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">
            Enterprise identity-provider configuration is not currently available through the verified backend interface.
          </p>
          <p className="mt-2 text-xs text-on-surface-variant">
            SAML, OIDC and OAuth provider registry exists in the backend but has no verified frontend wrapper in this phase.
          </p>
        </BrutalCard>

        <BrutalCard eyebrow="NOT EXPOSED BY API" title="SCIM / Directory Provisioning">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">SCIM directory provisioning is not currently available through the verified backend interface.</p>
          <p className="mt-2 text-xs text-on-surface-variant">Directory sync is in-memory only and not exposed as a durable frontend capability.</p>
        </BrutalCard>

        <BrutalCard eyebrow="NOT EXPOSED BY API" title="Service Accounts">
          <div className="mb-3">
            <BrutalBadge tone="muted">NOT EXPOSED BY API</BrutalBadge>
          </div>
          <p className="text-sm text-on-surface-variant">Service account management is not currently available through the verified backend interface.</p>
          <p className="mt-2 text-xs text-on-surface-variant">Backend supports service accounts but no verified frontend wrapper is included in this phase.</p>
        </BrutalCard>

        <BrutalCard eyebrow="Zero Trust · GET /zero-trust/posture" title="Access Posture">
          <dl>
            <Row label="Identity fields">{posture ? (objectFieldCount(posture.identity) ?? "—") : "—"}</Row>
            <Row label="Access fields">{posture ? (objectFieldCount(posture.access) ?? "—") : "—"}</Row>
            <Row label="Machine fields">{posture ? (objectFieldCount(posture.machine) ?? "—") : "—"}</Row>
            <Row label="Posture source">Backend verbatim</Row>
          </dl>
          {posture ? (
            <p className="mt-4 font-mono text-xs text-on-surface-variant">No security score is calculated here. Values are backend-reported only.</p>
          ) : (
            <p className="mt-4 text-sm text-on-surface-variant">No posture was returned. This is not an error — the backend may not expose posture for this tenant.</p>
          )}
          <div className="mt-4">
            <BrutalButton href="/security" variant="default" size="sm">
              Open Security workspace
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Zero Trust · privileged-access" title="Privileged Access">
          <dl>
            <Row label="Privileged items">{privilegedCount}</Row>
            <Row label="Source">GET /zero-trust/privileged-access</Row>
          </dl>
          {privilegedAccess && privilegedAccess.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {privilegedAccess.slice(0, 3).map((item) => (
                <li key={item.id} className="border border-outline-variant bg-surface px-3 py-2 text-xs text-on-surface-variant">
                  <span className="font-mono font-bold text-on-surface">{item.identity ?? shortId(item.id)}</span> · {item.resource ?? "—"} ·{" "}
                  <BrutalBadge tone="yellow">{item.privilege_level ?? "—"}</BrutalBadge> · {item.status ?? "—"}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-4 text-sm text-on-surface-variant">No privileged access was returned.</p>
          )}
          <div className="mt-4">
            <BrutalButton href="/admin" variant="default" size="sm">
              Open Admin control plane
            </BrutalButton>
          </div>
        </BrutalCard>

        <BrutalCard eyebrow="Zero Trust · access-requests · reviews" title="Access Reviews">
          <dl>
            <Row label="Access requests">{requestsCount}</Row>
            <Row label="Reviews">{reviewsCount}</Row>
            <Row label="Approval">zero_trust:write (server-enforced)</Row>
          </dl>
          {accessRequests && accessRequests.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {accessRequests.slice(0, 2).map((r) => (
                <li key={r.id} className="border border-outline-variant bg-surface px-3 py-2 font-mono text-xs text-on-surface-variant">
                  <span className="font-bold text-on-surface">{r.identity ?? shortId(r.id)}</span> · {r.action ?? "access"} · {r.status ?? "—"}
                </li>
              ))}
            </ul>
          ) : null}
          {reviews && reviews.length > 0 ? (
            <ul className="mt-4 space-y-2">
              {reviews.slice(0, 2).map((r) => (
                <li key={r.id} className="border border-outline-variant bg-surface px-3 py-2 font-mono text-xs text-on-surface-variant">
                  {shortId(r.id)} · {r.review_type ?? "review"} · {r.status ?? "—"}
                </li>
              ))}
            </ul>
          ) : null}
          {(!accessRequests || accessRequests.length === 0) && (!reviews || reviews.length === 0) ? (
            <p className="mt-4 text-sm text-on-surface-variant">No access requests or reviews were returned.</p>
          ) : null}
          <div className="mt-4 flex gap-2">
            <BrutalButton href="/admin" variant="default" size="sm">
              View access reviews
            </BrutalButton>
            <BrutalButton href="/security" variant="default" size="sm">
              Security
            </BrutalButton>
          </div>
        </BrutalCard>
      </SectionGrid>

      <div className="border border-outline bg-surface-container px-4 py-3 font-mono text-xs uppercase tracking-widest text-on-surface-variant">
        Identity provider health is not exposed by the backend. No uptime or connectivity status is shown.
      </div>
    </div>
  );
}
