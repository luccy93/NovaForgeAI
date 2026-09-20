"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface BrutalColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export function BrutalTable<T>({
  columns,
  rows,
  emptyMessage = "No rows yet.",
  title,
  className,
}: {
  columns: Array<BrutalColumn<T>>;
  rows: Array<T>;
  emptyMessage?: string;
  title?: string;
  className?: string;
}) {
  if (rows.length === 0) {
    return (
      <div
        role="status"
        className={cn("border border-outline bg-surface p-8 text-center", className)}
      >
        <p className="text-sm text-on-surface-variant">{emptyMessage}</p>
      </div>
    );
  }
  return (
    <div
      role="region"
      aria-label={title ?? "Data table"}
      tabIndex={0}
      className={cn("overflow-x-auto border border-outline focus-visible:outline-2 focus-visible:outline-primary-container focus-visible:outline-offset-2", className)}
    >
      <table className="w-full border-collapse text-left text-sm">
        {title ? <caption className="sr-only">{title}</caption> : null}
        <thead>
          <tr className="border-b border-outline bg-surface">
            {columns.map((col) => (
              <th
                key={col.key}
                scope="col"
                className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest text-on-surface-variant"
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr
              key={(row as unknown as { id?: string | number }).id ?? i}
              className="border-b border-outline-variant bg-surface-container last:border-b-0"
            >
              {columns.map((col) => (
                <td key={col.key} className="px-4 py-3 text-on-surface">
                  {col.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
