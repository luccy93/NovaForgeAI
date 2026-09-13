"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { NAV_GROUPS, visibleNavItems } from "@/lib/navigation";

export function SideNav({ authenticated, onNavigate }: { authenticated: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  const items = visibleNavItems(authenticated);
  const groups = NAV_GROUPS.map(({ id, label }) => ({
    id,
    label,
    items: items.filter((item) => item.group === id),
  })).filter((group) => group.items.length > 0);

  return (
    <nav aria-label="Application" className="flex h-full flex-col gap-6 overflow-y-auto">
      {groups.map(({ id, label, items: groupItems }) => (
        <div key={id}>
          <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">{label}</p>
          <ul className="space-y-1">
            {groupItems.map((item) => {
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
      ))}
    </nav>
  );
}