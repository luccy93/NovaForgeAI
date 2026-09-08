import { render, screen, waitFor, fireEvent, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { UniversalSearch } from "@/components/universal/UniversalSearch";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/knowledge/universal",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

vi.mock("@/components/auth/Protected", async () => {
  const actual = await vi.importActual<typeof import("@/components/auth/Protected")>(
    "@/components/auth/Protected",
  );
  return {
    ...actual,
    Protected: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

const knowledgeResponse = {
  items: [
    {
      document_id: "d1",
      chunk_id: "c1",
      title: "Payment auth guide",
      snippet: "How authentication failures are diagnosed.",
      score: 0.92,
      source_type: "documents",
      classification: "INTERNAL",
      freshness_score: 0.8,
      citations: [],
      retrieval_method: "hybrid",
    },
  ],
  total: 1,
  query_id: "q1",
  latency_ms: 23,
  filters_applied: {},
};

const catalogResponse = {
  items: [
    {
      id: "ds1",
      name: "payments-dataset",
      owner: "data-team",
      classification: "INTERNAL",
      description: "Normalized payment records.",
      score: 0.9,
      source: "postgresql",
    },
  ],
  total: 1,
  source: "postgresql",
  stale: false,
};

function installApiMock(): Record<string, ReturnType<typeof vi.fn>> {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    knowledgeSearch: vi.fn().mockResolvedValue(knowledgeResponse),
    dataCatalogSearch: vi.fn().mockResolvedValue(catalogResponse),
  };
  for (const [key, value] of Object.entries(defaults)) {
    api[key] = value;
  }
  return api;
}

async function searchHello() {
  fireEvent.change(screen.getByLabelText("Universal search"), { target: { value: "hello" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() => expect(screen.getByText("Payment auth guide")).toBeInTheDocument());
}

describe("Universal Search", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("starts with an honest idle state before any query runs", () => {
    render(<UniversalSearch />);
    expect(screen.getByText("Search across real domains")).toBeInTheDocument();
    expect(screen.getByText(/nothing is synthesized client-side/i)).toBeInTheDocument();
    expect(screen.getByText(/REALTIME: UNAVAILABLE/)).toBeInTheDocument();
  });

  it("runs every searchable domain's real API and renders its hits", async () => {
    render(<UniversalSearch />);
    await searchHello();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.knowledgeSearch).toHaveBeenCalledWith(
      "test-token",
      "hello",
      expect.objectContaining({ limit: 5 }),
    );
    expect(api.dataCatalogSearch).toHaveBeenCalledWith("test-token", "hello", { limit: 5 });
    expect(screen.getAllByText("1 hit")).toHaveLength(2);
    const knowledgeSection = screen.getByRole("region", { name: "Knowledge results" });
    expect(knowledgeSection.textContent).toContain("Payment auth guide");
    const catalogSection = screen.getByRole("region", { name: "Data catalog results" });
    expect(catalogSection.textContent).toContain("payments-dataset");
    expect(screen.getByText(/2 total hits across/)).toBeInTheDocument();
  });

  it("shows an honest no-search-contract list for domains without a real search API", async () => {
    render(<UniversalSearch />);
    await searchHello();
    const blocked = screen.getByRole("region", { name: "Unavailable domains" });
    expect(blocked.textContent).toContain("Code");
    expect(blocked.textContent).toContain("Incidents");
    expect(blocked.textContent).toContain("Security");
    expect(blocked.textContent).toContain("Workflows");
    expect(blocked.textContent).toContain("Integrations");
  });

  it("reports an honest empty hit state when a domain returns nothing", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.dataCatalogSearch.mockResolvedValue({ items: [], total: 0 });
    render(<UniversalSearch />);
    await searchHello();
    expect(screen.getByText("No matches returned by the data catalog API.")).toBeInTheDocument();
    expect(screen.getByText("0 hits")).toBeInTheDocument();
  });

  it("surfaces a failing domain without masking the successful one", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeSearch.mockRejectedValue(new ApiError("server", 500, "index unavailable"));
    render(<UniversalSearch />);
    fireEvent.change(screen.getByLabelText("Universal search"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getAllByRole("alert")).toHaveLength(1));
    expect(screen.getByText("index unavailable")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText("payments-dataset")).toBeInTheDocument());
  });

  it("links knowledge hits through to the real document view", async () => {
    render(<UniversalSearch />);
    await searchHello();
    const link = screen.getByRole("link", { name: /Payment auth guide/ });
    expect(link).toHaveAttribute("href", "/knowledge/document/d1");
  });

  it("resets and clears results on tenant switch", async () => {
    render(<UniversalSearch />);
    await searchHello();
    expect(screen.getByText("Payment auth guide")).toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() =>
      expect(screen.getByText("Search across real domains")).toBeInTheDocument(),
    );
    expect(screen.queryByText("Payment auth guide")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Universal search")).toHaveValue("");
  });

  it("escalates a 401 to a login redirect", async () => {
    const fakeLocation = { href: "", pathname: "/knowledge/universal", search: "" };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      api.knowledgeSearch.mockRejectedValue(new ApiError("unauthorized", 401, "expired"));
      render(<UniversalSearch />);
      fireEvent.change(screen.getByLabelText("Universal search"), { target: { value: "hello" } });
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      await waitFor(() => expect(apiModule.clearToken).toHaveBeenCalled());
      expect(fakeLocation.href).toBe("/auth/login");
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });
});