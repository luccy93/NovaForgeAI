"use client";

import { Globe, MessageCircle, Briefcase, Mail, ArrowUp } from "lucide-react";

const footerGroups = [
  { label: "Product", links: ["Features", "Pricing", "Documentation", "Changelog", "API Reference"] },
  { label: "Company", links: ["About", "Blog", "Careers", "Press Kit", "Contact"] },
  { label: "Legal", links: ["Privacy Policy", "Terms of Service", "Cookie Policy", "GDPR", "SOC 2"] },
  { label: "Resources", links: ["Help Center", "Community", "Status", "Tutorials", "Integrations"] },
];

const socialLinks = [
  { icon: Globe, href: "#" },
  { icon: MessageCircle, href: "#" },
  { icon: Briefcase, href: "#" },
  { icon: Mail, href: "#" },
];

export function FooterSection() {
  const scrollToTop = () => { window.scrollTo({ top: 0, behavior: "smooth" }); };

  return (
    <footer className="relative border-t border-white/10 bg-[#0f0f0f]">
      <div className="mx-auto max-w-[1400px] px-6 lg:px-12 py-20">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-12 lg:gap-16">
          <div className="col-span-2 md:col-span-1">
            <div className="flex items-center gap-3">
              <svg width="32" height="24" viewBox="0 0 32 24" fill="none" className="text-white">
                <rect x="0" y="2" width="6" height="22" fill="currentColor" />
                <polygon points="0,2 6,2 22,24 16,24" fill="currentColor" />
                <rect x="16" y="2" width="6" height="22" fill="currentColor" />
                <path d="M27 0 L31 4 L27 8 L23 4 Z" fill="currentColor" />
              </svg>
              <span className="text-xl font-bold text-white tracking-tight">NovaForge</span>
            </div>
            <p className="mt-6 text-sm text-white/50 leading-relaxed max-w-xs font-mono">
              Navigate your codebase in 3D space. Understand architecture visually. Ship faster with AI agents.
            </p>
            <div className="flex gap-3 mt-8">
              {socialLinks.map((s, i) => (
                <a
                  key={i}
                  href={s.href}
                  className="h-10 w-10 border border-white/20 flex items-center justify-center hover:bg-primary-container hover:text-black hover:border-primary-container transition-colors duration-200"
                >
                  <s.icon className="h-4 w-4 text-white hover:text-black" />
                </a>
              ))}
            </div>
          </div>
          
          {footerGroups.map((group) => (
            <div key={group.label} className="pt-2">
              <h4 className="font-mono text-xs font-bold text-white uppercase tracking-widest mb-6">{group.label}</h4>
              <ul className="space-y-4">
                {group.links.map((link) => (
                  <li key={link}>
                    <a href="#" className="text-sm text-white/60 hover:text-primary-container transition-colors">
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="mt-20 pt-8 border-t border-white/10 flex flex-col md:flex-row items-center justify-between gap-6">
          <p className="font-mono text-xs text-white/40 uppercase tracking-widest">© 2025 NovaForge. All rights reserved.</p>
          <div className="flex items-center gap-2">
            <span className="h-2 w-2 bg-primary-container" />
            <p className="font-mono text-xs text-white/40 uppercase tracking-widest">
              Built with AI for engineers who build the future.
            </p>
          </div>
        </div>
      </div>

      {/* Back to top */}
      <button
        onClick={scrollToTop}
        className="fixed bottom-8 right-8 h-12 w-12 border border-white/20 bg-[#151515] flex items-center justify-center hover:bg-primary-container hover:text-black hover:border-primary-container transition-colors duration-200 z-50 shadow-2xl group"
      >
        <ArrowUp className="h-5 w-5 text-white group-hover:text-black transition-colors" />
      </button>
    </footer>
  );
}
