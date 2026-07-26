"use client";

import { useRef, type ReactNode } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { cn } from "@/lib/utils";

interface BrutalPanelProps {
  children: ReactNode;
  className?: string;
  highlight?: boolean;
  style?: React.CSSProperties;
}

export function BrutalPanel({ children, className, highlight, style }: BrutalPanelProps) {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref as any, offset: ["start end", "end start"] });
  const opacity = useTransform(scrollYProgress, [0, 0.15, 0.8, 1], [0, 1, 1, 0]);

  return (
    <motion.div
      ref={ref}
      style={{ opacity, ...style }}
      className={cn(
        "border",
        highlight ? "border-primary-container bg-surface-container" : "border-outline bg-surface-container-low",
        className
      )}
    >
      {children}
    </motion.div>
  );
}
