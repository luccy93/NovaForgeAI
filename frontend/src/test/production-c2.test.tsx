import { cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { apiBase } from "@/lib/env";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";

const ROOT = "C:/Users/Devendraprasad/Downloads/GraphRAG-main";
const SRC = `${ROOT}/frontend/src`;

describe("production C2 — env edge cases", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("normalizes uppercase scheme and host, still rejecting prod localhost", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "HTTP://LOCALHOST:8000/api/v1");
    expect(() => apiBase()).toThrow("cannot point to a local development host");
  });

  it("treats whitespace-only config as missing", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "   ");
    expect(apiBase()).toBe("http://127.0.0.1:8000/api/v1");
    vi.stubEnv("NODE_ENV", "production");
    expect(() => apiBase()).toThrow("NEXT_PUBLIC_API_URL is required in production");
  });

  it("rejects IPv6 loopback in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://[::1]:8000/api/v1");
    expect(() => apiBase()).toThrow("cannot point to a local development host");
  });

  it("accepts loopback in non-production (dev convenience preserved)", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "http://127.0.0.1:8000/api/v1");
    expect(apiBase()).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("strips repeated trailing slashes and surrounding whitespace", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "  https://api.example.com/v1///  ");
    expect(apiBase()).toBe("https://api.example.com/v1");
  });
});

describe("production C2 — logout clears sensitive client state", () => {
  afterEach(() => {
    cleanup();
    localStorage.clear();
    useTenantStore.getState().clear();
    useAuthStore.setState({ status: "loading", user: null, mfaChallengeToken: null });
  });

  it("explicit logout wipes tokens, tenant, workspace and caches", () => {
    localStorage.setItem("nf_token", "tok");
    localStorage.setItem("nf_refresh", "ref");
    localStorage.setItem("nf_cache_dashboard", "stale");
    useTenantStore.setState({
      organizationId: "org-1",
      workspaceId: "ws-1",
      workspaceName: "WS",
      organizations: [{ id: "org-1", name: "Org", slug: "org" } as never],
      workspaces: [{ id: "ws-1", name: "WS" } as never],
    });
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "u1", email: "a@b.io", username: "ab" },
      mfaChallengeToken: null,
    });
    useAuthStore.getState().logout();
    expect(localStorage.getItem("nf_token")).toBeNull();
    expect(localStorage.getItem("nf_refresh")).toBeNull();
    expect(localStorage.getItem("nf_cache_dashboard")).toBeNull();
    expect(useTenantStore.getState().organizationId).toBeNull();
    expect(useTenantStore.getState().workspaceId).toBeNull();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
  });
});

describe("production C2 — no production logging in shipped code", () => {
  function walk(dir: string): string[] {
    const out: string[] = [];
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        out.push(...walk(full));
      } else if (/\.(ts|tsx)$/.test(entry) && !/\.test\.(ts|tsx)$/.test(entry)) {
        out.push(full);
      }
    }
    return out;
  }

  it("no console.* calls outside tests", () => {
    const offenders: string[] = [];
    for (const full of walk(SRC)) {
      const content = readFileSync(full, "utf-8");
      // String/template literals (e.g. docs code samples) are not calls.
      const stripped = content
        .replace(/`(?:\\.|[^`\\])*`/g, "")
        .replace(/'(?:\\.|[^'\\\n])*'/g, '')
        .replace(/"(?:\\.|[^"\\\n])*"/g, "");
      if (/console\.(log|error|warn|debug|info|trace)\(/.test(stripped)) offenders.push(full);
    }
    expect(offenders).toEqual([]);
  });
});

describe("production C2 — deterministic install + CI gates", () => {
  it("lockfile exists with pinned versions", () => {
    const lock = JSON.parse(readFileSync(`${ROOT}/frontend/package-lock.json`, "utf-8")) as {
      lockfileVersion?: number;
      packages?: Record<string, { version?: string }>;
    };
    expect(lock.lockfileVersion).toBeGreaterThanOrEqual(2);
    expect(lock.packages?.[""]?.version).toBeTruthy();
    expect(lock.packages?.["node_modules/next"]?.version).toMatch(/^16\./);
  });

  it("CI gates typecheck, tests and lint before build", () => {
    const ci = readFileSync(`${ROOT}/.github/workflows/ci-cd.yml`, "utf-8");
    expect(ci).toContain("npx tsc --noEmit");
    expect(ci).toContain("poolOptions.threads.maxThreads=1");
    expect(ci).not.toContain('|| echo "No frontend linter');
    const lintIdx = ci.indexOf("Typecheck frontend");
    const testIdx = ci.indexOf("Test frontend");
    const lintStepIdx = ci.indexOf("Lint frontend");
    expect(lintIdx).toBeGreaterThan(-1);
    expect(testIdx).toBeGreaterThan(lintIdx);
    expect(lintStepIdx).toBeGreaterThan(testIdx);
  });
});
