"use client";

import { type ReactNode, useState } from "react";
import { BrutalDrawer } from "@/components/ui/BrutalDrawer";
import { SideNav } from "@/components/layout/SideNav";
import { TopHeader } from "@/components/layout/TopHeader";

export function AppShell({
  email,
  workspaceLabel,
  onLogout,
  onOpenPalette,
  onOpenSearch,
  children,
}: {
  email: string | null;
  workspaceLabel: string | null;
  onLogout: () => void;
  onOpenPalette?: () => void;
  onOpenSearch?: () => void;
  children: ReactNode;
}) {
  const [navOpen, setNavOpen] = useState(false);
  const authenticated = email !== null;

  return (
    <div className="flex min-h-screen flex-col bg-surface text-on-surface">
      <TopHeader
        email={email}
        workspaceLabel={workspaceLabel}
        onMenu={() => setNavOpen(true)}
        onLogout={onLogout}
        onOpenPalette={onOpenPalette}
        onOpenSearch={onOpenSearch}
      />
      <div className="flex flex-1">
        <aside className="hidden w-60 shrink-0 border-r border-outline bg-surface p-4 lg:block">
          <SideNav authenticated={authenticated} />
        </aside>
        <main className="min-w-0 flex-1">{children}</main>
      </div>
      <BrutalDrawer open={navOpen} title="Navigate" onClose={() => setNavOpen(false)} side="left">
        <SideNav authenticated={authenticated} onNavigate={() => setNavOpen(false)} />
      </BrutalDrawer>
    </div>
  );
}
