"use client";

import Link from "next/link";
import { Menu, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";
import { OrgSwitcher } from "@/components/layout/OrgSwitcher";
import { WorkspaceSwitcher } from "@/components/layout/WorkspaceSwitcher";
import { useCommandCenter } from "@/components/navigation/CommandCenterProvider";
import { NotificationBell } from "@/components/notifications/NotificationBell";

export function TopHeader({
  email,
  workspaceLabel,
  onMenu,
  onLogout,
}: {
  email: string | null;
  workspaceLabel: string | null;
  onMenu: () => void;
  onLogout: () => void;
}) {
  const { open: openPalette } = useCommandCenter();

  return (
    <header className="flex min-h-16 flex-wrap items-center gap-2 border-b border-outline bg-surface px-3 py-2 sm:px-4 lg:px-6 sm:gap-3">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="border border-outline p-2 text-on-surface hover:border-primary-container lg:hidden min-h-[44px] min-w-[44px] flex items-center justify-center"
      >
        <Menu className="h-4 w-4" />
      </button>
      <Link href={email ? "/dashboard" : "/"} aria-label="NovaForge home" className="flex min-w-0 items-center gap-2">
        <span className="flex h-8 w-8 shrink-0 items-center justify-center bg-primary-container font-bold text-on-primary">
          NF
        </span>
        <span className="hidden font-bold tracking-widest text-on-surface sm:block truncate">NOVAFORGE</span>
      </Link>
      {email ? (
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2 sm:flex-nowrap">
          <div className="flex min-w-0 flex-1 flex-wrap gap-2 sm:flex-nowrap">
            <OrgSwitcher />
            <WorkspaceSwitcher />
          </div>
          <div className="hidden flex-1 sm:block" />
        </div>
      ) : workspaceLabel ? (
        <span className="hidden max-w-[160px] truncate border border-outline px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant sm:block" title={workspaceLabel}>
          {workspaceLabel}
        </span>
      ) : (
        <div className="flex-1" />
      )}
      {email ? (
        <div className="flex shrink-0 items-center gap-2">
          <button
            type="button"
            onClick={openPalette}
            aria-label="Search"
            className="border border-outline p-2 text-on-surface-variant hover:border-primary-container hover:text-on-surface min-h-[44px] min-w-[44px] flex items-center justify-center"
          >
            <Search className="h-4 w-4" />
          </button>
          <NotificationBell />
          <UserMenu email={email} onLogout={onLogout} />
        </div>
      ) : (
        <Link
          href="/auth/login"
          className="shrink-0 border border-primary-container bg-primary-container px-4 py-2 text-xs font-bold uppercase tracking-widest text-on-primary hover:bg-surface hover:text-primary-container"
        >
          Sign in
        </Link>
      )}
    </header>
  );
}