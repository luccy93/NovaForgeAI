import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrutalButton } from "@/components/ui/BrutalButton";

describe("BrutalButton", () => {
  it("renders an anchor with href, onClick and className", () => {
    const onClick = vi.fn();
    render(
      <BrutalButton href="/docs" onClick={onClick} className="extra">
        Docs
      </BrutalButton>,
    );
    const link = screen.getByRole("link", { name: "Docs" });
    expect(link).toHaveAttribute("href", "/docs");
    expect(link.className).toContain("extra");
    fireEvent.click(link);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("renders a button that forwards type and onClick", () => {
    const onClick = vi.fn();
    render(
      <BrutalButton onClick={onClick} type="submit">
        Go
      </BrutalButton>,
    );
    const button = screen.getByRole("button", { name: "Go" });
    expect(button).toHaveAttribute("type", "submit");
    fireEvent.click(button);
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("supports the yellow full-width variant", () => {
    render(
      <BrutalButton variant="yellow" size="lg" fullWidth>
        Go
      </BrutalButton>,
    );
    const button = screen.getByRole("button", { name: "Go" });
    expect(button.className).toContain("bg-primary-container");
    expect(button.className).toContain("w-full");
  });
});
