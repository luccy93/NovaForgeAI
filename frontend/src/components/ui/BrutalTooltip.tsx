"use client";

import { type ReactNode, useId, useState } from "react";

export function BrutalTooltip({ label, children }: { label: string; children: ReactNode }) {
  const [visible, setVisible] = useState(false);
  const id = useId();
  return (
    <span
      className="relative inline-flex"
      onMouseEnter={() => setVisible(true)}
      onMouseLeave={() => setVisible(false)}
      onFocus={() => setVisible(true)}
      onBlur={() => setVisible(false)}
      aria-describedby={visible ? id : undefined}
    >
      {children}
      {visible ? (
        <span
          id={id}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-[80] mb-2 -translate-x-1/2 border border-outline bg-black px-2 py-1 font-mono text-[11px] whitespace-nowrap text-on-surface"
        >
          {label}
        </span>
      ) : null}
    </span>
  );
}
