"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { ArrowRight } from "lucide-react";
import { useAuthStore } from "@/stores/auth";
import { ApiError } from "@/lib/api-client";

export default function MfaPage() {
  const router = useRouter();
  const completeMfa = useAuthStore((s) => s.completeMfa);
  const challengeToken = useAuthStore((s) => s.mfaChallengeToken);
  const [code, setCode] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!code.trim()) { setError("Enter your 6-digit code or backup code"); return; }
    if (!challengeToken) { setError("No MFA challenge pending. Please sign in again."); return; }
    setBusy(true);
    try {
      await completeMfa(code.trim());
      router.push("/dashboard");
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) setError("Invalid code. Try again.");
        else setError(err.message);
      } else setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />
      <section className="pt-32 pb-24">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} className="max-w-md mx-auto text-center">
            <div className="h-10 w-10 bg-primary-container flex items-center justify-center mx-auto mb-6">
              <span className="text-black font-bold text-lg">NF</span>
            </div>
            <h1 className="text-4xl font-bold text-on-surface mb-4">Two-factor authentication</h1>
            <p className="text-body-md text-on-surface-variant mb-8">Enter the code from your authenticator app or a backup code.</p>
            <div className="border border-outline bg-surface-container p-8 text-left">
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <BrutalInput label="MFA code" placeholder="123456 or backup code" value={code} onChange={(e) => setCode(e.target.value)} autoComplete="one-time-code" autoFocus />
                {error ? <p role="alert" className="text-sm text-error">{error}</p> : null}
                {!challengeToken ? <p className="text-sm text-error">No active MFA challenge. <a href="/auth/login" className="underline">Sign in again</a>.</p> : null}
                <BrutalButton variant="yellow" size="lg" fullWidth type="submit" disabled={busy || !challengeToken}>
                  {busy ? "Verifying…" : <>Verify <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </form>
              <p className="mt-6 text-sm text-center text-on-surface-variant">
                Lost access? Use a backup code or <a href="/auth/login" className="text-primary-container hover:text-on-surface">try again</a>.
              </p>
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
