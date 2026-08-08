"use client";

import { useRef } from "react";
import { motion, useScroll, useTransform } from "framer-motion";
import { ArrowRight, Shield } from "lucide-react";

const features = [
  { label: "SOC 2 Type II", desc: "Certified annually with continuous monitoring" },
  { label: "SSO / SAML", desc: "Okta, Azure AD, Google Workspace, and more" },
  { label: "RBAC", desc: "Granular permissions down to the function level" },
  { label: "Audit Logs", desc: "Complete audit trail with 1-year retention" },
  { label: "GDPR", desc: "Full compliance with data residency controls" },
  { label: "HIPAA", desc: "BAAs available for healthcare customers" },
  { label: "Encryption", desc: "AES-256 at rest, TLS 1.3 in transit" },
  { label: "Uptime SLA", desc: "99.99% uptime guarantee with 24/7 support" },
];

export function EnterpriseSection() {
  const ref = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const opacity = useTransform(scrollYProgress, [0, 0.2], [0, 1]);

  return (
    <section ref={ref} className="relative py-32 lg:py-48 overflow-hidden bg-[#0a0a0a] border-t border-white/10">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12 relative z-10">
        <motion.div style={{ opacity }} className="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24 items-start">
          {/* Left content */}
          <div>
            <div className="inline-flex items-center gap-2 border border-white/20 bg-[#151515] px-3 py-1 mb-8">
              <span className="font-mono text-xs font-bold text-primary-container uppercase tracking-widest">06 / Enterprise Security</span>
            </div>
            <h2 className="text-[clamp(32px,4vw,56px)] font-bold tracking-tight text-white leading-tight">
              Security you can
              <br />
              <span className="text-white/40">build your business on.</span>
            </h2>
            <p className="mt-6 text-lg text-white/60 leading-relaxed max-w-md">
              From startups to Fortune 500, NovaForge meets the highest standards of security and compliance.
            </p>
            <div className="mt-12">
              <a href="#pricing" className="inline-flex items-center gap-4 bg-primary-container text-black px-8 py-4 hover:bg-white hover:text-black transition-colors group">
                <span className="font-mono text-sm uppercase tracking-widest font-bold">View Enterprise Plans</span>
                <ArrowRight className="h-4 w-4 group-hover:translate-x-1 transition-transform" />
              </a>
            </div>
          </div>

          {/* Right — security grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 border-t border-l border-white/10 bg-[#0f0f0f]">
            {features.map((f) => (
              <div key={f.label} className="border-b border-r border-white/10 p-8 hover:bg-[#151515] transition-colors duration-300 group">
                <div className="flex items-center gap-3 mb-3">
                  <Shield className="h-4 w-4 text-white/40 group-hover:text-primary-container transition-colors" />
                  <span className="text-lg font-bold text-white group-hover:text-primary-container transition-colors">{f.label}</span>
                </div>
                <p className="text-sm text-white/50 leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  );
}
