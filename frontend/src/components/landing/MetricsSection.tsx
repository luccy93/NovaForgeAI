"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { AnimatedCounter } from "@/components/ui/AnimatedCounter";

const metrics = [
  { value: 1200, suffix: "+", label: "Engineering Teams", subtitle: "Trusted by Fortune 500" },
  { value: 47, suffix: "%", label: "Faster Shipment", subtitle: "Average velocity increase" },
  { value: 99.9, suffix: "%", label: "Uptime", subtitle: "Last 12 months" },
  { value: 3.2, suffix: "M+", label: "Repos Indexed", subtitle: "Across all tiers" },
];

export function MetricsSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const y = useTransform(scrollYProgress, [0, 0.3], [60, 0]);
  const opacity = useTransform(scrollYProgress, [0, 0.3], [0, 1]);

  return (
    <section ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-primary-container border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12 relative z-10">
        <motion.div style={{ y, opacity }}>
          <div className="inline-flex items-center gap-2 border border-black bg-black px-3 py-1 mb-12">
            <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">04 / Metrics</span>
          </div>
        </motion.div>
        
        <motion.div style={{ opacity }} className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 border border-black">
          {metrics.map((m, i) => (
            <div
              key={m.label}
              className={`py-16 px-8 relative flex flex-col items-start ${
                i < metrics.length - 1 ? "border-b sm:border-b-0 sm:border-r border-black" : ""
              } ${i === 1 ? "border-b lg:border-b-0 border-black" : ""}`}
            >
              <div className="text-[clamp(48px,5vw,72px)] leading-none font-bold tracking-tight text-black tabular-nums mb-4">
                <AnimatedCounter from={0} to={m.value} />{m.suffix}
              </div>
              <p className="mt-auto text-lg font-bold text-black uppercase tracking-widest">{m.label}</p>
              <p className="mt-2 text-sm font-mono text-black/60">{m.subtitle}</p>
            </div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
