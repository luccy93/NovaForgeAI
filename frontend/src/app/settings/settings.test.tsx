import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import SettingsPage from "@/app/settings/page";
import { useAuthStore } from "@/stores/auth";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings",
}));

describe("Settings hub", () => {
  beforeEach(() => {
    useAuthStore.setState({
      status: "authenticated",
      user: { id: "u1", email: "dev@corp.dev", username: "dev" },
    });
    useTenantStore.getState().setContext("org-1", "ws-1");
  });

  it("exposes a single Preferences tile that resolves to the preferences route", () => {
    render(<SettingsPage />);
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(
      screen.getByText("Appearance, workspace experience, accessibility and supported user preferences."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open preferences" })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Open preferences" })).toHaveAttribute("href", "/settings/preferences");
  });

  it("keeps the preferences hub read-only with no embedded preference controls", () => {
    render(<SettingsPage />);
    const card = screen.getByText("Appearance, workspace experience, accessibility and supported user preferences.")
      .closest("div");
    expect(card).not.toBeNull();
    expect(card?.querySelectorAll("button")).toHaveLength(0);
  });
});