import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BrutalModal } from "@/components/ui/BrutalModal";

describe("BrutalModal", () => {
  it("renders nothing when closed", () => {
    render(
      <BrutalModal open={false} title="Confirm" onClose={() => {}}>
        Body
      </BrutalModal>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(
      <BrutalModal open title="Confirm" onClose={onClose}>
        Body
      </BrutalModal>,
    );
    expect(screen.getByRole("dialog", { name: "Confirm" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("renders actions", () => {
    render(
      <BrutalModal open title="Confirm" onClose={() => {}} actions={<button type="button">OK</button>}>
        Body
      </BrutalModal>,
    );
    expect(screen.getByRole("button", { name: "OK" })).toBeInTheDocument();
  });
});
