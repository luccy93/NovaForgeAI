"use client";

import { type ReactNode, useEffect } from "react";
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
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
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
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className={`absolute top-0 bottom-0 ${side === "right" ? "right-0" : "left-0"} w-full max-w-sm border-outline bg-surface-container p-6 ${
              side === "right" ? "border-l" : "border-r"
            }`}
            initial={{ x }}
            animate={{ x: 0 }}
            exit={{ x }}
            transition={{ duration: 0.18 }}
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <h2 className="text-xl font-bold text-on-surface">{title}</h2>
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
