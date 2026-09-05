"use client";

import { cn } from "@/lib/utils";

export function BrutalSkeleton({ className, label = "Loading" }: { className?: string; label?: string }) {
  return (
    <div
      role="status"
      aria-label={label}
      className={cn("animate-pulse border border-outline bg-surface-container-high", className)}
    >
      <span className="sr-only">{label}…</span>
    </div>
  );
}
