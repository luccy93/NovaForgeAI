"use client";

/* eslint-disable react-hooks/set-state-in-effect -- authoritative backend profile load on mount and context switch */

import { useCallback, useEffect, useRef, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { Protected } from "@/components/auth/Protected";
import { PreferencesWorkspace } from "@/components/settings/PreferencesWorkspace";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import { getToken, api } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { ApiUser, WhoAmI } from "@/types/api";

export default function PreferencesPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);
  const workspaceName = useTenantStore((s) => s.workspaceName);

  const [me, setMe] = useState<ApiUser | null>(null);
  const [whoami, setWhoami] = useState<WhoAmI | null>(null);
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
    (async () => {
      try {
        const [m, w] = await Promise.all([
          api.me(token),
          api.whoami(token).catch((e) => {
            if (e instanceof ApiError && e.kind === "unauthorized") throw e;
            return null;
          }),
        ]);
        if (seq !== seqRef.current || controller.signal.aborted) return;
        setMe(m);
        setWhoami(w as WhoAmI | null);
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
          title="Preferences"
          description="Your NovaForge experience and supported personalization capabilities."
          crumbs={[{ label: "Home", href: "/" }, { label: "Settings", href: "/settings" }, { label: "Preferences" }]}
        >
          <PreferencesWorkspace
            me={me}
            whoami={whoami}
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