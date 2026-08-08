"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { fadeUp, staggerContainer } from "@/lib/animations";
import { Brain, Search, Shield, TestTube, FileText, Rocket, ArrowRight } from "lucide-react";

const agents = [
  { num: "01", icon: Brain, name: "Planner", desc: "Analyzes requirements and generates multi-step implementation plans across your codebase.", status: "Active" },
  { num: "02", icon: Search, name: "Reviewer", desc: "Code review with architectural awareness. Catches logic errors, security issues, and style problems.", status: "Active" },
  { num: "03", icon: Shield, name: "Security", desc: "Real-time vulnerability scanning. Detects OWASP Top 10, secrets leakage, and dependency risks.", status: "Active" },
  { num: "04", icon: TestTube, name: "Testing", desc: "Generates unit, integration, and E2E tests. Achieves 90%+ coverage automatically.", status: "Active" },
  { num: "05", icon: FileText, name: "Documentation", desc: "Generates and maintains living documentation that stays in sync with your code.", status: "Active" },
  { num: "06", icon: Rocket, name: "Deployment", desc: "Manages CI/CD pipelines, containerization, and infrastructure as code.", status: "Active" },
];

export function AIAgentsSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const headingOpacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);

  return (
    <section id="agents" ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-[#0a0a0a] border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12 relative z-10">
        <motion.div style={{ opacity: headingOpacity }} className="mb-20 text-center max-w-3xl mx-auto">
          <div className="inline-flex items-center gap-2 border border-white/20 bg-[#151515] px-3 py-1 mb-8">
            <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">02 / AI Agents</span>
          </div>
          <h2 className="text-[clamp(32px,4vw,56px)] font-bold tracking-tight text-white leading-tight">
            Six specialized agents.
            <br />
            <span className="text-white/40">One unified intelligence.</span>
          </h2>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 border-t border-l border-white/10 bg-[#0f0f0f]"
        >
          {agents.map((agent) => (
            <motion.div
              key={agent.name}
              variants={fadeUp}
              className="border-b border-r border-white/10 p-10 group hover:bg-[#1a1a1a] transition-colors duration-300 relative flex flex-col"
            >
              <div className="flex items-start justify-between mb-8">
                <div className="h-12 w-12 border border-white/20 bg-[#0a0a0a] flex items-center justify-center group-hover:border-primary-container transition-colors">
                  <agent.icon className="h-5 w-5 text-white group-hover:text-primary-container transition-colors" />
                </div>
                <span className="font-mono text-xs font-bold text-white/30 tracking-widest">{agent.num}</span>
              </div>
              
              <h3 className="text-xl font-bold text-white mb-4">{agent.name}</h3>
              <p className="text-sm text-white/60 leading-relaxed flex-1">{agent.desc}</p>
              
              <div className="mt-10 pt-6 border-t border-white/10 flex items-center justify-between">
                <span className="font-mono text-[10px] uppercase text-white/40 tracking-widest">Status</span>
                <span className="font-mono text-[10px] uppercase text-primary-container flex items-center gap-2 tracking-widest bg-primary-container/10 px-2 py-1">
                  <span className="h-1.5 w-1.5 bg-primary-container animate-pulse" />
                  {agent.status}
                </span>
              </div>
            </motion.div>
          ))}
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="mt-16 flex justify-center"
        >
          <a href="#enterprise" className="inline-flex items-center gap-4 border border-white/20 bg-[#151515] px-8 py-4 hover:bg-white hover:text-black hover:border-white transition-all group">
            <span className="font-mono text-sm uppercase tracking-widest font-bold">See Agent Mesh Architecture</span>
            <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
          </a>
        </motion.div>
      </div>
    </section>
  );
}
