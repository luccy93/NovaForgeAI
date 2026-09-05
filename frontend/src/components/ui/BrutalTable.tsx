"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface BrutalColumn<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
}

export function BrutalTable<T extends { id?: string | number }>({
  columns,
  rows,
  emptyMessage = "No rows yet.",
  className,
}: {
  columns: Array<BrutalColumn<T>>;
  rows: Array<T>;
  emptyMessage?: string;
  className?: string;
}) {
  if (rows.length === 0) {
    return (
      <div className={cn("border border-outline bg-surface p-8 text-center", className)}>
        <p className="text-sm text-on-surface-variant">{emptyMessage}</p>
      </div>
    );
  }
  return (
    <div className={cn("overflow-x-auto border border-outline", className)}>
      <table className="w-full border-collapse text-left text-sm">
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
              key={row.id ?? i}
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
