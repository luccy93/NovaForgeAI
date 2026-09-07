"use client";

/* eslint-disable react-hooks/set-state-in-effect -- one-time verification status */

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Navigation } from "@/components/landing/Navigation";
import { FooterSection } from "@/components/landing/FooterSection";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api-client";

export default function VerifyPage() {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle");
  const [message, setMessage] = useState("");

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setStatus("error");
      setMessage("Missing verification token");
      return;
    }
    setStatus("loading");
    api.verifyEmail(token)
      .then(() => {
        setStatus("success");
        setMessage("Email verified. You can now sign in.");
      })
      .catch((err) => {
        setStatus("error");
        setMessage(err instanceof ApiError ? err.message : "Verification failed");
      });
  }, []);

  return (
    <main className="relative min-h-screen bg-surface overflow-hidden">
      <Navigation />
      <section className="pt-32 pb-24">
        <div className="mx-auto max-w-[1400px] px-6 lg:px-12">
          <motion.div initial={{ opacity: 0, y: 30 }} animate={{ opacity: 1, y: 0 }} className="max-w-md mx-auto text-center">
            <div className="h-10 w-10 bg-primary-container flex items-center justify-center mx-auto mb-6">
              <span className="text-black font-bold text-lg">NF</span>
            </div>
            <h1 className="text-4xl font-bold text-on-surface mb-4">Email verification</h1>
            <div className="border border-outline bg-surface-container p-8">
              {status === "loading" ? <p className="text-on-surface-variant">Verifying…</p> : null}
              {status === "success" ? <p role="status" className="text-sm text-primary-container">{message}</p> : null}
              {status === "error" ? <p role="alert" className="text-sm text-error">{message}</p> : null}
              {status !== "loading" ? (
                <div className="mt-6">
                  <BrutalButton href="/auth/login" variant="yellow" size="lg" fullWidth>Go to sign in</BrutalButton>
                </div>
              ) : null}
            </div>
          </motion.div>
        </div>
      </section>
      <FooterSection />
    </main>
  );
}
