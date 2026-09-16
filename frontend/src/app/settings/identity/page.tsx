"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative backend identity load on mount and context switch */

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { IdentityAccessWorkspace } from "@/components/settings/IdentityAccessWorkspace";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { getToken, api } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { ApiUser, WhoAmI, SessionOut, ApiKeyOut } from "@/types/api";
import type { Organization, Workspace, Role } from "@/types/org";
import type { ZeroTrustPosture, PrivilegedAccessItem, AccessRequestItem } from "@/types/security";
import type { ZeroTrustReview } from "@/types/admin";

export default function IdentityPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);
  const workspaceName = useTenantStore((s) => s.workspaceName);

  const [me, setMe] = useState<ApiUser | null>(null);
  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
  const [sessions, setSessions] = useState<SessionOut[] | null>(null);
  const [apiKeys, setApiKeys] = useState<ApiKeyOut[] | null>(null);
  const [organizations, setOrganizations] = useState<Organization[] | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[] | null>(null);
  const [roles, setRoles] = useState<Role[] | null>(null);
  const [posture, setPosture] = useState<ZeroTrustPosture | null>(null);
  const [privilegedAccess, setPrivilegedAccess] = useState<PrivilegedAccessItem[] | null>(null);
  const [accessRequests, setAccessRequests] = useState<AccessRequestItem[] | null>(null);
  const [reviews, setReviews] = useState<ZeroTrustReview[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const seqRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const load = useCallback(() => {
    const token = getToken();
    if (!token) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const seq = ++seqRef.current;
    setLoading(true);
    setError(null);

    function safe<T>(promise: Promise<T>): Promise<T | null> {
      return promise.catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") throw e;
        return null;
      });
    }

    (async () => {
      try {
        const currentOrg = useTenantStore.getState().organizationId;
        const [m, w, s, k, orgs, ws, r, p, pa, ar, rev] = await Promise.all([
          api.me(token),
          safe(api.whoami(token)) as Promise<WhoAmI | null>,
          safe(api.listSessions(token)) as Promise<SessionOut[] | null>,
          safe(api.listApiKeys(token)) as Promise<ApiKeyOut[] | null>,
          safe(api.listMyOrganizations(token)) as Promise<Organization[] | null>,
          currentOrg ? (safe(api.listWorkspaces(token, currentOrg)) as Promise<Workspace[] | null>) : Promise.resolve(null),
          currentOrg ? (safe(api.listRoles(token, currentOrg)) as Promise<Role[] | null>) : Promise.resolve(null),
          safe(api.zeroTrustPosture(token)) as Promise<ZeroTrustPosture | null>,
          safe(api.zeroTrustPrivilegedAccess(token, { limit: 20 }).then((v) => (Array.isArray(v?.items) ? v.items : []))) as Promise<PrivilegedAccessItem[] | null>,
          safe(api.zeroTrustAccessRequests(token, { limit: 20 }).then((v) => (Array.isArray(v?.items) ? v.items : []))) as Promise<AccessRequestItem[] | null>,
          safe(api.zeroTrustReviews(token, { limit: 20 }).then((v) => (Array.isArray(v?.items) ? v.items : []))) as Promise<ZeroTrustReview[] | null>,
        ]);

        if (seq !== seqRef.current || controller.signal.aborted) return;
        setMe(m);
        setWhoami(w);
        setSessions(s);
        setApiKeys(k);
        setOrganizations(orgs);
        setWorkspaces(ws);
        setRoles(r);
        setPosture(p);
        setPrivilegedAccess(pa);
        setAccessRequests(ar);
        setReviews(rev);
      } catch (e) {
        if (seq !== seqRef.current || controller.signal.aborted) return;
        if (e instanceof ApiError) {
          if (e.kind === "unauthorized") {
            useAuthStore.getState().markExpired();
            return;
          }
          if (e.kind === "forbidden") {
            setError("Backend denied access: additional authorization is required for your role.");
          } else if (e.status === 404) {
            setError("Not found on the backend.");
          } else if (e.status === 409) {
            setError("Changed on the server — use Refresh to reload.");
          } else if (e.kind === "validation") {
            setError("Backend rejected the request.");
          } else if (e.kind === "server" || (e.status >= 500 && e.status < 600)) {
            setError("Identity services temporarily unavailable");
          } else {
            setError(e.message || "Unavailable");
          }
        } else {
          setError(e instanceof Error ? e.message : "Unavailable");
        }
      } finally {
        if (seq === seqRef.current) setLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    load();
    return () => abortRef.current?.abort();
  }, [load]);

  useEffect(() => {
    function onSwitch() {
      seqRef.current += 1;
      abortRef.current?.abort();
      load();
    }
    window.addEventListener("tenant:switched", onSwitch);
    window.addEventListener("workspace:switched", onSwitch);
    return () => {
      window.removeEventListener("tenant:switched", onSwitch);
      window.removeEventListener("workspace:switched", onSwitch);
    };
  }, [load]);

  const email = me?.email ?? user?.email ?? null;

  const handleLogout = () => {
    logout("Signed out");
    window.location.href = "/auth/login";
  };

  return (
    <Protected>
      <AppShell email={email} workspaceLabel={null} onLogout={handleLogout}>
        <PageFrame
          eyebrow="Settings"
          title="Identity & Access"
          description="Verified identity, authentication and enterprise access visibility. Server-authoritative and tenant-scoped."
          crumbs={[{ label: "Home", href: "/" }, { label: "Settings", href: "/settings" }, { label: "Identity & Access" }]}
        >
          <IdentityAccessWorkspace
            me={me}
            whoami={whoami}
            sessions={sessions}
            apiKeys={apiKeys}
            organizations={organizations}
            workspaces={workspaces}
            roles={roles}
            posture={posture}
            privilegedAccess={privilegedAccess}
            accessRequests={accessRequests}
            reviews={reviews}
            loading={loading}
            error={error}
            onRetry={load}
            organizationId={organizationId}
            workspaceId={workspaceId}
            workspaceName={workspaceName}
          />
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
