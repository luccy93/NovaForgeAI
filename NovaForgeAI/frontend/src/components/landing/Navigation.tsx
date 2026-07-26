"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";
import Link from "next/link";

const links = [
  { label: "DOCS", href: "/docs" },
  { label: "EXAMPLES", href: "/examples" },
  { label: "AI KIT", href: "/ai-kit" },
];

export function Navigation() {
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => {
    const handler = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", handler, { passive: true });
    return () => window.removeEventListener("scroll", handler);
  }, []);

  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: [0.25, 0.1, 0, 1] }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-primary-container/95 backdrop-blur-md border-b border-black/10"
          : "bg-primary-container"
      }`}
    >
      <div className="mx-auto flex max-w-[1400px] items-center justify-between py-3 px-6 lg:px-12">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-3 group">
          <svg width="32" height="24" viewBox="0 0 32 24" fill="none" className="text-black group-hover:scale-105 transition-transform duration-300">
            <rect x="0" y="2" width="6" height="22" fill="currentColor" />
            <polygon points="0,2 6,2 22,24 16,24" fill="currentColor" />
            <rect x="16" y="2" width="6" height="22" fill="currentColor" />
            <path d="M27 0 L31 4 L27 8 L23 4 Z" fill="currentColor" />
          </svg>
          <span className="text-xl font-bold text-black tracking-tight">NovaForge</span>
        </Link>

        {/* Center Links */}
        <div className="hidden md:flex items-center gap-8">
          {links.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className={`text-xs font-semibold tracking-[0.12em] transition-colors uppercase ${
                pathname === link.href
                  ? "text-black border-b-2 border-black pb-0.5"
                  : "text-black/70 hover:text-black"
              }`}
            >
              {link.label}
            </Link>
          ))}
        </div>

        {/* Right side */}
        <div className="hidden md:flex items-center gap-4">
          <button className="text-black/60 hover:text-black transition-colors" aria-label="Search">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
          </button>
          <Link
            href="/auth/register"
            className="bg-black text-primary-container px-5 py-2 text-xs font-bold tracking-[0.08em] uppercase hover:bg-black/80 transition-colors"
          >
            NOVAFORGE+
          </Link>
        </div>

        {/* Mobile Menu Button */}
        <button
          onClick={() => setMobileOpen(!mobileOpen)}
          className="md:hidden text-black"
          aria-label="Menu"
        >
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            {mobileOpen ? <path d="M6 18L18 6M6 6l12 12" /> : <path d="M4 6h16M4 12h16M4 18h16" />}
          </svg>
        </button>
      </div>

      {/* Mobile Menu */}
      <AnimatePresence>
        {mobileOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="md:hidden bg-primary-container border-t border-black/10 overflow-hidden"
          >
            <div className="px-6 py-6 flex flex-col gap-4">
              {links.map((link) => (
                <Link
                  key={link.href}
                  href={link.href}
                  onClick={() => setMobileOpen(false)}
                  className={`text-sm font-semibold uppercase tracking-widest py-2 transition-colors ${
                    pathname === link.href ? "text-black" : "text-black/70 hover:text-black"
                  }`}
                >
                  {link.label}
                </Link>
              ))}
              <hr className="border-black/10 my-2" />
              <Link
                href="/auth/register"
                className="bg-black text-primary-container px-5 py-3 text-center text-xs font-bold tracking-[0.08em] uppercase"
              >
                NOVAFORGE+
              </Link>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}
