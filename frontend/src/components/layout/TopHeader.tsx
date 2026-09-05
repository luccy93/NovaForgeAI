"use client";

import Link from "next/link";
import { Menu, Search } from "lucide-react";
import { UserMenu } from "@/components/layout/UserMenu";

export function TopHeader({
  email,
  workspaceLabel,
  onMenu,
  onLogout,
  onOpenPalette,
  onOpenSearch,
}: {
  email: string | null;
  workspaceLabel: string | null;
  onMenu: () => void;
  onLogout: () => void;
  onOpenPalette?: () => void;
  onOpenSearch?: () => void;
}) {
  return (
    <header className="flex h-16 items-center gap-3 border-b border-outline bg-surface px-4 lg:px-6">
      <button
        type="button"
        onClick={onMenu}
        aria-label="Open navigation"
        className="border border-outline p-2 text-on-surface hover:border-primary-container lg:hidden"
      >
        <Menu className="h-4 w-4" />
      </button>
      <Link href={email ? "/dashboard" : "/"} aria-label="NovaForge home" className="flex items-center gap-2">
        <span className="flex h-8 w-8 items-center justify-center bg-primary-container font-bold text-black">
          NF
        </span>
        <span className="hidden font-bold tracking-widest text-on-surface sm:block">NOVAFORGE</span>
      </Link>
      {workspaceLabel ? (
        <span className="hidden border border-outline px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant md:block">
          {workspaceLabel}
        </span>
      ) : null}
      <div className="flex-1" />
      {onOpenSearch ? (
        <button
          type="button"
          onClick={onOpenSearch}
          aria-label="Search"
          className="hidden border border-outline p-2 text-on-surface-variant hover:border-primary-container hover:text-on-surface sm:block"
        >
          <Search className="h-4 w-4" />
        </button>
      ) : null}
      {email ? (
        <UserMenu email={email} onLogout={onLogout} onOpenPalette={onOpenPalette} />
      ) : (
        <Link
          href="/auth/login"
          className="border border-primary-container bg-primary-container px-4 py-2 text-xs font-bold uppercase tracking-widest text-black hover:bg-black hover:text-primary-container"
        >
          Sign in
        </Link>
      )}
    </header>
  );
}
