import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("AppShell", () => {
  it("renders header, navigation and content", () => {
    render(
      <AppShell email="a@b.io" workspaceLabel="Acme" onLogout={() => {}}>
        <p>Content</p>
      </AppShell>,
    );
    expect(screen.getByText("NOVAFORGE")).toBeInTheDocument();
    expect(screen.getByText("Content")).toBeInTheDocument();
  });

  it("opens the mobile drawer", () => {
    render(
      <AppShell email="a@b.io" workspaceLabel={null} onLogout={() => {}}>
        <p>Content</p>
      </AppShell>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Open navigation" }));
    expect(screen.getByRole("dialog", { name: "Navigate" })).toBeInTheDocument();
  });

  it("shows sign-in for visitors", () => {
    render(
      <AppShell email={null} workspaceLabel={null} onLogout={() => {}}>
        <p>Content</p>
      </AppShell>,
    );
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/auth/login");
  });
});
