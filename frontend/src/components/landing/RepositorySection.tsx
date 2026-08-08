"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { fadeUp, staggerContainer } from "@/lib/animations";
import { GitFork, GitPullRequest, Code2, Network, BarChart3, ArrowRight } from "lucide-react";

const features = [
  { icon: GitFork, title: "Smart Branching", desc: "Visual branch topology with AI-predicted merge outcomes. Never break main again." },
  { icon: GitPullRequest, title: "PR Intelligence", desc: "AI reviews every PR with architectural context. Suggests changes before humans review." },
  { icon: Code2, title: "Live Indexing", desc: "Real-time codebase indexing. Every commit, every branch, instantly searchable." },
  { icon: Network, title: "Dependency Graph", desc: "Interactive 3D dependency graph. See the full impact of any change." },
  { icon: BarChart3, title: "Code Analytics", desc: "Complexity trends, contributor insights, and quality metrics over time." },
];

const codeLines = [
  { indent: 0, text: "import { NovaForge } from '@novaforge/core'" },
  { indent: 0, text: "" },
  { indent: 0, text: "const engine = new NovaForge({" },
  { indent: 1, text: "mode: 'spatial'," },
  { indent: 1, text: "agents: ['planner', 'reviewer', 'security']," },
  { indent: 1, text: "indexing: { realtime: true }," },
  { indent: 0, text: "})" },
  { indent: 0, text: "" },
  { indent: 0, text: "await engine.analyze('./src')" },
];

export function RepositorySection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const headingY = useTransform(scrollYProgress, [0, 0.2], [60, 0]);

  return (
    <section id="enterprise" ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-[#0a0a0a] border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-start">
          {/* Left — text content */}
          <motion.div style={{ y: headingY }}>
            <div className="inline-flex items-center gap-2 border border-white/20 bg-[#151515] px-3 py-1 mb-8">
              <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">05 / Repository Intelligence</span>
            </div>
            
            <h2 className="text-[clamp(32px,4vw,56px)] font-bold tracking-tight text-white leading-tight">
              Your codebase,
              <br />
              <span className="text-white/40">reimagined in 3D</span>
            </h2>
            <p className="mt-6 text-lg text-white/60 leading-relaxed max-w-md">
              Stop jumping between files. Navigate your entire repository as a living, breathing spatial environment.
            </p>

            <motion.div
              variants={staggerContainer}
              initial="hidden"
              whileInView="visible"
              viewport={{ once: true }}
              className="mt-12 border-t border-white/10"
            >
              {features.map((f) => (
                <motion.div
                  key={f.title}
                  variants={fadeUp}
                  className="flex items-start gap-5 py-6 border-b border-white/10 group hover:pl-4 transition-all duration-300 bg-[#0f0f0f] hover:bg-[#151515]"
                >
                  <div className="h-10 w-10 border border-white/20 flex items-center justify-center shrink-0 group-hover:border-primary-container transition-colors ml-6">
                    <f.icon className="h-4 w-4 text-white group-hover:text-primary-container transition-colors" />
                  </div>
                  <div className="pr-6">
                    <h4 className="text-lg font-bold text-white group-hover:text-primary-container transition-colors">{f.title}</h4>
                    <p className="text-sm text-white/50 mt-1 leading-relaxed">{f.desc}</p>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </motion.div>

          {/* Right — code preview */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.6 }}
            className="border border-white/20 bg-[#0a0a0a] sticky top-32 p-1"
          >
            <div className="bg-[#0f0f0f] h-full border border-white/10">
              {/* Terminal header */}
              <div className="flex items-center justify-between px-6 py-4 border-b border-white/10 bg-[#151515]">
                <div className="flex gap-2">
                  <span className="w-2.5 h-2.5 bg-white/20" />
                  <span className="w-2.5 h-2.5 bg-white/20" />
                  <span className="w-2.5 h-2.5 bg-white/20" />
                </div>
                <span className="font-mono text-xs font-bold text-white/40 tracking-widest uppercase">index.ts</span>
                <div className="w-8" /> {/* spacer for balance */}
              </div>
              
              {/* Code body */}
              <div className="p-8 font-mono text-sm leading-8 bg-[#0a0a0a] relative overflow-hidden">
                {/* Decorative background grid in the code window */}
                <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff03_1px,transparent_1px),linear-gradient(to_bottom,#ffffff03_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none" />
                
                <div className="relative z-10">
                  {codeLines.map((line, i) => (
                    <motion.div
                      key={i}
                      initial={{ opacity: 0, x: -10 }}
                      whileInView={{ opacity: 1, x: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: i * 0.08 }}
                      style={{ paddingLeft: `${line.indent * 24}px` }}
                      className="flex items-center gap-6 group cursor-default"
                    >
                      <span className="text-white/20 w-6 text-right select-none text-xs group-hover:text-primary-container transition-colors">{i + 1}</span>
                      <span className="text-white/70 group-hover:text-white transition-colors">
                        {line.text.split("'").map((part, pi, arr) =>
                          pi < arr.length - 1 ? (
                            <span key={pi}>
                              {part}
                              <span className="text-primary-container">&apos;</span>
                            </span>
                          ) : (
                            <span key={pi}>{part}</span>
                          )
                        )}
                      </span>
                    </motion.div>
                  ))}
                  <motion.div 
                    className="flex items-center gap-6 mt-4"
                    initial={{ opacity: 0 }}
                    whileInView={{ opacity: 1 }}
                    viewport={{ once: true }}
                    transition={{ delay: codeLines.length * 0.08 + 0.2 }}
                  >
                    <span className="text-white/20 w-6 text-right select-none text-xs">{codeLines.length + 1}</span>
                    <span className="w-2.5 h-4 bg-primary-container animate-pulse" />
                  </motion.div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </div>
    </section>
  );
}
