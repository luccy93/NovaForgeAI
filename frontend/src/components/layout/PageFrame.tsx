"use client";

import { type ReactNode } from "react";
import { Breadcrumbs, type Crumb } from "@/components/layout/Breadcrumbs";

export function PageFrame({
  eyebrow,
  title,
  description,
  actions,
  crumbs,
  children,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  crumbs?: Array<Crumb>;
  children: ReactNode;
}) {
  return (
    <div className="mx-auto w-full max-w-[1400px] px-4 py-8 lg:px-6">
      {crumbs ? <Breadcrumbs items={crumbs} /> : null}
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          {eyebrow ? (
            <p className="mb-2 font-mono text-[11px] uppercase tracking-widest text-primary-container">
              {eyebrow}
            </p>
          ) : null}
          <h1 className="text-4xl font-bold text-on-surface">{title}</h1>
          {description ? <p className="mt-2 max-w-2xl text-body-md text-on-surface-variant">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
      </div>
      {children}
    </div>
  );
}
