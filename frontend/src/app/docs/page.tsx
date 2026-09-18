"use client";

import { DocsOverview } from "@/components/docs/DocsOverview";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";

export default function DocsPage() {
  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />
      <div className="mx-auto w-full max-w-[1600px] px-4 py-6 lg:px-6 pt-28">
        <div className="border-b border-outline bg-surface px-4 py-4 mb-6">
          <h1 className="font-mono text-xs uppercase tracking-widest text-primary-container">NovaForge Documentation</h1>
          <p className="text-sm text-on-surface-variant">Search documentation · Public · versioned · server-authoritative</p>
        </div>
        <DocsOverview />
      </div>
      <FooterSection />
    </main>
  );
}
