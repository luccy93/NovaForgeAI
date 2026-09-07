"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api-client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setSuccess(false);
    if (!email.trim() || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("Enter a valid email");
      return;
    }
    setBusy(true);
    try {
      await api.requestPasswordReset(email.trim());
      setSuccess(true);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Unable to send reset link. Try again.");
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
            <h1 className="text-4xl font-bold text-on-surface mb-4">Reset password</h1>
            <p className="text-body-md text-on-surface-variant mb-8">We&apos;ll send a reset link if the account exists.</p>
            <div className="border border-outline bg-surface-container p-8 text-left">
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <BrutalInput label="Email" type="email" placeholder="you@company.io" value={email} onChange={(e) => setEmail(e.target.value)} error={error} autoComplete="email" autoFocus />
                {success ? <p role="status" className="text-sm text-primary-container">If the email exists, a reset link has been sent.</p> : null}
                <BrutalButton variant="yellow" size="lg" fullWidth type="submit" disabled={busy}>
                  {busy ? "Sending…" : <>Send reset link <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </form>
              <p className="mt-6 text-sm text-center text-on-surface-variant">
                <a href="/auth/login" className="text-primary-container hover:text-on-surface">Back to sign in</a>
              </p>
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
