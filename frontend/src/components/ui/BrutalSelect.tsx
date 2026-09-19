"use client";

import { type SelectHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface BrutalSelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: Array<{ value: string; label: string }>;
}

export const BrutalSelect = forwardRef<HTMLSelectElement, BrutalSelectProps>(
  function BrutalSelect({ label, error, id, options, className, ...rest }, ref) {
    const autoId = useId();
    const inputId = id ?? (label ? `brutal-select-${label.replace(/\s+/g, "-").toLowerCase()}-${autoId}` : `brutal-select-field-${autoId}`);
    return (
      <div className="w-full text-left">
        {label ? (
          <label
            htmlFor={inputId}
            className="mb-2 block text-label-caps uppercase tracking-widest text-on-surface-variant"
          >
            {label}
          </label>
        ) : null}
        <select
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : undefined}
          className={cn(
            "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface outline-none focus:border-primary-container transition-colors disabled:opacity-50",
            error && "border-error",
            className,
          )}
          {...rest}
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {error ? (
          <p id={`${inputId}-error`} role="alert" className="mt-2 text-sm text-error">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
