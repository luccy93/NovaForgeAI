"use client";

import { useEffect } from "react";
import { BrutalButton } from "@/components/ui/BrutalButton";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log to monitoring if available, but never expose raw stack to UI
  }, [error]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-surface p-6">
      <div className="w-full max-w-lg border border-error bg-surface p-8 text-center">
        <p className="font-mono text-xs uppercase tracking-widest text-error">Unexpected error</p>
        <h1 className="mt-2 text-2xl font-bold text-on-surface">Something went wrong</h1>
        <p className="mt-3 text-sm text-on-surface-variant">An unexpected error occurred. Your session and data remain safe. Try again or return to your workspace.</p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <BrutalButton variant="yellow" size="sm" onClick={() => reset()}>
            Retry
          </BrutalButton>
          <BrutalButton variant="ghost" size="sm" href="/dashboard">
            Go to Dashboard
          </BrutalButton>
        </div>
      </div>
    </main>
  );
}
