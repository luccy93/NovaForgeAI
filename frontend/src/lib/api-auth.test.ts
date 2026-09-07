import { describe, it, expect, vi, beforeEach } from "vitest";
import { apiRequest, ApiError } from "@/lib/api-client";

describe("ApiError classification", () => {
  it("maps 401 to unauthorized", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "nope" }), { status: 401 })));
    await expect(apiRequest("/x")).rejects.toMatchObject({ kind: "unauthorized", status: 401 });
    vi.unstubAllGlobals();
  });
  it("maps 403 to forbidden", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "forbidden" }), { status: 403 })));
    await expect(apiRequest("/x")).rejects.toMatchObject({ kind: "forbidden" });
    vi.unstubAllGlobals();
  });
  it("maps 429 to rate_limited", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: "rate" }), { status: 429 })));
    await expect(apiRequest("/x", { retryGet: false })).rejects.toMatchObject({ kind: "rate_limited" });
    vi.unstubAllGlobals();
  });
  it("does not log tokens", async () => {
    const spy = vi.spyOn(console, "log").mockImplementation(() => {});
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 })));
    await apiRequest("/auth/me", { token: "secret-token-123" });
    const logged = spy.mock.calls.flat().join(" ");
    expect(logged).not.toContain("secret-token-123");
    spy.mockRestore();
    vi.unstubAllGlobals();
  });
});

describe("auth validation helpers", () => {
  it("validates email format", () => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    expect(emailRegex.test("bad")).toBe(false);
    expect(emailRegex.test("good@example.com")).toBe(true);
  });
  it("validates password length", () => {
    expect("short".length >= 8).toBe(false);
    expect("longenough1".length >= 8).toBe(true);
  });
});
