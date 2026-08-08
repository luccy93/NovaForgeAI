"use client";

import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import Link from "next/link";
import {
  BookOpen, Zap, Layers, Cpu, GitBranch, Shield, Rocket,
  Code2, Terminal, Settings, Database, Network, FileText,
  ArrowRight, Search, ChevronRight,
} from "lucide-react";

const gettingStarted = [
  { icon: Rocket, title: "Quick Start", desc: "Get up and running in under 5 minutes with our CLI.", href: "#" },
  { icon: Terminal, title: "Installation", desc: "Install NovaForge via npm, yarn, or pnpm.", href: "#" },
  { icon: Settings, title: "Configuration", desc: "Configure your project with novaforge.config.ts.", href: "#" },
  { icon: Code2, title: "First Visualization", desc: "Render your codebase in 3D space.", href: "#" },
];

const apiReference = [
  { icon: Cpu, title: "Core API", desc: "Main engine methods — init, analyze, render, destroy.", badge: "v2.0" },
  { icon: Layers, title: "Spatial Engine", desc: "Three.js integration, camera controls, node layouts.", badge: "v2.0" },
  { icon: GitBranch, title: "Branch Intelligence", desc: "Branch diff, merge prediction, topology APIs.", badge: "v1.8" },
  { icon: Shield, title: "Security Scanner", desc: "Vulnerability detection, OWASP scanning, secrets audit.", badge: "v2.0" },
  { icon: Database, title: "RAG Pipeline", desc: "Embedding search, graph traversal, hybrid retrieval.", badge: "v2.0" },
  { icon: Network, title: "Agent Mesh", desc: "Multi-agent orchestration, task routing, consensus.", badge: "v2.0" },
];

const guides = [
  { title: "3D Code Visualization", category: "VISUALIZATION", time: "15 min" },
  { title: "Setting Up AI Agents", category: "AI", time: "10 min" },
  { title: "Multi-Repo Management", category: "ENTERPRISE", time: "20 min" },
  { title: "Custom Agent Creation", category: "ADVANCED", time: "25 min" },
  { title: "CI/CD Integration", category: "DEVOPS", time: "12 min" },
  { title: "Security Best Practices", category: "SECURITY", time: "18 min" },
];

export default function DocsPage() {
  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />

      {/* Hero */}
      <section className="pt-28 pb-20 bg-surface border-b border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="h-10 w-10 bg-primary-container flex items-center justify-center">
                <BookOpen className="h-5 w-5 text-black" />
              </div>
              <span className="label text-primary-container">Documentation</span>
            </div>
            <h1 className="text-[clamp(40px,5vw,72px)] font-bold leading-[0.95] tracking-[-0.03em] text-on-surface">
              Documentation
            </h1>
            <p className="mt-4 text-body-lg text-on-surface-variant max-w-lg">
              Everything you need to build with NovaForge. From quick start guides to advanced API references.
            </p>
          </motion.div>

          {/* Search bar */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className="mt-10 max-w-xl"
          >
            <div className="flex items-center gap-3 border border-outline bg-surface-container px-5 py-3.5 group focus-within:border-primary-container transition-colors">
              <Search className="h-4 w-4 text-on-surface-variant shrink-0" />
              <input
                type="text"
                placeholder="Search documentation..."
                className="bg-transparent text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none w-full"
              />
              <span className="label text-on-surface-variant border border-outline px-2 py-0.5 text-[10px]">⌘K</span>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Getting Started */}
      <section className="py-20 bg-surface">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <span className="label text-primary-container">Getting Started</span>
          <h2 className="mt-4 text-3xl font-bold text-on-surface">Start building in minutes</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 border-t border-l border-outline mt-10">
            {gettingStarted.map((item, i) => (
              <motion.a
                key={item.title}
                href={item.href}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * i, duration: 0.5 }}
                className="border-b border-r border-outline p-6 group hover:bg-surface-container transition-colors duration-300 flex flex-col"
              >
                <div className="h-10 w-10 border border-outline flex items-center justify-center mb-5 group-hover:border-primary-container transition-colors">
                  <item.icon className="h-5 w-5 text-primary-container" />
                </div>
                <h3 className="text-lg font-bold text-on-surface mb-2">{item.title}</h3>
                <p className="text-sm text-on-surface-variant flex-1">{item.desc}</p>
                <div className="mt-4 flex items-center gap-1 text-primary-container text-sm font-semibold group-hover:gap-2 transition-all">
                  Read more <ArrowRight className="h-3.5 w-3.5" />
                </div>
              </motion.a>
            ))}
          </div>
        </div>
      </section>

      {/* API Reference */}
      <section className="py-20 bg-surface-dim border-t border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <span className="label text-primary-container">API Reference</span>
          <h2 className="mt-4 text-3xl font-bold text-on-surface">Complete API documentation</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 border-t border-l border-outline mt-10">
            {apiReference.map((item, i) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.05 * i, duration: 0.5 }}
                className="border-b border-r border-outline p-6 group hover:bg-surface-container transition-colors duration-300 cursor-pointer"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <item.icon className="h-5 w-5 text-primary-container" />
                    <h3 className="text-lg font-bold text-on-surface">{item.title}</h3>
                  </div>
                  <span className="label text-on-surface-variant border border-outline px-2 py-0.5 text-[10px]">
                    {item.badge}
                  </span>
                </div>
                <p className="text-sm text-on-surface-variant">{item.desc}</p>
                <ChevronRight className="h-4 w-4 text-on-surface-variant mt-4 group-hover:text-primary-container group-hover:translate-x-1 transition-all" />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Guides */}
      <section className="py-20 bg-surface border-t border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <span className="label text-primary-container">Guides</span>
          <h2 className="mt-4 text-3xl font-bold text-on-surface">Step-by-step tutorials</h2>

          <div className="mt-10 border-t border-outline">
            {guides.map((guide, i) => (
              <motion.a
                key={guide.title}
                href="#"
                initial={{ opacity: 0, x: -20 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.05 * i }}
                className="flex items-center justify-between py-5 px-4 border-b border-outline group hover:bg-surface-container hover:pl-6 transition-all duration-300"
              >
                <div className="flex items-center gap-4">
                  <span className="tag-yellow text-[10px] w-24 text-center">{guide.category}</span>
                  <span className="text-body-md font-semibold text-on-surface group-hover:text-primary-container transition-colors">
                    {guide.title}
                  </span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="label text-on-surface-variant">{guide.time}</span>
                  <ArrowRight className="h-4 w-4 text-on-surface-variant group-hover:text-primary-container transition-colors" />
                </div>
              </motion.a>
            ))}
          </div>
        </div>
      </section>

      <FooterSection />
    </main>
  );
}
