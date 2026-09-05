"use client";

import Link from "next/link";
import { Fragment } from "react";

export interface Crumb {
  label: string;
  href?: string;
}

export function Breadcrumbs({ items }: { items: Array<Crumb> }) {
  if (items.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className="mb-4">
      <ol className="flex flex-wrap items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant">
        {items.map((crumb, index) => {
          const last = index === items.length - 1;
          return (
            <Fragment key={`${crumb.label}-${index}`}>
              {index > 0 ? <li aria-hidden="true">/</li> : null}
              <li>
                {crumb.href && !last ? (
                  <Link href={crumb.href} className="hover:text-primary-container">
                    {crumb.label}
                  </Link>
                ) : (
                  <span aria-current={last ? "page" : undefined} className={last ? "text-on-surface" : undefined}>
                    {crumb.label}
                  </span>
                )}
              </li>
            </Fragment>
          );
        })}
      </ol>
    </nav>
  );
}
