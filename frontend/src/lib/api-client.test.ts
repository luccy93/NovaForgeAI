import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiRequest } from "@/lib/api-client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("apiRequest", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("sends bearer tokens and parses JSON", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { ok: true }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await apiRequest<{ ok: boolean }>("/ping", { token: "abc" });
    expect(result).toEqual({ ok: true });
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.headers as Record<string, string>)["Authorization"]).toBe("Bearer abc");
  });

  it.each([
    [401, "unauthorized"],
    [403, "forbidden"],
    [422, "validation"],
    [429, "rate_limited"],
    [500, "server"],
  ])("classifies HTTP %i as %s", async (status, kind) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, { detail: "nope" })));
    const error: unknown = await apiRequest("/x", { retryGet: false }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).kind).toBe(kind);
    expect((error as ApiError).message).toBe("nope");
  });

  it("does not retry mutations", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new TypeError("down"));
    vi.stubGlobal("fetch", fetchMock);
    await expect(apiRequest("/x", { method: "POST", body: {} })).rejects.toMatchObject({
      kind: "network",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("aborts slow requests", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () =>
              reject(new DOMException("timeout", "TimeoutError")),
            );
          }),
      ),
    );
    await expect(apiRequest("/slow", { timeoutMs: 20 })).rejects.toMatchObject({ kind: "timeout" });
  });

  it("supports cancellation", async () => {
    const controller = new AbortController();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => {
            init.signal?.addEventListener("abort", () =>
              reject(new DOMException("aborted", "AbortError")),
            );
          }),
      ),
    );
    const pending = apiRequest("/slow", { signal: controller.signal, timeoutMs: 5000 });
    controller.abort();
    await expect(pending).rejects.toMatchObject({ kind: "unknown" });
  });
});
