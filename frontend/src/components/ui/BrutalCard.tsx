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
    <section className={cn("w-full min-w-0 border border-outline bg-surface-container p-4 sm:p-6 text-left break-words", className)}>
      {(eyebrow || title || actions) && (
        <header className="mb-4 flex min-w-0 flex-wrap items-start justify-between gap-2 sm:gap-4">
          <div className="min-w-0 flex-1">
            {eyebrow ? (
              <p className="mb-1 break-words text-label-caps uppercase tracking-widest text-on-surface-variant">
                {eyebrow}
              </p>
            ) : null}
            {title ? <h2 className="break-words text-lg font-bold text-on-surface sm:text-xl">{title}</h2> : null}
          </div>
          {actions ? <div className="flex shrink-0 flex-wrap gap-2">{actions}</div> : null}
        </header>
      )}
      <div className="min-w-0 break-words">
        {children}
      </div>
    </section>
  );
}
