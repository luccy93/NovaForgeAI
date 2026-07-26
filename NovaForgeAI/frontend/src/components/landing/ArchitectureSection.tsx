"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { fadeInRight, fadeInLeft, staggerContainer } from "@/lib/animations";

const layers = [
  { num: "01", label: "3D Spatial Engine", desc: "Three.js powered rendering engine with WebGPU support. Handles millions of nodes with instanced rendering." },
  { num: "02", label: "AI Agent Mesh", desc: "Distributed agent network. Planner, Reviewer, Security, Testing, Documentation, Deployment — all coordinated." },
  { num: "03", label: "Real-Time Sync", desc: "WebSocket-based live collaboration. Multiple engineers can explore the same codebase simultaneously." },
  { num: "04", label: "Multi-Database Engine", desc: "PostgreSQL for metadata. Neo4j for code graphs. Qdrant for vectors. Redis for caching." },
  { num: "05", label: "Enterprise Security", desc: "SOC 2 compliant. End-to-end encryption. RBAC with granular permissions and audit logging." },
];

const services = ["3D Spatial Engine", "AI Agent Mesh", "Real-Time Sync", "Enterprise Security", "Plugin System"];

export function ArchitectureSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const headingOpacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);

  return (
    <section id="architecture" ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-[#0f0f0f] border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12 relative z-10">
        <motion.div style={{ opacity: headingOpacity }} className="mb-24">
          <div className="inline-flex items-center gap-2 border border-white/20 bg-[#151515] px-3 py-1 mb-8">
            <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">03 / Architecture</span>
          </div>
          <h2 className="text-[clamp(32px,4vw,56px)] font-bold tracking-tight text-white leading-tight">
            Built for scale.
            <br />
            <span className="text-white/40">Engineered for performance.</span>
          </h2>
        </motion.div>

        <div className="relative grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24">
          <motion.div variants={staggerContainer} initial="hidden" whileInView="visible" viewport={{ once: true }} className="space-y-0">
            {layers.map((layer) => (
              <motion.div key={layer.num} variants={fadeInLeft} className="group border-t border-white/10 py-8 first:border-t-0">
                <div className="flex flex-col sm:flex-row sm:items-start gap-6">
                  <span className="font-mono text-2xl font-bold text-primary-container tracking-tighter">{layer.num}</span>
                  <div>
                    <h3 className="text-xl font-bold text-white mb-2 group-hover:text-primary-container transition-colors">{layer.label}</h3>
                    <p className="text-sm text-white/60 leading-relaxed">{layer.desc}</p>
                  </div>
                </div>
              </motion.div>
            ))}
            <div className="border-t border-white/10" />
          </motion.div>

          <motion.div variants={fadeInRight} initial="hidden" whileInView="visible" viewport={{ once: true }} className="relative lg:sticky lg:top-32 self-start">
            <div className="border border-white/10 bg-[#0a0a0a] p-8 lg:p-12 relative">
              {/* Decorative grid */}
              <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff05_1px,transparent_1px),linear-gradient(to_bottom,#ffffff05_1px,transparent_1px)] bg-[size:24px_24px] pointer-events-none" />
              
              <div className="relative z-10">
                <div className="inline-flex items-center gap-3 border border-white/10 bg-[#151515] px-4 py-2 mb-10">
                  <span className="h-2 w-2 bg-primary-container animate-pulse" />
                  <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">All systems operational</span>
                </div>
                
                <div className="space-y-6">
                  {services.map((service) => (
                    <div key={service} className="flex items-center justify-between pb-6 border-b border-white/10 last:border-0 last:pb-0">
                      <span className="text-sm font-bold text-white">{service}</span>
                      <div className="flex items-center gap-4">
                        <div className="hidden sm:block h-1 w-24 bg-white/10 overflow-hidden">
                          <div className="h-full w-[100%] bg-primary-container" />
                        </div>
                        <span className="font-mono text-xs font-bold text-white/40 uppercase tracking-widest">Ready</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
