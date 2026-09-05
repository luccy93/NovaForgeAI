"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

type BadgeTone = "yellow" | "default" | "error" | "muted";

const tones: Record<BadgeTone, string> = {
  yellow: "bg-primary-container text-black border-primary-container",
  default: "bg-surface-container text-on-surface border-outline",
  error: "bg-error-container text-error-on-container border-error",
  muted: "bg-transparent text-on-surface-variant border-outline",
};

export function BrutalBadge({
  children,
  tone = "default",
  className,
}: {
  children: ReactNode;
  tone?: BadgeTone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center border px-2 py-1 font-mono text-[11px] uppercase tracking-widest",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
