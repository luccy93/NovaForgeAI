"use client";

import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface BrutalInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const inputCls =
  "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none focus:border-primary-container transition-colors disabled:opacity-50";

export const BrutalInput = forwardRef<HTMLInputElement, BrutalInputProps>(
  function BrutalInput({ label, error, id, className, ...rest }, ref) {
    const inputId = id ?? `brutal-input-${label?.replace(/\s+/g, "-").toLowerCase() ?? "field"}`;
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
        <input
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${inputId}-error` : undefined}
          className={cn(inputCls, error && "border-error", className)}
          {...rest}
        />
        {error ? (
          <p id={`${inputId}-error`} role="alert" className="mt-2 text-sm text-error">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
