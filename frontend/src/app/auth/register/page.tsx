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

export default function RegisterPage() {
  const router = useRouter();
  const register = useAuthStore((s) => s.register);
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; username?: string; password?: string }>({});
  const [serverError, setServerError] = useState("");
  const [success, setSuccess] = useState(false);
  const [busy, setBusy] = useState(false);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!email.trim()) next.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = "Enter a valid email";
    if (!username.trim()) next.username = "Username is required";
    else if (!/^[a-zA-Z0-9_]+$/.test(username.trim())) next.username = "Letters, numbers and _ only";
    else if (username.trim().length < 2) next.username = "At least 2 characters";
    if (!password) next.password = "Password is required";
    else if (password.length < 8) next.password = "At least 8 characters";
    else if (password.length > 128) next.password = "At most 128 characters";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    setServerError("");
    setSuccess(false);
    if (!validate()) return;
    setBusy(true);
    try {
      await register(email.trim(), username.trim(), password);
      setSuccess(true);
      setTimeout(() => router.push("/dashboard"), 800);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 409) setServerError("An account with that email or username already exists");
        else if (err.status === 422) setServerError(err.message || "Please check your details");
        else if (err.status === 429) setServerError("Too many attempts. Try again later.");
        else setServerError(err.message);
      } else if (err instanceof Error) setServerError(err.message);
      else setServerError("Registration failed");
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
            <h1 className="text-4xl font-bold text-on-surface mb-4">Create your account</h1>
            <p className="text-body-md text-on-surface-variant mb-8">Start building with NovaForge AI in minutes.</p>
            <div className="border border-outline bg-surface-container p-8 text-left">
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <BrutalInput label="Email" type="email" placeholder="you@company.io" value={email} onChange={(e) => setEmail(e.target.value)} error={errors.email} autoComplete="email" autoFocus />
                <BrutalInput label="Username" placeholder="your_name" value={username} onChange={(e) => setUsername(e.target.value)} error={errors.username} autoComplete="username" />
                <BrutalInput label="Password" type="password" placeholder="At least 8 characters" value={password} onChange={(e) => setPassword(e.target.value)} error={errors.password} autoComplete="new-password" />
                {serverError ? <p role="alert" className="text-sm text-error">{serverError}</p> : null}
                {success ? <p role="status" className="text-sm text-primary-container">Account created — redirecting…</p> : null}
                <BrutalButton variant="yellow" size="lg" fullWidth type="submit" disabled={busy}>
                  {busy ? "Creating…" : <>Create Account <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </form>
              <p className="mt-6 text-sm text-on-surface-variant text-center">Already have an account? <a href="/auth/login" className="text-primary-container hover:text-on-surface transition-colors">Sign in</a></p>
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
