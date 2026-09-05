import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";
import * as apiModule from "@/lib/api";

vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    getToken: vi.fn(),
    setToken: vi.fn(),
    clearToken: vi.fn(),
  };
});

const mocked = apiModule as unknown as {
  getToken: ReturnType<typeof vi.fn>;
  api: Record<string, ReturnType<typeof vi.fn>>;
};

describe("auth store", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "loading", user: null });
    useTenantStore.getState().clear();
    vi.clearAllMocks();
    mocked.api = {
      me: vi.fn(),
      login: vi.fn(),
      register: vi.fn(),
    };
  });

  it("hydrates an existing session", async () => {
    mocked.getToken.mockReturnValue("tok");
    mocked.api.me.mockResolvedValue({ id: "1", email: "a@b.io", username: "ab" });
    await useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().status).toBe("authenticated");
    expect(useAuthStore.getState().user?.email).toBe("a@b.io");
  });

  it("expires when the session is rejected", async () => {
    mocked.getToken.mockReturnValue("tok");
    mocked.api.me.mockRejectedValue(new Error("nope"));
    await useAuthStore.getState().hydrate();
    expect(useAuthStore.getState().status).toBe("expired");
    expect(useAuthStore.getState().user).toBeNull();
  });

  it("clears tenant context on logout", async () => {
    useTenantStore.getState().setContext("org-1", "ws-1");
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().status).toBe("unauthenticated");
    expect(useTenantStore.getState().organizationId).toBeNull();
  });

  it("logs in and stores the session", async () => {
    mocked.api.login.mockResolvedValue({ access_token: "tok" });
    mocked.api.me.mockResolvedValue({ id: "2", email: "c@d.io", username: "cd" });
    await useAuthStore.getState().login("c@d.io", "secret123");
    expect(useAuthStore.getState().status).toBe("authenticated");
  });
});
