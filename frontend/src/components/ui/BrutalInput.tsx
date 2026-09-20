"use client";

import { type InputHTMLAttributes, forwardRef, useId } from "react";
import { cn } from "@/lib/utils";

export interface BrutalInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

const inputCls =
  "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/70 outline-none focus:border-primary-container focus-visible:outline-2 focus-visible:outline-primary-container focus-visible:outline-offset-2 transition-colors disabled:opacity-60 disabled:cursor-not-allowed";

export const BrutalInput = forwardRef<HTMLInputElement, BrutalInputProps>(
  function BrutalInput({ label, error, id, className, ...rest }, ref) {
    const autoId = useId();
    const inputId = id ?? (label ? `brutal-input-${label.replace(/\s+/g, "-").toLowerCase()}-${autoId}` : `brutal-input-field-${autoId}`);
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
