"use client";

import { useEffect, useRef, useState } from "react";

export function UserMenu({
  email,
  onLogout,
  onOpenPalette,
}: {
  email: string;
  onLogout: () => void;
  onOpenPalette?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    function onPointer(event: PointerEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open ]);

  const initial = (email.trim()[0] ?? "?").toUpperCase();
  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="flex h-9 w-9 items-center justify-center border border-outline bg-surface-container font-bold text-primary-container hover:border-primary-container"
      >
        {initial}
      </button>
      {open ? (
        <div
          role="menu"
          aria-label="Account"
          className="absolute right-0 top-11 z-[60] w-64 border border-outline bg-surface-container p-2"
        >
          <p className="truncate px-3 py-2 font-mono text-xs text-on-surface-variant">{email}</p>
          <div className="border-t border-outline-variant">
            <a href="/settings/profile" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Profile</a>
            <a href="/settings/security" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Security</a>
            <a href="/settings/organization" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Organization</a>
            <a href="/settings/members" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Members</a>
            <a href="/settings/workspaces" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Workspaces</a>
            <a href="/settings/roles" role="menuitem" onClick={() => setOpen(false)} className="block px-3 py-2 text-sm text-on-surface hover:bg-surface-container-high">Roles</a>
            {onOpenPalette ? (
              <button
                type="button"
                role="menuitem"
                onClick={() => {
                  setOpen(false);
                  onOpenPalette();
                }}
                className="block w-full px-3 py-2 text-left text-sm text-on-surface hover:bg-surface-container-high"
              >
                Command palette <span className="font-mono text-xs text-on-surface-variant">⌘K</span>
              </button>
            ) : null}
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                onLogout();
              }}
              className="block w-full px-3 py-2 text-left text-sm text-on-surface hover:bg-surface-container-high"
            >
              Log out
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}
