import { fireEvent, render, screen, waitForElementToBeRemoved } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandCenterProvider, useCommandCenter } from "@/components/navigation/CommandCenterProvider";

vi.mock("@/lib/api", () => ({
  getToken: () => null,
  clearToken: vi.fn(),
  api: {
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
    whoami: vi.fn(),
  },
}));

function Trigger() {
  const { open } = useCommandCenter();
  return (
    <button type="button" onClick={open}>
      open palette
    </button>
  );
}

describe("CommandCenterProvider", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
  });

  it("opens the palette from a trigger via context", () => {
    render(
      <CommandCenterProvider>
        <Trigger />
      </CommandCenterProvider>,
    );
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "open palette" }));
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  });

  it("toggles the palette with Ctrl+K", async () => {
    render(
      <CommandCenterProvider>
        <Trigger />
      </CommandCenterProvider>,
    );
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    await waitForElementToBeRemoved(() => screen.queryByRole("dialog"));
  });

  it("closes the palette on Escape", async () => {
    render(
      <CommandCenterProvider>
        <Trigger />
      </CommandCenterProvider>,
    );
    fireEvent.keyDown(document, { key: "k", ctrlKey: true });
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "Escape" });
    await waitForElementToBeRemoved(() => screen.queryByRole("dialog"));
  });

  it("renders without a provider", () => {
    render(<Trigger />);
    fireEvent.click(screen.getByRole("button", { name: "open palette" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});