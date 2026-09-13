"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { PageFrame } from "@/components/layout/PageFrame";
import { ExecutiveAnalytics } from "@/components/analytics/ExecutiveAnalytics";
import { api, clearToken, getToken } from "@/lib/api";
import type { ApiUser } from "@/types/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";

export default function AnalyticsPage() {
  const [user, setUser] = useState<ApiUser | null>(null);
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let active = true;
    api
      .me(token)
      .then((me) => {
        if (active) setUser(me);
      })
      .catch((e) => {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          clearToken();
          window.location.href = "/auth/login";
        }
      });
    return () => {
      active = false;
    };
  }, []);

  function logout() {
    clearToken();
    window.location.href = "/";
  }

  const email = typeof user?.email === "string" ? user.email : null;
  const orgLabel = organizationId ? `Org ${organizationId.slice(0, 8)}` : null;
  const wsLabel = workspaceId ? `WS ${workspaceId.slice(0, 8)}` : email ? "Workspace" : null;

  return (
    <Protected>
      <AppShell
        email={email}
        workspaceLabel={wsLabel ?? orgLabel ?? (email ? "Workspace" : null)}
        onLogout={logout}
      >
        <PageFrame
          eyebrow="EXECUTIVE ANALYTICS"
          title="Analytics"
          description="Organization-level engineering, AI, operations, security, governance, data, FinOps and platform performance aggregated from verified backend sources. Domain workspaces remain authoritative."
          crumbs={[{ label: "Analytics" }]}
        >
          <ExecutiveAnalytics />
        </PageFrame>
      </AppShell>
    </Protected>
  );
}
