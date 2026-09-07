"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { BrutalInput } from "@/components/ui/BrutalInput";
import { ArrowRight } from "lucide-react";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api-client";

export default function ResetPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("token");
    // eslint-disable-next-line react-hooks/set-state-in-effect -- initialize from URL once
    if (t) setToken(t);
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (!token.trim()) { setError("Reset token is required"); return; }
    if (password.length < 8) { setError("Password must be at least 8 characters"); return; }
    if (password !== confirm) { setError("Passwords do not match"); return; }
    setBusy(true);
    try {
      await api.confirmPasswordReset(token.trim(), password);
      setSuccess(true);
      setTimeout(() => router.push("/auth/login"), 1200);
    } catch (err) {
      if (err instanceof ApiError) setError(err.message);
      else setError("Reset failed. Link may be expired.");
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
            <h1 className="text-4xl font-bold text-on-surface mb-4">Set new password</h1>
            <p className="text-body-md text-on-surface-variant mb-8">Enter your reset token and a new password.</p>
            <div className="border border-outline bg-surface-container p-8 text-left">
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <BrutalInput label="Reset token" placeholder="Paste token from email" value={token} onChange={(e) => setToken(e.target.value)} />
                <BrutalInput label="New password" type="password" placeholder="At least 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
                <BrutalInput label="Confirm password" type="password" value={confirm} onChange={(e) => setConfirm(e.target.value)} autoComplete="new-password" />
                {error ? <p role="alert" className="text-sm text-error">{error}</p> : null}
                {success ? <p role="status" className="text-sm text-primary-container">Password updated — redirecting to sign in…</p> : null}
                <BrutalButton variant="yellow" size="lg" fullWidth type="submit" disabled={busy}>
                  {busy ? "Updating…" : <>Update password <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </form>
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
