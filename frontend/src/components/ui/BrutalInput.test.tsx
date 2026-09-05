import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BrutalInput } from "@/components/ui/BrutalInput";

describe("BrutalInput", () => {
  it("associates label with the input", () => {
    render(<BrutalInput label="Email" placeholder="you@x.io" />);
    expect(screen.getByLabelText("Email")).toHaveAttribute("placeholder", "you@x.io");
  });

  it("exposes errors to assistive technology", () => {
    render(<BrutalInput label="Email" error="Required" />);
    const input = screen.getByLabelText("Email");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByRole("alert")).toHaveTextContent("Required");
  });
});
