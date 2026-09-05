"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export function BrutalCard({
  title,
  eyebrow,
  actions,
  children,
  className,
}: {
  title?: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("border border-outline bg-surface-container p-6 text-left", className)}>
      {(eyebrow || title || actions) && (
        <header className="mb-4 flex items-start justify-between gap-4">
          <div>
            {eyebrow ? (
              <p className="mb-1 text-label-caps uppercase tracking-widest text-on-surface-variant">
                {eyebrow}
              </p>
            ) : null}
            {title ? <h2 className="text-xl font-bold text-on-surface">{title}</h2> : null}
          </div>
          {actions}
        </header>
      )}
      {children}
    </section>
  );
}
