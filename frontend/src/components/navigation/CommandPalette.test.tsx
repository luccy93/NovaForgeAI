import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/navigation/CommandPalette";

vi.mock("@/lib/api", () => ({
  getToken: () => null,
  clearToken: vi.fn(),
  api: {
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
    whoami: vi.fn(),
  },
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

  it("shows handoff shortcuts and honest empty recent state", () => {
    render(<CommandPalette open onClose={() => {}} />);
    expect(screen.getByText("Search everything")).toBeInTheDocument();
    expect(screen.getByText("Search Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Search Code")).toBeInTheDocument();
    expect(screen.getByText("Ask AI")).toBeInTheDocument();
    expect(screen.getByText("No recent resources exposed by API.")).toBeInTheDocument();
  });

  it("hides recent when searching", () => {
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Command palette query"), { target: { value: "finops" } });
    expect(screen.queryByText("No recent resources exposed by API.")).toBeNull();
  });

  it("moves selection with arrow keys", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "ArrowDown" });
    expect(options[0]).toHaveAttribute("aria-selected", "false");
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "ArrowUp" });
    expect(options[0]).toHaveAttribute("aria-selected", "true");
  });

  it("runs the active action on Enter", () => {
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "Enter" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});