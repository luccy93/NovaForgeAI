"use client";

import { useEffect, useState } from "react";
import { Protected } from "@/components/auth/Protected";
import { AppShell } from "@/components/layout/AppShell";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { KnowledgeWorkspace } from "@/components/knowledge/KnowledgeWorkspace";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import { handleSessionExpired, useAuthStore } from "@/stores/auth";
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
          handleSessionExpired();
        }
      });
    return () => {
      active = false;
    };
  }, []);

  function logout() {
    useAuthStore.getState().logout();
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
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h1 className="font-mono text-xs uppercase tracking-widest text-primary-container">
                Knowledge
              </h1>
              <p className="text-sm text-on-surface-variant">
                {email ?? "Authenticated"} {workspaceId ? `· ${wsLabel}` : ""}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <BrutalButton variant="ghost" size="sm" href="/knowledge/universal">
                Universal search
              </BrutalButton>
              <BrutalButton variant="ghost" size="sm" href="/knowledge/graph">
                Knowledge graph
              </BrutalButton>
            </div>
          </div>
        </div>
        <div className="mx-auto flex h-[calc(100vh-8.5rem)] w-full max-w-[1600px] flex-col px-0">
          <KnowledgeWorkspace />
        </div>
      </AppShell>
    </Protected>
  );
}