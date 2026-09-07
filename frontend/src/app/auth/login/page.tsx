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

function safeNext(value: string | null): string {
  if (!value) return "/dashboard";
  if (!value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  return value;
}

export default function LoginPage() {
  const router = useRouter();
  const login = useAuthStore((s) => s.login);
  const status = useAuthStore((s) => s.status);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [serverError, setServerError] = useState("");
  const [busy, setBusy] = useState(false);

  const nextUrl = safeNext(typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("next") : null);

  function validate(): boolean {
    const next: typeof errors = {};
    if (!email.trim()) next.email = "Email is required";
    else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) next.email = "Enter a valid email";
    if (!password) next.password = "Password is required";
    setErrors(next);
    return Object.keys(next).length === 0;
  }

  async function onSubmit(e?: React.FormEvent) {
    e?.preventDefault();
    setServerError("");
    if (!validate()) return;
    setBusy(true);
    try {
      const result = await login(email.trim(), password);
      if (result === "mfa_required") {
        router.push("/auth/mfa");
        return;
      }
      router.push(nextUrl);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) setServerError("Invalid email or password");
        else if (err.status === 423) setServerError(err.message || "Account is locked. Try again later.");
        else if (err.status === 429) setServerError("Too many attempts. Please wait and try again.");
        else setServerError(err.message);
      } else if (err instanceof Error) {
        setServerError(err.message);
      } else {
        setServerError("Sign in failed. Please try again.");
      }
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
            <h1 className="text-4xl font-bold text-on-surface mb-4">Welcome back</h1>
            <p className="text-body-md text-on-surface-variant mb-8">Sign in to your NovaForge account.</p>
            <div className="border border-outline bg-surface-container p-8 text-left">
              <form onSubmit={onSubmit} noValidate className="space-y-4">
                <BrutalInput
                  label="Email"
                  type="email"
                  placeholder="you@company.io"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  error={errors.email}
                  autoComplete="email"
                  autoFocus
                />
                <BrutalInput
                  label="Password"
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  error={errors.password}
                  autoComplete="current-password"
                />
                {serverError ? (
                  <p role="alert" className="text-sm text-error">
                    {serverError}
                  </p>
                ) : null}
                <BrutalButton variant="yellow" size="lg" fullWidth type="submit" disabled={busy}>
                  {busy ? "Signing in…" : <>Sign In <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </form>
              <div className="mt-6 flex justify-between text-sm">
                <a href="/auth/forgot-password" className="text-on-surface-variant hover:text-primary-container transition-colors">
                  Forgot password?
                </a>
                <a href="/auth/register" className="text-primary-container hover:text-on-surface transition-colors">
                  Create account
                </a>
              </div>
              {status === "expired" ? (
                <p className="mt-4 text-sm text-error" role="status">
                  Session expired. Please sign in again.
                </p>
              ) : null}
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
