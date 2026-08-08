"use client";

import { type ReactNode } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface BrutalButtonProps {
  children: ReactNode;
  href?: string;
  onClick?: () => void;
  variant?: "primary" | "ghost" | "yellow" | "default";
  size?: "sm" | "md" | "lg";
  className?: string;
  fullWidth?: boolean;
}

export function BrutalButton({ children, href, onClick, variant = "primary", size = "md", className, fullWidth }: BrutalButtonProps) {
  const base = "inline-flex items-center justify-center font-sans font-bold transition-all duration-200 relative overflow-hidden group tracking-[0.05em] uppercase";
  const sizes = { sm: "px-4 py-2 text-xs", md: "px-8 py-3 text-sm", lg: "px-10 py-4 text-sm" };
  const variants = {
    primary: "bg-black text-primary-container border border-primary-container hover:bg-primary-container hover:text-black",
    ghost: "bg-transparent text-on-surface border border-outline hover:border-on-surface hover:text-on-surface",
    yellow: "bg-primary-container text-black hover:bg-black hover:text-primary-container border border-primary-container",
    default: "bg-surface-container text-on-surface border border-outline hover:border-primary-container hover:text-primary-container",
  };

  const content = (
    <motion.div
      className={cn(base, sizes[size], variants[variant], fullWidth && "w-full", className)}
      whileHover={{ scale: 1.02 }}
      whileTap={{ scale: 0.98 }}
    >
      <span className="relative z-10 flex items-center gap-2">{children}</span>
    </motion.div>
  );

  if (href) return <a href={href}>{content}</a>;
  return <button onClick={onClick} type="button">{content}</button>;
}
