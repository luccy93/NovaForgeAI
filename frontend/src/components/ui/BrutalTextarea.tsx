"use client";

import { type TextareaHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/utils";

export interface BrutalTextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  error?: string;
}

export const BrutalTextarea = forwardRef<HTMLTextAreaElement, BrutalTextareaProps>(
  function BrutalTextarea({ label, error, id, className, ...rest }, ref) {
    const inputId = id ?? `brutal-textarea-${label?.replace(/\s+/g, "-").toLowerCase() ?? "field"}`;
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
        <textarea
          ref={ref}
          id={inputId}
          aria-invalid={error ? true : undefined}
          className={cn(
            "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none focus:border-primary-container transition-colors disabled:opacity-50",
            error && "border-error",
            className,
          )}
          {...rest}
        />
        {error ? (
          <p role="alert" className="mt-2 text-sm text-error">
            {error}
          </p>
        ) : null}
      </div>
    );
  },
);
