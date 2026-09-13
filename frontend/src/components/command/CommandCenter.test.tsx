import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandCenter } from "@/components/command/CommandCenter";
import { ApiError } from "@/lib/api-client";

const whoamiMock = vi.fn();
const knowledgeSearchMock = vi.fn();
const dataCatalogSearchMock = vi.fn();

vi.mock("@/lib/api", () => ({
  getToken: () => "token",
  clearToken: vi.fn(),
  api: {
    whoami: (...args: unknown[]) => whoamiMock(...args),
    knowledgeSearch: (...args: unknown[]) => knowledgeSearchMock(...args),
    dataCatalogSearch: (...args: unknown[]) => dataCatalogSearchMock(...args),
  },
}));

beforeEach(() => {
  whoamiMock.mockResolvedValue({ permissions: ["zero_trust:write"] });
  knowledgeSearchMock.mockResolvedValue({
    items: [{ document_id: "d1", title: "Doc One", snippet: "Snippet one", score: 0.9, citations: [] }],
    total: 1,
    query_id: "q1",
    latency_ms: 10,
    filters_applied: {},
  });
  dataCatalogSearchMock.mockResolvedValue({
    items: [{ id: "cat1", name: "Catalog One", description: "Cat description", owner: "me", classification: "public" }],
    total: 1,
  });
});

describe("CommandCenter", () => {
  it("renders navigation groups, honest recent and realtime states", async () => {
    render(<CommandCenter />);
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.getByText("Workspaces")).toBeInTheDocument();
    expect(screen.getByText("Command")).toBeInTheDocument();
    expect(screen.getByText("Security & Governance")).toBeInTheDocument();
    expect(screen.getByText("Recent activity")).toBeInTheDocument();
    expect(screen.getByText("Not exposed by API")).toBeInTheDocument();
    expect(screen.getByText(/Realtime: unavailable/i)).toBeInTheDocument();
    expect(whoamiMock).toHaveBeenCalled();
  });

  it("runs a global search across knowledge and the data catalog", async () => {
    render(<CommandCenter />);
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.change(screen.getByLabelText("Command center search query"), { target: { value: "billing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Doc One")).toBeInTheDocument();
    expect(await screen.findByText("Catalog One")).toBeInTheDocument();
    expect(knowledgeSearchMock).toHaveBeenCalledWith("token", "billing", expect.objectContaining({ limit: 5 }));
    expect(dataCatalogSearchMock).toHaveBeenCalledWith("token", "billing", { limit: 5 });
  });

  it("clears results on tenant switch", async () => {
    render(<CommandCenter />);
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.change(screen.getByLabelText("Command center search query"), { target: { value: "billing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await screen.findByText("Doc One");
    act(() => {
      window.dispatchEvent(new CustomEvent("tenant:switched", { detail: {} }));
    });
    await waitFor(() => expect(screen.queryByText("Doc One")).toBeNull());
    expect(screen.getByText("Results appear here from the knowledge base and data catalog.")).toBeInTheDocument();
  });

  it("surfaces a permission error on global search", async () => {
    knowledgeSearchMock.mockRejectedValue(new ApiError("forbidden", 403, "Not allowed"));
    dataCatalogSearchMock.mockResolvedValue({ items: [], total: 0 });
    render(<CommandCenter />);
    await act(async () => {
      await Promise.resolve();
    });
    fireEvent.change(screen.getByLabelText("Command center search query"), { target: { value: "billing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("Your session lacks permission for this search.")).toBeInTheDocument();
  });
});