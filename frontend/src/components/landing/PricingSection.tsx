"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { fadeUp, staggerContainer } from "@/lib/animations";
import { Check, ArrowRight } from "lucide-react";

const plans = [
  {
    name: "Free",
    price: "$0",
    desc: "Self-hosted. Full access. MIT license.",
    features: ["All 5 AI agents", "RAG pipeline (chat + search)", "Code analysis (AST parser)", "Plugin system", "Community support"],
    cta: "Get Started",
    variant: "default" as const,
    href: "/auth/register",
  },
  {
    name: "Pro",
    price: "$29",
    period: "/month",
    desc: "Managed hosting with no infrastructure setup.",
    features: ["Unlimited repos", "Unlimited agent queries", "Hosted Neo4j + Qdrant", "Automatic updates", "Priority support"],
    cta: "Start Trial",
    variant: "yellow" as const,
    featured: true,
    href: "/auth/register",
  },
  {
    name: "Enterprise",
    price: "$99",
    period: "/month",
    desc: "Dedicated deployment with SLA and support.",
    features: ["Everything in Pro", "SSO / SAML", "Audit logs", "Custom agents", "Dedicated support"],
    cta: "Contact Sales",
    variant: "default" as const,
    href: "#",
  },
];

export function PricingSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const opacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);

  return (
    <section id="pricing" ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-[#0a0a0a] border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
        <motion.div style={{ opacity }} className="text-center mb-24 max-w-2xl mx-auto">
          <div className="inline-flex items-center gap-2 border border-white/20 bg-[#151515] px-3 py-1 mb-8">
            <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">08 / Pricing</span>
          </div>
          <h2 className="text-[clamp(32px,4vw,56px)] font-bold tracking-tight text-white leading-tight">
            Simple pricing.
            <br />
            <span className="text-white/40">No surprises.</span>
          </h2>
        </motion.div>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          whileInView="visible"
          viewport={{ once: true, margin: "-100px" }}
          className="grid grid-cols-1 md:grid-cols-3 max-w-5xl mx-auto border-t border-l border-white/10 bg-[#0f0f0f]"
        >
          {plans.map((plan) => (
            <motion.div
              key={plan.name}
              variants={fadeUp}
              className={`border-b border-r border-white/10 p-10 flex flex-col ${
                plan.featured ? "bg-primary-container relative z-10 scale-[1.02] shadow-2xl" : "bg-[#0f0f0f] hover:bg-[#151515] transition-colors"
              }`}
            >
              <h3 className={`text-2xl font-bold tracking-tight ${plan.featured ? "text-black" : "text-white"}`}>
                {plan.name}
              </h3>
              <div className="mt-6 flex items-baseline gap-1">
                <span className={`text-[64px] leading-none font-bold tracking-tighter ${
                  plan.featured ? "text-black" : "text-primary-container"
                }`}>
                  {plan.price}
                </span>
                {plan.period && (
                  <span className={`font-mono text-xs uppercase tracking-widest ${plan.featured ? "text-black/50" : "text-white/40"}`}>
                    {plan.period}
                  </span>
                )}
              </div>
              <p className={`mt-4 text-sm leading-relaxed ${plan.featured ? "text-black/70" : "text-white/60"}`}>
                {plan.desc}
              </p>
              
              <div className={`mt-8 mb-8 h-px w-full ${plan.featured ? "bg-black/10" : "bg-white/10"}`} />
              
              <ul className="space-y-4 flex-1">
                {plan.features.map((f) => (
                  <li
                    key={f}
                    className={`flex items-start gap-4 text-sm ${
                      plan.featured ? "text-black" : "text-white/80"
                    }`}
                  >
                    <Check className={`h-4 w-4 mt-0.5 shrink-0 ${
                      plan.featured ? "text-black" : "text-primary-container"
                    }`} />
                    {f}
                  </li>
                ))}
              </ul>
              
              <div className="mt-10">
                {plan.featured ? (
                  <a
                    href={plan.href}
                    className="flex items-center justify-center gap-3 bg-black text-primary-container px-8 py-4 text-sm font-bold tracking-widest uppercase hover:bg-black/80 transition-colors w-full group"
                  >
                    {plan.cta} <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
                  </a>
                ) : (
                  <a
                    href={plan.href}
                    className="flex items-center justify-center gap-3 border border-white/20 bg-[#151515] text-white px-8 py-4 text-sm font-bold tracking-widest uppercase hover:bg-white hover:text-black transition-colors w-full group"
                  >
                    {plan.cta} <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform opacity-0 group-hover:opacity-100 -ml-7 group-hover:ml-0" />
                  </a>
                )}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </div>
    </section>
  );
}
