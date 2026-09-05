import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/navigation/CommandPalette";

vi.mock("@/lib/api", () => ({
  getToken: () => null,
  api: { knowledgeSearch: vi.fn() },
}));

describe("CommandPalette", () => {
  it("renders nothing when closed", () => {
    render(<CommandPalette open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("filters navigation actions by query", () => {
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Command palette query"), { target: { value: "finops" } });
    expect(screen.getByText("Go to FinOps")).toBeInTheDocument();
    expect(screen.queryByText("Go to AI")).toBeNull();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
