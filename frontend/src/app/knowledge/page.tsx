"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { KnowledgeWorkspace } from "@/components/knowledge/KnowledgeWorkspace";
import { api, clearToken, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import type { ApiUser } from "@/types/api";

export default function KnowledgePage() {
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
        <div className="border-b border-outline bg-surface px-4 py-4 lg:px-6">
          <h1 className="font-mono text-xs uppercase tracking-widest text-primary-container">
            Knowledge
          </h1>
          <p className="text-sm text-on-surface-variant">
            {email ?? "Authenticated"} {workspaceId ? `· ${wsLabel}` : ""}
          </p>
        </div>
        <div className="mx-auto flex h-[calc(100vh-8.5rem)] w-full max-w-[1600px] flex-col px-0">
          <KnowledgeWorkspace />
        </div>
      </AppShell>
    </Protected>
  );
}