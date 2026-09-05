import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Protected } from "@/components/auth/Protected";
import { useAuthStore } from "@/stores/auth";
import { PERMISSIONS } from "@/types/auth";

vi.mock("@/lib/api", () => ({
  getToken: () => "tok",
  api: { me: () => new Promise(() => {}) },
}));

describe("Protected", () => {
  beforeEach(() => {
    useAuthStore.setState({ status: "loading", user: null });
  });

  it("shows a loading state while checking the session", () => {
    render(
      <Protected>
        <p>Secret</p>
      </Protected>,
    );
    expect(screen.getByLabelText("Checking session")).toBeInTheDocument();
  });

  it("renders children when authenticated", () => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "1", email: "a@b.io", username: "ab" },
    });
    render(
      <Protected>
        <p>Secret</p>
      </Protected>,
    );
    expect(screen.getByText("Secret")).toBeInTheDocument();
  });

  it("shows a forbidden experience without granted permissions", () => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "1", email: "a@b.io", username: "ab" },
    });
    render(
      <Protected requiredPermissions={[PERMISSIONS.billingAdmin]} grantedPermissions={[]}>
        <p>Secret</p>
      </Protected>,
    );
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText("Secret")).toBeNull();
  });
});
