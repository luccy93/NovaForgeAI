import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiBase } from "@/lib/env";
import { Protected } from "@/components/auth/Protected";
import { useAuthStore } from "@/stores/auth";
import { PERMISSIONS } from "@/types/auth";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/dashboard",
  useSearchParams: () => new URLSearchParams(),
}));

describe("production C1 — API configuration", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("falls back to dev backend when unconfigured outside production", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(apiBase()).toBe("http://127.0.0.1:8000/api/v1");
  });

  it("trims whitespace and strips trailing slashes", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "  https://api.example.com/v1//  ");
    expect(apiBase()).toBe("https://api.example.com/v1");
  });

  it("rejects malformed URLs with a clear error", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "not a url at all with spaces");
    expect(() => apiBase()).toThrow("NEXT_PUBLIC_API_URL is malformed");
  });

  it("rejects non-HTTP(S) protocols", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "ftp://files.example.com/api");
    expect(() => apiBase()).toThrow("NEXT_PUBLIC_API_URL must use HTTP or HTTPS");
  });

  it("rejects local hosts in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    for (const host of ["localhost", "127.0.0.1", "0.0.0.0"]) {
      vi.stubEnv("NEXT_PUBLIC_API_URL", `http://${host}:8000/api/v1`);
      expect(() => apiBase()).toThrow("cannot point to a local development host");
    }
  });

  it("requires configuration in production when missing", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");
    expect(() => apiBase()).toThrow("NEXT_PUBLIC_API_URL is required in production");
  });

  it("accepts a valid HTTPS API URL in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.novaforge.ai/api/v1/");
    expect(apiBase()).toBe("https://api.novaforge.ai/api/v1");
  });

  it("env module exposes no secrets to the client bundle", async () => {
    const { readFileSync } = await import("node:fs");
    const content = readFileSync("C:/Users/Devendraprasad/Downloads/GraphRAG-main/frontend/src/lib/env.ts", "utf-8");
    expect(content).not.toMatch(/process\.env\.\w*(SECRET|API_KEY|PASSWORD|PRIVATE)/i);
    expect(content).not.toMatch(/NEXT_PUBLIC_\w*(SECRET|KEY|PASSWORD|TOKEN)/);
    const reads = content.match(/process\.env\.([A-Z_]+)/g) ?? [];
    for (const read of reads) {
      expect(["process.env.NEXT_PUBLIC_API_URL", "process.env.NODE_ENV"]).toContain(read);
    }
  });
});

describe("production C1 — error boundaries", () => {
  afterEach(() => cleanup());

  it("not-found renders safe navigation without secrets", async () => {
    const { default: NotFound } = await import("@/app/not-found");
    const { container } = render(<NotFound />);
    expect(screen.getByText("Page not found")).toBeInTheDocument();
    expect(container.innerHTML).not.toMatch(/stack|token|secret|password/i);
  });

  it("route error boundary renders retry without raw stack", async () => {
    const { default: RouteError } = await import("@/app/error");
    const { container } = render(<RouteError error={new Error("boom")} reset={() => {}} />);
    expect(screen.getByText("Something went wrong")).toBeInTheDocument();
    expect(container.innerHTML).not.toContain("boom");
  });
});

describe("production C1 — route protection", () => {
  afterEach(() => {
    cleanup();
    useAuthStore.setState({ status: "loading", user: null, mfaChallengeToken: null });
  });

  it("unauthenticated users are redirected to login without rendering children", () => {
    let navigated = "";
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        get href() {
          return "http://localhost:3000/dashboard";
        },
        set href(v: string) {
          navigated = v;
        },
      },
    });
    try {
      useAuthStore.setState({ status: "unauthenticated", user: null, mfaChallengeToken: null });
      const { container } = render(
        <Protected>
          <div>secret child</div>
        </Protected>,
      );
      expect(container.textContent).not.toContain("secret child");
      return waitFor(() => expect(navigated).toBe("/auth/login"));
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("admin gate denies without granted permission", () => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "u1", email: "a@b.io", username: "ab" },
      mfaChallengeToken: null,
    });
    render(
      <Protected requiredPermissions={[PERMISSIONS.admin]} grantedPermissions={[]}>
        <div>admin child</div>
      </Protected>,
    );
    expect(screen.getByText("403 — Forbidden")).toBeInTheDocument();
    expect(screen.queryByText("admin child")).toBeNull();
  });
});
