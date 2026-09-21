"use client";

import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { cn } from "@/lib/utils";

type Variant = "primary" | "ghost" | "yellow" | "default";
type Size = "sm" | "md" | "lg";

interface BrutalButtonProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  children: ReactNode;
  href?: string;
  onClick?: () => void;
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
}

const base =
  "inline-flex items-center justify-center font-sans font-bold transition-all duration-200 relative overflow-hidden group tracking-[0.05em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-container disabled:opacity-60 disabled:pointer-events-none disabled:cursor-not-allowed min-h-[44px] min-w-[44px]";
const sizes: Record<Size, string> = {
  sm: "px-4 py-2 text-xs",
  md: "px-8 py-3 text-sm",
  lg: "px-10 py-4 text-sm",
};
const variants: Record<Variant, string> = {
  primary:
    "bg-surface text-primary-container border border-primary-container hover:bg-primary-container hover:text-on-primary",
  ghost:
    "bg-transparent text-on-surface border border-outline hover:border-on-surface hover:text-on-surface",
  yellow:
    "bg-primary-container text-on-primary hover:bg-surface hover:text-primary-container border border-primary-container",
  default:
    "bg-surface-container text-on-surface border border-outline hover:border-primary-container hover:text-primary-container",
};

export function BrutalButton({
  children,
  href,
  onClick,
  variant = "primary",
  size = "md",
  fullWidth,
  className,
  type = "button",
  disabled,
  "aria-label": ariaLabel,
  "aria-disabled": ariaDisabled,
  id,
  ...rest
}: BrutalButtonProps & { "aria-label"?: string; "aria-disabled"?: boolean; id?: string }) {
  const cls = cn(base, sizes[size], variants[variant], fullWidth && "w-full", "hover:scale-[1.02] active:scale-[0.98]", className);
  const content = <span className="relative z-10 flex items-center gap-2">{children}</span>;
  if (href) {
    const isDisabled = Boolean(disabled || ariaDisabled);
    return (
      <a
        href={isDisabled ? undefined : href}
        aria-label={ariaLabel}
        aria-disabled={isDisabled || undefined}
        id={id}
        onClick={onClick}
        className={cn(cls, isDisabled && "opacity-60 pointer-events-none")}
        role={isDisabled ? "link" : undefined}
        tabIndex={isDisabled ? -1 : undefined}
      >
        {content}
      </a>
    );
  }
  return (
    <button type={type} onClick={onClick} disabled={disabled} aria-label={ariaLabel} aria-disabled={ariaDisabled} id={id} className={cls} {...rest}>
      {content}
    </button>
  );
}
