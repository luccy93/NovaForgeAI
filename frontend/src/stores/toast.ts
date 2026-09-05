"use client";

import { create } from "zustand";

export type ToastTone = "success" | "warning" | "error" | "info";

export interface Toast {
  id: string;
  tone: ToastTone;
  message: string;
}

interface ToastState {
  toasts: Array<Toast>;
  push: (tone: ToastTone, message: string) => void;
  dismiss: (id: string) => void;
}

let counter = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (tone, message) => {
    counter += 1;
    const id = `toast-${Date.now()}-${counter}`;
    set((state) => ({ toasts: [...state.toasts.slice(-4), { id, tone, message }] }));
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
    }, 5000);
  },
  dismiss: (id) =>
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
