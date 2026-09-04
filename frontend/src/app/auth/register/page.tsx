"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { ArrowRight } from "lucide-react";
import { api, setToken } from "@/lib/api";

const inputCls =
  "w-full border border-outline bg-surface px-4 py-3 text-body-md text-on-surface placeholder:text-on-surface-variant/50 outline-none focus:border-primary-container transition-colors";

export default function RegisterPage() {
  const [email, setEmail] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function onSubmit() {
    setError("");
    setBusy(true);
    try {
      const res = await api.register(email.trim(), username.trim(), password);
      setToken(res.access_token);
      window.location.href = "/dashboard";
    } catch (e) {
      setError(e instanceof Error ? e.message : "Registration failed");
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
            <div className="border border-outline bg-surface-container p-8">
              <div className="space-y-4">
                <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} />
                <input type="text" placeholder="Username (letters, numbers, _)" value={username} onChange={(e) => setUsername(e.target.value)} className={inputCls} />
                <input type="password" placeholder="Password (min 8 chars)" value={password} onChange={(e) => setPassword(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void onSubmit(); }} className={inputCls} />
                {error ? <p className="text-sm text-red-500 text-left">{error}</p> : null}
                <BrutalButton variant="yellow" size="lg" fullWidth onClick={() => { if (!busy) void onSubmit(); }}>
                  {busy ? "Creating…" : <>Create Account <ArrowRight className="h-4 w-4" /></>}
                </BrutalButton>
              </div>
              <p className="mt-6 text-sm text-on-surface-variant">Already have an account? <a href="/auth/login" className="text-primary-container hover:text-on-surface transition-colors">Sign in</a></p>
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
