"use client";

import { AnimatedBackground } from "@/components/landing/AnimatedBackground";
import { Navigation } from "@/components/landing/Navigation";
import { HeroSection } from "@/components/landing/HeroSection";
import { CapabilitiesSection } from "@/components/landing/CapabilitiesSection";
import { ArchitectureSection } from "@/components/landing/ArchitectureSection";
import { AIAgentsSection } from "@/components/landing/AIAgentsSection";
import { MetricsSection } from "@/components/landing/MetricsSection";
import { RepositorySection } from "@/components/landing/RepositorySection";
import { EnterpriseSection } from "@/components/landing/EnterpriseSection";
import { PricingSection } from "@/components/landing/PricingSection";
import { FooterSection } from "@/components/landing/FooterSection";

export default function LandingPage() {
  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <AnimatedBackground />
      <Navigation />
      <HeroSection />
      <CapabilitiesSection />
      <ArchitectureSection />
      <AIAgentsSection />
      <MetricsSection />
      <RepositorySection />
      <EnterpriseSection />
      <PricingSection />
      <FooterSection />
    </main>
  );
}
