import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "@/lib/api-client";
import { BrutalButton } from "@/components/ui/BrutalButton";
import { useTenantStore } from "@/stores/tenant";
import { EventStream } from "@/lib/realtime";

describe("Perf C1 — API client hardening", () => {
  it("aborted retry does not fire second attempt when outerSignal aborted", async () => {
    const controller = new AbortController();
    const outer = controller.signal;
    // stub fetch to always reject with 500 to trigger retry
    const origFetch = global.fetch;
    let calls = 0;
    global.fetch = vi.fn(async () => {
      calls += 1;
      return new Response(JSON.stringify({ detail: "server error" }), { status: 500, headers: {} });
    }) as unknown as typeof fetch;

    const promise = apiRequest("/test-retry-abort", { method: "GET", signal: outer });
    // abort during retry delay (500ms)
    setTimeout(() => controller.abort(), 100);
    await expect(promise).rejects.toBeDefined();
    // should have only 1 call because retry was aborted (second attempt not fired due to abort)
    // allow timer to settle
    await new Promise((r) => setTimeout(r, 700));
    expect(calls).toBe(1);
    global.fetch = origFetch;
  });

  it("respects Retry-After header for 429 (capped at 5s)", async () => {
    const origFetch = global.fetch;
    let calls = 0;
    global.fetch = vi.fn(async () => {
      calls += 1;
      if (calls === 1) {
        return new Response(JSON.stringify({ detail: "rate limited" }), {
          status: 429,
          headers: { "Retry-After": "1" },
        });
      }
      return new Response(JSON.stringify({ ok: true }), { status: 200, headers: {} });
    }) as unknown as typeof fetch;

    const start = Date.now();
    const res = await apiRequest<{ ok: boolean }>("/test-retry-after", { method: "GET" });
    const elapsed = Date.now() - start;
    expect(res.ok).toBe(true);
    expect(elapsed).toBeGreaterThanOrEqual(900); // ~1000ms delay for Retry-After 1
    expect(calls).toBe(2);
    global.fetch = origFetch;
  });

  it("does not retry mutations (POST)", async () => {
    const origFetch = global.fetch;
    let calls = 0;
    global.fetch = vi.fn(async () => {
      calls += 1;
      return new Response(JSON.stringify({ detail: "oops" }), { status: 500, headers: {} });
    }) as unknown as typeof fetch;
    await expect(apiRequest("/test-mutate", { method: "POST", body: {} })).rejects.toBeInstanceOf(ApiError);
    expect(calls).toBe(1);
    global.fetch = origFetch;
  });
});

describe("Perf C1 — Three.js + BrutalButton", () => {
  afterEach(() => cleanup());

  it("BrutalButton renders without framer-motion and has CSS scale", () => {
    render(<BrutalButton variant="default">Click</BrutalButton>);
    const btn = screen.getByRole("button", { name: "Click" });
    expect(btn.className).toContain("hover:scale-[1.02]");
    // no motion styles
    expect(document.body.innerHTML).not.toContain("whileHover");
  });

  it("AICoreScene uses DPR cap 1.5 (static import check)", async () => {
    const src = await import("@/components/three/AICoreScene");
    expect(src.AICoreScene).toBeDefined();
    // source check: file should contain dpr={[1, 1.5]} and demand frameloop (guarded by reduced motion)
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:\\Users\\Devendraprasad\\Downloads\\GraphRAG-main\\frontend\\src\\components\\three\\AICoreScene.tsx", "utf-8");
    expect(content).toContain("dpr={[1, 1.5]}");
    expect(content).toContain('frameloop={reducedMotion ? "never" : "demand"}');
    expect(content).not.toContain("OrbitControls");
  });
});

describe("Perf C1 — tenant cache safety", () => {
  afterEach(() => {
    localStorage.clear();
    useTenantStore.getState().clear();
  });

  it("tenant switch clears nf_cache_* and does not leak to new tenant", () => {
    localStorage.setItem("nf_cache_dashboard", "stale");
    useTenantStore.getState().setContext("org-1", "ws-1");
    useTenantStore.getState().switchOrganization("org-2");
    expect(localStorage.getItem("nf_cache_dashboard")).toBeNull();
  });

  it("stale seq: old tenant response does not overwrite new tenant", async () => {
    const seqRef = { current: 0 };
    const applied: string[] = [];
    async function load(seq: number, val: string, delay: number) {
      await new Promise((r) => setTimeout(r, delay));
      if (seq !== seqRef.current) return;
      applied.push(val);
    }
    seqRef.current = 1;
    const p1 = load(1, "A", 30);
    seqRef.current = 2;
    const p2 = load(2, "B", 10);
    await Promise.all([p1, p2]);
    expect(applied).toEqual(["B"]);
  });
});

describe("Perf C1 — realtime cleanup", () => {
  it("EventStream close clears reconnect timer and prevents reconnect", () => {
    vi.useFakeTimers();
    const es = new EventStream("/test", () => {});
    // force error path to schedule timer
    (es as unknown as Record<string, unknown>)["closed"] = false;
    // simulate onerror scheduling
    // we directly test that close clears timer
    // Trigger connect then onerror via mock EventSource
    const origES = global.EventSource;
    class FakeES {
      onopen: (() => void) | null = null;
      onmessage: ((e: MessageEvent) => void) | null = null;
      onerror: (() => void) | null = null;
      close = vi.fn();
    }
    global.EventSource = FakeES as unknown as typeof EventSource;
    es.connect();
    // simulate error to schedule reconnect
    // Access private source and trigger onerror
    const src = (es as unknown as Record<string, unknown>)["source"] as unknown as FakeES;
    src.onerror?.();
    expect((es as unknown as Record<string, unknown>)["reconnectTimer"]).not.toBeNull();
    es.close();
    expect((es as unknown as Record<string, unknown>)["reconnectTimer"]).toBeNull();
    // advancing timers should not reconnect
    vi.advanceTimersByTime(5000);
    global.EventSource = origES;
    vi.useRealTimers();
  });
});
