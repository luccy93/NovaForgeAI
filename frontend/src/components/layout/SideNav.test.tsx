import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SideNav } from "@/components/layout/SideNav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

describe("SideNav", () => {
  it("shows all sections to authenticated users", () => {
    render(<SideNav authenticated />);
    expect(screen.getByText("Workspace")).toBeInTheDocument();
    expect(screen.getByText("Platform")).toBeInTheDocument();
    expect(screen.getByText("System")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "FinOps" })).toBeInTheDocument();
  });

  it("hides authenticated entries from visitors", () => {
    render(<SideNav authenticated={false} />);
    expect(screen.queryByRole("link", { name: "FinOps" })).toBeNull();
    expect(screen.queryByRole("link", { name: "AI" })).toBeNull();
  });

  it("marks the current page and notifies on navigate", () => {
    const onNavigate = vi.fn();
    render(<SideNav authenticated onNavigate={onNavigate} />);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    fireEvent.click(screen.getByRole("link", { name: "AI" }));
    expect(onNavigate).toHaveBeenCalledTimes(1);
  });
});
