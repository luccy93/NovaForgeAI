"use client";

import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import {
  Brain, Search, Shield, TestTube, FileText, Rocket,
  ArrowRight, Cpu, MessageSquare, Workflow, Zap,
  Plug, Settings, BarChart3, Code2, Sparkles,
  CheckCircle, GitPullRequest, Bug, Eye,
} from "lucide-react";

const agents = [
  {
    icon: Brain,
    name: "Planner Agent",
    desc: "Analyzes requirements and generates multi-step implementation plans. Breaks complex tasks into atomic operations across your codebase.",
    capabilities: ["Task decomposition", "Dependency analysis", "Execution planning", "Risk assessment"],
    status: "Stable",
  },
  {
    icon: Eye,
    name: "Reviewer Agent",
    desc: "Code review with full architectural awareness. Catches logic errors, security issues, performance problems, and style violations.",
    capabilities: ["PR review", "Architecture validation", "Pattern detection", "Auto-suggestions"],
    status: "Stable",
  },
  {
    icon: Shield,
    name: "Security Agent",
    desc: "Real-time vulnerability scanning. Detects OWASP Top 10, secrets leakage, dependency risks, and supply chain attacks.",
    capabilities: ["OWASP scanning", "Secrets detection", "Dependency audit", "Threat modeling"],
    status: "Stable",
  },
  {
    icon: TestTube,
    name: "Testing Agent",
    desc: "Generates unit, integration, and E2E tests. Achieves 90%+ coverage automatically with meaningful assertions.",
    capabilities: ["Unit tests", "Integration tests", "E2E tests", "Coverage analysis"],
    status: "Stable",
  },
  {
    icon: FileText,
    name: "Documentation Agent",
    desc: "Generates and maintains living documentation. API docs, README files, architecture diagrams — always in sync.",
    capabilities: ["API docs", "README generation", "Architecture diagrams", "Changelog"],
    status: "Beta",
  },
  {
    icon: Rocket,
    name: "Deployment Agent",
    desc: "Manages CI/CD pipelines, containerization, and infrastructure as code. From Dockerfile to Kubernetes manifests.",
    capabilities: ["CI/CD setup", "Docker", "Kubernetes", "IaC templates"],
    status: "Beta",
  },
];

const tools = [
  { icon: Code2, name: "Code Analysis", desc: "Static analysis, AST parsing, and complexity metrics" },
  { icon: Search, name: "Semantic Search", desc: "Natural language code search across your repository" },
  { icon: GitPullRequest, name: "PR Automation", desc: "Automated PR creation, review, and merge" },
  { icon: Bug, name: "Bug Detection", desc: "AI-powered bug detection and root cause analysis" },
  { icon: Workflow, name: "Workflow Engine", desc: "Define custom multi-agent workflows in YAML" },
  { icon: Plug, name: "Plugin System", desc: "Extend agents with custom tools and integrations" },
  { icon: MessageSquare, name: "Chat Interface", desc: "Natural language interaction with your codebase" },
  { icon: BarChart3, name: "Analytics", desc: "Agent performance metrics and usage dashboards" },
];

const codeExample = `import { AgentMesh } from '@novaforge/ai-kit'

const mesh = new AgentMesh({
  agents: ['planner', 'reviewer', 'security', 'testing'],
  mode: 'collaborative',
  consensus: 'majority',
})

// Run a coordinated code review
const result = await mesh.review({
  pr: '#42',
  depth: 'architectural',
  autoFix: true,
})

console.log(result.summary)
// → "3 issues found, 2 auto-fixed, 1 needs review"`;

export default function AIKitPage() {
  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />

      {/* Hero */}
      <section className="relative pt-28 pb-20 overflow-hidden">
        {/* Gradient accent */}
        <div className="absolute top-0 right-0 w-1/2 h-full bg-gradient-to-l from-primary-container/10 via-transparent to-transparent pointer-events-none" />

        <div className="mx-auto max-w-[1400px] px-6 lg:px-12 relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6 }}
          >
            <div className="flex items-center gap-3 mb-6">
              <div className="h-10 w-10 bg-primary-container flex items-center justify-center">
                <Sparkles className="h-5 w-5 text-black" />
              </div>
              <span className="label text-primary-container">AI Kit</span>
            </div>
            <h1 className="text-[clamp(40px,5vw,72px)] font-bold leading-[0.95] tracking-[-0.03em] text-on-surface">
              AI Kit
            </h1>
            <p className="mt-4 text-body-lg text-on-surface-variant max-w-lg">
              Six specialized AI agents working as a unified intelligence.
              Orchestrate, customize, and deploy AI-powered code workflows.
            </p>
            <div className="mt-8 flex gap-4">
              <BrutalButton href="#" variant="yellow" size="lg">
                Get Started <ArrowRight className="h-4 w-4" />
              </BrutalButton>
              <BrutalButton href="#" variant="ghost" size="lg">
                View on GitHub
              </BrutalButton>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Agents Grid */}
      <section className="py-20 bg-surface border-t border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <span className="label text-primary-container">Agents</span>
          <h2 className="mt-4 text-3xl font-bold text-on-surface">Meet the agents</h2>
          <p className="mt-2 text-body-md text-on-surface-variant max-w-lg">
            Each agent is specialized for a specific domain but collaborates with others through the Agent Mesh.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 border-t border-l border-outline mt-10">
            {agents.map((agent, i) => (
              <motion.div
                key={agent.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: 0.05 * i, duration: 0.5 }}
                className="border-b border-r border-outline p-8 group hover:bg-surface-container transition-colors duration-300"
              >
                {/* Header */}
                <div className="flex items-center justify-between mb-5">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 border border-primary-container flex items-center justify-center group-hover:bg-primary-container group-hover:text-black transition-colors">
                      <agent.icon className="h-5 w-5 text-primary-container group-hover:text-black transition-colors" />
                    </div>
                    <h3 className="text-lg font-bold text-on-surface">{agent.name}</h3>
                  </div>
                  <span className={`label text-[10px] px-2 py-0.5 border ${
                    agent.status === "Stable"
                      ? "text-green-400 border-green-400/30"
                      : "text-primary-container border-primary-container/30"
                  }`}>
                    {agent.status}
                  </span>
                </div>

                {/* Description */}
                <p className="text-sm text-on-surface-variant leading-relaxed mb-5">{agent.desc}</p>

                {/* Capabilities */}
                <div className="space-y-2">
                  {agent.capabilities.map((cap) => (
                    <div key={cap} className="flex items-center gap-2">
                      <CheckCircle className="h-3.5 w-3.5 text-primary-container shrink-0" />
                      <span className="text-xs text-on-surface-variant">{cap}</span>
                    </div>
                  ))}
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Code Example + Tools */}
      <section className="py-20 bg-surface-dim border-t border-outline">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-16">
            {/* Code example */}
            <div>
              <span className="label text-primary-container">Quick Start</span>
              <h2 className="mt-4 text-3xl font-bold text-on-surface mb-8">Simple, powerful API</h2>

              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                className="border border-outline bg-surface-container-low"
              >
                {/* Terminal header */}
                <div className="flex items-center gap-2 px-6 py-3 border-b border-outline">
                  <div className="flex gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-on-surface-variant/20" />
                    <span className="w-2.5 h-2.5 rounded-full bg-on-surface-variant/20" />
                    <span className="w-2.5 h-2.5 rounded-full bg-on-surface-variant/20" />
                  </div>
                  <span className="label text-on-surface-variant ml-4">agent-mesh.ts</span>
                </div>
                {/* Code */}
                <pre className="p-6 font-mono text-sm leading-7 text-on-surface-variant overflow-x-auto">
                  {codeExample.split("\n").map((line, i) => (
                    <div key={i} className="flex gap-4">
                      <span className="text-on-surface-variant/20 w-5 text-right select-none text-xs leading-7">
                        {i + 1}
                      </span>
                      <span>
                        {line.includes("'") ? (
                          line.split("'").map((part, pi, arr) =>
                            pi < arr.length - 1 ? (
                              <span key={pi}>
                                {part}<span className="text-primary-container">&apos;</span>
                              </span>
                            ) : (
                              <span key={pi}>{part}</span>
                            )
                          )
                        ) : line.includes("//") ? (
                          <span className="text-on-surface-variant/40">{line}</span>
                        ) : (
                          line
                        )}
                      </span>
                    </div>
                  ))}
                </pre>
              </motion.div>
            </div>

            {/* Tools grid */}
            <div>
              <span className="label text-primary-container">Built-in Tools</span>
              <h2 className="mt-4 text-3xl font-bold text-on-surface mb-8">Everything agents need</h2>

              <div className="grid grid-cols-2 border-t border-l border-outline">
                {tools.map((tool, i) => (
                  <motion.div
                    key={tool.name}
                    initial={{ opacity: 0, y: 10 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: 0.04 * i }}
                    className="border-b border-r border-outline p-5 group hover:bg-surface-container transition-colors duration-300"
                  >
                    <tool.icon className="h-5 w-5 text-primary-container mb-3" />
                    <h4 className="text-sm font-bold text-on-surface mb-1">{tool.name}</h4>
                    <p className="text-xs text-on-surface-variant">{tool.desc}</p>
                  </motion.div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Architecture Banner */}
      <section className="py-20 bg-primary-container">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12 text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
          >
            <Cpu className="h-10 w-10 text-black mx-auto mb-6" />
            <h2 className="text-4xl font-bold text-black mb-4">
              Ready to build with AI agents?
            </h2>
            <p className="text-body-lg text-black/60 max-w-md mx-auto mb-8">
              Start with our free tier. Upgrade when you need more agents, repos, or enterprise features.
            </p>
            <div className="flex justify-center gap-4">
              <a
                href="/auth/register"
                className="bg-black text-primary-container px-10 py-4 text-sm font-bold tracking-[0.05em] uppercase hover:bg-black/80 transition-colors inline-flex items-center gap-2"
              >
                Get Started Free <ArrowRight className="h-4 w-4" />
              </a>
            </div>
          </motion.div>
        </div>
      </section>

      <FooterSection />
    </main>
  );
}
