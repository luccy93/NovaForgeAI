"use client";

import { type ReactNode } from "react";

export function BrutalErrorState({
  title = "Something went wrong",
  description,
  onRetry,
}: {
  title?: string;
  description?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="border border-error bg-surface p-8 text-center" role="alert">
      <p className="font-bold text-error">{title}</p>
      {description ? <p className="mt-2 text-sm text-on-surface-variant">{description}</p> : null}
      {onRetry ? (
        <div className="mt-4 flex justify-center">
          <RetryButton onRetry={onRetry} />
        </div>
      ) : null}
    </div>
  );
}

function RetryButton({ onRetry }: { onRetry: () => void }): ReactNode {
  return (
    <button
      type="button"
      onClick={onRetry}
      className="border border-outline px-4 py-2 font-mono text-xs uppercase tracking-widest text-on-surface hover:border-primary-container hover:text-primary-container"
    >
      Retry
    </button>
  );
}
