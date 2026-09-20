"use client";

import { useToastStore, type ToastTone } from "@/stores/toast";
import { cn } from "@/lib/utils";

const tones: Record<ToastTone, string> = {
  success: "border-primary-container text-on-surface",
  warning: "border-primary-container text-primary-container",
  error: "border-error text-error",
  info: "border-outline text-on-surface",
};

export function Toasts() {
  const toasts = useToastStore((state) => state.toasts);
  const dismiss = useToastStore((state) => state.dismiss);
  const hasError = toasts.some((toast) => toast.tone === "error");
  return (
    <div
      aria-live={hasError ? "assertive" : "polite"}
      aria-atomic="false"
      aria-relevant="additions text"
      className="pointer-events-none fixed bottom-4 right-4 z-[90] flex w-80 flex-col gap-2"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          role={toast.tone === "error" ? "alert" : "status"}
          className={cn("pointer-events-auto border bg-black p-3 text-sm", tones[toast.tone])}
        >
          <div className="flex items-start justify-between gap-2">
            <p>{toast.message}</p>
            <button
              type="button"
              aria-label="Dismiss notification"
              onClick={() => dismiss(toast.id)}
              className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center font-mono text-xs text-on-surface-variant hover:text-on-surface focus-visible:outline-2 focus-visible:outline-primary-container focus-visible:outline-offset-2"
            >
              <span aria-hidden="true">✕</span>
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
