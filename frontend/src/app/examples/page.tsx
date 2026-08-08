"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import {
  Box, GitBranch, Shield, Zap, Layers, Network,
  Code2, Eye, Play, ExternalLink, Filter,
  RotateCcw, Sparkles, Puzzle, BarChart3, Lock,
} from "lucide-react";

const categories = ["All", "Visualization", "AI Agents", "Security", "Analytics", "Integration"];

const examples = [
  {
    title: "3D Codebase Explorer",
    desc: "Navigate your entire repository as an interactive 3D spatial environment with real-time node updates.",
    category: "Visualization",
    icon: Box,
    difficulty: "Beginner",
    lines: 42,
    accent: true,
  },
  {
    title: "Branch Diff Visualizer",
    desc: "Compare branches side-by-side in 3D space. See merge conflicts before they happen.",
    category: "Visualization",
    icon: GitBranch,
    difficulty: "Intermediate",
    lines: 78,
    accent: false,
  },
  {
    title: "AI Code Reviewer",
    desc: "Set up an AI agent that reviews PRs with full architectural context and suggests improvements.",
    category: "AI Agents",
    icon: Eye,
    difficulty: "Beginner",
    lines: 35,
    accent: false,
  },
  {
    title: "Multi-Agent Refactor",
    desc: "Orchestrate planner, reviewer, and testing agents to refactor a legacy codebase safely.",
    category: "AI Agents",
    icon: Sparkles,
    difficulty: "Advanced",
    lines: 124,
    accent: true,
  },
  {
    title: "Vulnerability Scanner",
    desc: "Real-time OWASP Top 10 scanning with dependency risk analysis and secrets detection.",
    category: "Security",
    icon: Shield,
    difficulty: "Intermediate",
    lines: 56,
    accent: false,
  },
  {
    title: "Dependency Graph",
    desc: "Interactive dependency visualization showing impact analysis for every code change.",
    category: "Analytics",
    icon: Network,
    difficulty: "Beginner",
    lines: 48,
    accent: false,
  },
  {
    title: "Custom Agent Builder",
    desc: "Create your own specialized AI agent with custom tools, prompts, and review criteria.",
    category: "AI Agents",
    icon: Puzzle,
    difficulty: "Advanced",
    lines: 156,
    accent: false,
  },
  {
    title: "Code Complexity Heatmap",
    desc: "Visualize complexity hotspots in your codebase with color-coded 3D overlays.",
    category: "Analytics",
    icon: BarChart3,
    difficulty: "Intermediate",
    lines: 63,
    accent: true,
  },
  {
    title: "SSO/SAML Integration",
    desc: "Connect NovaForge to your identity provider — Okta, Azure AD, Google Workspace.",
    category: "Integration",
    icon: Lock,
    difficulty: "Intermediate",
    lines: 89,
    accent: false,
  },
  {
    title: "Live Indexing Pipeline",
    desc: "Stream real-time repository changes into the spatial engine with incremental updates.",
    category: "Integration",
    icon: Zap,
    difficulty: "Advanced",
    lines: 112,
    accent: false,
  },
  {
    title: "Layout Animations",
    desc: "Smoothly animate between different 3D layout algorithms — force-directed, tree, radial.",
    category: "Visualization",
    icon: RotateCcw,
    difficulty: "Intermediate",
    lines: 71,
    accent: false,
  },
  {
    title: "Monorepo Explorer",
    desc: "Navigate and manage multi-package repositories with cross-repo dependency tracking.",
    category: "Integration",
    icon: Layers,
    difficulty: "Advanced",
    lines: 98,
    accent: false,
  },
];

const difficultyColors: Record<string, string> = {
  Beginner: "text-green-400",
  Intermediate: "text-primary-container",
  Advanced: "text-[#ff6b9d]",
};

export default function ExamplesPage() {
  const [active, setActive] = useState("All");

  const filtered = active === "All" ? examples : examples.filter((e) => e.category === active);

  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />

      {/* Hero */}
      <section className="pt-28 pb-16 bg-surface border-b border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="h-10 w-10 bg-primary-container flex items-center justify-center">
                <Code2 className="h-5 w-5 text-black" />
              </div>
              <span className="label text-primary-container">Examples</span>
            </div>
            <h1 className="text-[clamp(40px,5vw,72px)] font-bold leading-[0.95] tracking-[-0.03em] text-on-surface">
              Examples
            </h1>
            <p className="mt-4 text-body-lg text-on-surface-variant max-w-lg">
              Explore real-world examples and starter templates. Copy, paste, and customize.
            </p>
          </motion.div>

          {/* Filter tabs */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className="mt-10 flex items-center gap-2 flex-wrap"
          >
            <Filter className="h-4 w-4 text-on-surface-variant mr-2" />
            {categories.map((cat) => (
              <button
                key={cat}
                onClick={() => setActive(cat)}
                className={`label px-4 py-2 border transition-all duration-200 ${
                  active === cat
                    ? "bg-primary-container text-black border-primary-container"
                    : "bg-transparent text-on-surface-variant border-outline hover:border-on-surface-variant"
                }`}
              >
                {cat}
              </button>
            ))}
          </motion.div>
        </div>
      </section>

      {/* Examples Grid */}
      <section className="py-16 bg-surface">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <AnimatePresence mode="wait">
            <motion.div
              key={active}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.3 }}
              className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 border-t border-l border-outline"
            >
              {filtered.map((example, i) => (
                <motion.div
                  key={example.title}
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.04 * i, duration: 0.4 }}
                  className={`border-b border-r border-outline p-0 group cursor-pointer flex flex-col ${
                    example.accent ? "bg-primary-container" : "bg-surface hover:bg-surface-container"
                  } transition-colors duration-300`}
                >
                  {/* Preview area */}
                  <div className={`h-44 flex items-center justify-center relative overflow-hidden ${
                    example.accent ? "border-b border-black/10" : "border-b border-outline"
                  }`}>
                    {/* Animated icon */}
                    <motion.div
                      whileHover={{ scale: 1.1, rotate: 5 }}
                      transition={{ type: "spring", stiffness: 300 }}
                    >
                      <example.icon className={`h-12 w-12 ${example.accent ? "text-black/30" : "text-outline"}`} />
                    </motion.div>
                    {/* Play button overlay */}
                    <div className={`absolute top-4 right-4 h-8 w-8 flex items-center justify-center border ${
                      example.accent ? "border-black/20 text-black/40 hover:bg-black/10" : "border-outline text-on-surface-variant hover:bg-surface-container-high"
                    } transition-colors`}>
                      <Play className="h-3.5 w-3.5" />
                    </div>
                  </div>

                  {/* Content */}
                  <div className="p-6 flex-1 flex flex-col">
                    <div className="flex items-center gap-2 mb-3">
                      <span className={`label ${example.accent ? "text-black/40" : "text-on-surface-variant"}`}>
                        {example.category.toUpperCase()}
                      </span>
                      <span className="text-[10px] text-on-surface-variant">•</span>
                      <span className={`text-[10px] font-mono ${difficultyColors[example.difficulty]}`}>
                        {example.difficulty}
                      </span>
                    </div>
                    <h3 className={`text-lg font-bold mb-2 ${example.accent ? "text-black" : "text-on-surface"}`}>
                      {example.title}
                    </h3>
                    <p className={`text-sm flex-1 ${example.accent ? "text-black/60" : "text-on-surface-variant"}`}>
                      {example.desc}
                    </p>
                    <div className="mt-4 flex items-center justify-between">
                      <span className={`font-mono text-xs ${example.accent ? "text-black/40" : "text-on-surface-variant"}`}>
                        {example.lines} lines
                      </span>
                      <ExternalLink className={`h-4 w-4 ${
                        example.accent ? "text-black/40 group-hover:text-black" : "text-on-surface-variant group-hover:text-primary-container"
                      } transition-colors`} />
                    </div>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          </AnimatePresence>
        </div>
      </section>

      <FooterSection />
    </main>
  );
}
