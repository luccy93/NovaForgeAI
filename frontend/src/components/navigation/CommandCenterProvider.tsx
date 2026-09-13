"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { CommandPalette } from "@/components/navigation/CommandPalette";

interface CommandCenterContextValue {
  /** Open the global command palette. */
  open: () => void;
}

/**
 * Safe default so components render without a provider (e.g. in isolated
 * page tests). Coordinates with a no-op open().
 */
const CommandCenterContext = createContext<CommandCenterContextValue>({ open: () => {} });

export function useCommandCenter(): CommandCenterContextValue {
  return useContext(CommandCenterContext);
}

/**
 * Global command center provider. Registers the platform-wide Ctrl/Cmd+K
 * shortcut and owns the single CommandPalette instance so the command affordance
 * works on every page, not just the dashboard.
 */
export function CommandCenterProvider({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const openPalette = useCallback(() => setOpen(true), []);

  return (
    <CommandCenterContext.Provider value={{ open: openPalette }}>
      {children}
      <CommandPalette open={open} onClose={() => setOpen(false)} />
    </CommandCenterContext.Provider>
  );
}