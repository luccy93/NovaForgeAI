"use client";

import { useToastStore } from "@/stores/toast";
import { useTenantStore } from "@/stores/tenant";

export function WorkspaceSwitcher() {
  const organizationId = useTenantStore((s) => s.organizationId);
  const workspaceId = useTenantStore((s) => s.workspaceId);
  const workspaces = useTenantStore((s) => s.workspaces);
  const switchWorkspace = useTenantStore((s) => s.switchWorkspace);
  const pushToast = useToastStore((s) => s.push);

  if (!organizationId) return null;
  if (workspaces.length === 0) {
    return (
      <span className="block max-w-[140px] truncate border border-outline px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant sm:max-w-[180px]">
        No workspaces
      </span>
    );
  }

  function handleChange(e: React.ChangeEvent<HTMLSelectElement>) {
    const nextId = e.target.value || null;
    const ws = workspaces.find((w) => w.id === nextId);
    switchWorkspace(nextId, ws?.name ?? null);
    pushToast("info", nextId ? `Workspace: ${ws?.name ?? nextId.slice(0, 8)}` : "Workspace cleared");
  }

  return (
    <select
      aria-label="Workspace"
      value={workspaceId ?? ""}
      onChange={handleChange}
      className="block w-full min-w-0 max-w-[140px] truncate border border-outline bg-surface px-2 py-1 font-mono text-xs uppercase tracking-widest text-on-surface outline-none focus:border-primary-container sm:w-auto sm:max-w-[180px]"
    >
      <option value="">Select workspace</option>
      {workspaces.map((ws) => (
        <option key={ws.id} value={ws.id}>
          {ws.name}
        </option>
      ))}
    </select>
  );
}
