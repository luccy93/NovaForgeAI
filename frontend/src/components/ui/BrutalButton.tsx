"use client";

import { type ButtonHTMLAttributes, type ReactNode } from "react";
import { motion } from "framer-motion";
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
  "inline-flex items-center justify-center font-sans font-bold transition-all duration-200 relative overflow-hidden group tracking-[0.05em] uppercase focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary-container disabled:opacity-50 disabled:pointer-events-none";
const sizes: Record<Size, string> = {
  sm: "px-4 py-2 text-xs",
  md: "px-8 py-3 text-sm",
  lg: "px-10 py-4 text-sm",
};
const variants: Record<Variant, string> = {
  primary:
    "bg-black text-primary-container border border-primary-container hover:bg-primary-container hover:text-black",
  ghost:
    "bg-transparent text-on-surface border border-outline hover:border-on-surface hover:text-on-surface",
  yellow:
    "bg-primary-container text-black hover:bg-black hover:text-primary-container border border-primary-container",
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
  ...rest
}: BrutalButtonProps) {
  const cls = cn(base, sizes[size], variants[variant], fullWidth && "w-full", className);
  const content = (
    <motion.span
      className="relative z-10 flex items-center gap-2"
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      {children}
    </motion.span>
  );
  if (href) {
    return (
      <a href={href} onClick={onClick} className={cls}>
        {content}
      </a>
    );
  }
  return (
    <button type={type} onClick={onClick} className={cls} {...rest}>
      {content}
    </button>
  );
}
