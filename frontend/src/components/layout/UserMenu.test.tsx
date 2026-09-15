import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { UserMenu } from "@/components/layout/UserMenu";

describe("UserMenu", () => {
  it("lists Preferences between Profile and Security resolving to the preferences route", () => {
    render(<UserMenu email="dev@corp.dev" onLogout={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    const labels = screen.getAllByRole("menuitem").map((node) => node.textContent ?? "");
    const prefsIndex = labels.indexOf("Preferences");
    expect(prefsIndex).toBeGreaterThan(labels.indexOf("Profile"));
    expect(prefsIndex).toBeLessThan(labels.indexOf("Security"));
    expect(screen.getByRole("menuitem", { name: "Preferences" })).toHaveAttribute("href", "/settings/preferences");
  });

  it("closes the menu when Preferences is activated", () => {
    render(<UserMenu email="dev@corp.dev" onLogout={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Account menu" }));
    fireEvent.click(screen.getByRole("menuitem", { name: "Preferences" }));
    expect(screen.queryByRole("menu")).toBeNull();
  });
});