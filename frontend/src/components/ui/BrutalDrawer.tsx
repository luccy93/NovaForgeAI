"use client";

import { type ReactNode, useEffect, useId, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";

export function BrutalDrawer({
  open,
  title,
  onClose,
  children,
  side = "right",
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  side?: "left" | "right";
}) {
  const panelRef = useRef<HTMLElement>(null);
  const titleId = useId();
  const previousActiveRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previousActiveRef.current = document.activeElement as HTMLElement | null;
    const frame = window.requestAnimationFrame(() => panelRef.current?.focus());
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
      if (event.key === "Tab") {
        const root = panelRef.current;
        if (!root) return;
        const focusables = Array.from(root.querySelectorAll<HTMLElement>("button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"));
        if (focusables.length === 0) return;
        const first = focusables[0];
        const last = focusables[focusables.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.cancelAnimationFrame(frame);
      const prev = previousActiveRef.current;
      if (prev && typeof prev.focus === "function") window.requestAnimationFrame(() => prev.focus());
    };
  }, [open, onClose]);

  const x = side === "right" ? "100%" : "-100%";
  return (
    <AnimatePresence>
      {open ? (
        <motion.div
          className="fixed inset-0 z-[70] bg-black/70"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onClick={onClose}
          role="presentation"
        >
          <motion.aside
            ref={panelRef as unknown as React.RefObject<HTMLDivElement>}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className={`absolute top-0 bottom-0 ${side === "right" ? "right-0" : "left-0"} w-full max-w-sm border-outline bg-surface-container p-6 outline-none ${
              side === "right" ? "border-l" : "border-r"
            }`}
            initial={{ x }}
            animate={{ x: 0 }}
            exit={{ x }}
            transition={{ duration: 0.18 }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <h2 id={titleId} className="text-xl font-bold text-on-surface">{title}</h2>
              <button
                type="button"
                onClick={onClose}
                aria-label="Close panel"
                className="border border-outline px-2 py-1 font-mono text-xs text-on-surface-variant hover:border-on-surface hover:text-on-surface"
              >
                ESC
              </button>
            </div>
            {children}
          </motion.aside>
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
