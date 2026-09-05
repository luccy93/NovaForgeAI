"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { visibleNavItems, type NavItem } from "@/lib/navigation";

const SECTION_LABELS: Record<NavItem["section"], string> = {
  main: "Workspace",
  platform: "Platform",
  system: "System",
};

export function SideNav({ authenticated, onNavigate }: { authenticated: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const items = visibleNavItems(authenticated);
  const sections = (["main", "platform", "system"] as const).map((section) => ({
    section,
    items: items.filter((item) => item.section === section),
  }));

  return (
    <nav aria-label="Application" className="flex h-full flex-col gap-6 overflow-y-auto">
      {sections.map(
        ({ section, items: sectionItems }) =>
          sectionItems.length > 0 && (
            <div key={section}>
              <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
                {SECTION_LABELS[section]}
              </p>
              <ul className="space-y-1">
                {sectionItems.map((item) => {
                  const active = pathname === item.href;
                  return (
                    <li key={item.id}>
                      <Link
                        href={item.href}
                        onClick={onNavigate}
                        aria-current={active ? "page" : undefined}
                        className={cn(
                          "block border-l-2 px-3 py-2 text-sm transition-colors",
                          active
                            ? "border-primary-container bg-surface-container-high text-on-surface"
                            : "border-transparent text-on-surface-variant hover:border-outline hover:text-on-surface",
                        )}
                      >
                        {item.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ),
      )}
    </nav>
  );
}
