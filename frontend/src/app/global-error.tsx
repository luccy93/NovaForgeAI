"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-surface p-6 flex items-center justify-center">
        <div className="w-full max-w-lg border border-error bg-surface p-8 text-center">
          <p className="font-mono text-xs uppercase tracking-widest text-error">Application error</p>
          <h1 className="mt-2 text-2xl font-bold text-white">Something went wrong</h1>
          <p className="mt-3 text-sm text-on-surface-variant">An unexpected error occurred. Please try again.</p>
          <button
            type="button"
            onClick={() => reset()}
            className="mt-6 border border-outline bg-surface px-4 py-2 font-mono text-xs uppercase tracking-widest hover:border-primary-container"
          >
            Retry
          </button>
        </div>
      </body>
    </html>
  );
}
