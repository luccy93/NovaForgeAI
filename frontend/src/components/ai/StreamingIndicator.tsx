"use client";

import { motion } from "framer-motion";

const dot = "inline-block h-1.5 w-1.5 rounded-full bg-primary-container";

export function StreamingIndicator() {
  return (
    <div className="flex items-center gap-1.5 px-4 py-2" role="status" aria-live="polite">
      <motion.span
        className={dot}
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0 }}
      />
      <motion.span
        className={dot}
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.2 }}
      />
      <motion.span
        className={dot}
        animate={{ opacity: [0.3, 1, 0.3] }}
        transition={{ duration: 1.2, repeat: Infinity, delay: 0.4 }}
      />
      <span className="sr-only">AI is generating a response</span>
    </div>
  );
}
