"use client";

import { type ReactNode } from "react";

export function BrutalEmptyState({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="border border-outline bg-surface p-8 text-center">
      <p className="font-bold text-on-surface">{title}</p>
      {description ? <p className="mt-2 text-sm text-on-surface-variant">{description}</p> : null}
      {actions ? <div className="mt-4 flex justify-center gap-3">{actions}</div> : null}
    </div>
  );
}
