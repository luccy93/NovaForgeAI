"use client";

import { useEffect, useState } from "react";
import { getToken, api } from "@/lib/api";
import { useTenantStore } from "@/stores/tenant";
import { useToastStore } from "@/stores/toast";
import type { Organization } from "@/types/org";
import { ApiError } from "@/lib/api-client";

export function OrgSwitcher() {
  const organizationId = useTenantStore((s) => s.organizationId);
  const organizations = useTenantStore((s) => s.organizations);
  const setOrganizations = useTenantStore((s) => s.setOrganizations);
  const switchOrganization = useTenantStore((s) => s.switchOrganization);
  const setWorkspaces = useTenantStore((s) => s.setWorkspaces);
  const pushToast = useToastStore((s) => s.push);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const token = getToken();
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const orgs = await api.listMyOrganizations(token);
        if (cancelled) return;
        setOrganizations(orgs);
        // Auto-select first org if none selected
        if (!organizationId && orgs.length > 0) {
          switchOrganization(orgs[0].id);
          // Fetch workspaces for auto-selected
          try {
            const wss = await api.listWorkspaces(token, orgs[0].id);
            if (!cancelled) setWorkspaces(wss);
          } catch {}
        } else if (organizationId) {
          // Ensure workspaces loaded for current org
          try {
            const wss = await api.listWorkspaces(token, organizationId);
            if (!cancelled) setWorkspaces(wss);
          } catch {}
        }
      } catch (e) {
        if (e instanceof ApiError && e.kind === "unauthorized") {
          // handled by auth layer
        }
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const nextId = e.target.value || null;
    if (!nextId) {
      switchOrganization(null);
      setWorkspaces([]);
      return;
    }
    const token = getToken();
    if (!token) return;
    setLoading(true);
    try {
      // Verify backend authorization
      await api.getOrganization(token, nextId);
      switchOrganization(nextId);
      // Invalidate and reload workspaces
      const wss = await api.listWorkspaces(token, nextId);
      setWorkspaces(wss);
      pushToast("success", "Organization switched");
      // Broadcast for realtime & cache invalidation listeners
      window.dispatchEvent(new CustomEvent("tenant:switched", { detail: { previousOrg: organizationId, nextOrg: nextId } }));
    } catch (err) {
      pushToast("error", err instanceof Error ? err.message : "Failed to switch organization");
    } finally {
      setLoading(false);
    }
  }

  if (organizations.length === 0) return null;

  return (
    <select
      aria-label="Organization"
      value={organizationId ?? ""}
      onChange={handleChange}
      disabled={loading}
      className="hidden md:block border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface outline-none focus:border-primary-container disabled:opacity-50"
    >
      <option value="">Select org</option>
      {organizations.map((org) => (
        <option key={org.id} value={org.id}>
          {org.name} ({org.slug})
        </option>
      ))}
    </select>
  );
}
