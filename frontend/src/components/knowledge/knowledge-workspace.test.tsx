import { render, screen, waitFor, fireEvent, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import KnowledgePage from "@/app/knowledge/page";
import { KnowledgeWorkspace } from "@/components/knowledge/KnowledgeWorkspace";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/knowledge",
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

function unauthorized(error: string) {
  return new ApiError("unauthorized", 401, error);
}

const searchResponse = {
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
      citations: [
        { source_name: "Payments Runbook", doc_type: "document", version: "1.2", url: "https://docs.example.com/payments" },
      ],
      retrieval_method: "hybrid",
    },
    {
      document_id: "d2",
      chunk_id: "c2",
      title: "IAM tokens",
      snippet: "Token lifetimes and rotation.",
      score: 0.71,
      source_type: "security",
      classification: "CONFIDENTIAL",
      freshness_score: 0.2,
      citations: [],
      retrieval_method: "hybrid",
    },
  ],
  total: 2,
  query_id: "q1",
  latency_ms: 23,
  filters_applied: { source_type: null, doc_type: null, classification: null },
};

const documentDetail = {
  document_id: "d1",
  title: "Payment auth guide",
  content: "1. Check the payment provider status page.\n2. Inspect failed auth logs.\n3. Verify token expiry.",
  summary: "Diagnosing payment authentication failures.",
  doc_type: "guide",
  version: "1.2",
  classification: "INTERNAL",
  source_id: "s1",
  freshness_score: 0.8,
  chunk_count: 3,
  status: "INGESTED",
  tags: ["payments", "auth"],
  attribution: { author: "Payments Runbook" },
  language: "en",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-05T00:00:00Z",
};

const sources = [
  {
    source_id: "s1",
    name: "Payments KB",
    source_type: "documents",
    status: "ACTIVE",
    classification: "INTERNAL",
    owner: "u1",
    last_ingested_at: "2026-01-01T00:00:00Z",
    created_at: "2025-12-01T00:00:00Z",
  },
];

function installApiMock(): Record<string, ReturnType<typeof vi.fn>> {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
    knowledgeSearch: vi.fn().mockResolvedValue(searchResponse),
    knowledgeListSources: vi.fn().mockResolvedValue({ items: sources, total: 1 }),
    knowledgeFreshnessStats: vi.fn().mockResolvedValue({ total: 3, fresh: 2, aging: 1, stale: 0 }),
    knowledgeUsageStats: vi
      .fn()
      .mockResolvedValue({
        total_queries: 42,
        by_type: { search: 42 },
        avg_latency_ms: 12,
        unique_users: 3,
        top_terms: ["auth"],
      }),
    knowledgeGetDocument: vi.fn().mockResolvedValue(documentDetail),
  };
  for (const [key, value] of Object.entries(defaults)) {
    api[key] = value;
  }
  return api;
}

async function searchHello() {
  fireEvent.change(screen.getByLabelText("Knowledge search"), { target: { value: "hello" } });
  fireEvent.click(screen.getByRole("button", { name: "Search" }));
  await waitFor(() =>
    expect(screen.getByRole("list", { name: "Knowledge results" })).toBeInTheDocument(),
  );
}

describe("Knowledge Workspace", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    window.history.replaceState(null, "", "/knowledge");
  });

  it("renders the page shell with a workspace title", async () => {
    render(<KnowledgePage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Knowledge" })).toBeInTheDocument(),
    );
  });

  it("loads sources, freshness and usage into the sidebar", async () => {
    render(<KnowledgeWorkspace />);
    await waitFor(() => expect(screen.getByText("Payments KB")).toBeInTheDocument());
    expect(screen.getByText("Sources · 1")).toBeInTheDocument();
    expect(screen.getByText("Freshness · 3 indexed")).toBeInTheDocument();
    expect(screen.getByText("42 queries")).toBeInTheDocument();
  });

  it("starts with an honest empty state until a search is submitted", async () => {
    render(<KnowledgeWorkspace />);
    await waitFor(() =>
      expect(screen.getByText("Search the knowledge base")).toBeInTheDocument(),
    );
    expect(screen.queryByRole("list", { name: "Knowledge results" })).not.toBeInTheDocument();
  });

  it("runs the backend search and renders real results with citations and score", async () => {
    render(<KnowledgeWorkspace />);
    await searchHello();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.knowledgeSearch).toHaveBeenCalledWith(
      "test-token",
      "hello",
      expect.objectContaining({
        limit: 20,
        offset: 0,
        source_type: undefined,
        doc_type: undefined,
        classification: undefined,
      }),
    );
    expect(screen.getByText("IAM tokens")).toBeInTheDocument();
    expect(screen.getByText("2 results · 23 ms")).toBeInTheDocument();
    expect(screen.getByText("1 citation")).toBeInTheDocument();
    const resultItems = screen.getAllByRole("listitem");
    expect(resultItems.length).toBeGreaterThanOrEqual(2);
  });

  it("passes filter selections to the backend and re-searches", async () => {
    render(<KnowledgeWorkspace />);
    await searchHello();
    fireEvent.change(screen.getByLabelText("Source type filter"), { target: { value: "security" } });
    await waitFor(() =>
      expect(
        (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).knowledgeSearch,
      ).toHaveBeenLastCalledWith(
        "test-token",
        "hello",
        expect.objectContaining({ source_type: "security", offset: 0 }),
      ),
    );
    // URL reflects the filter for shareable/backable state
    expect(window.location.search).toContain("st=security");
  });

  it("shows an honest empty state when the backend returns no results", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeSearch.mockResolvedValueOnce({
      ...searchResponse,
      items: [],
      total: 0,
    });
    render(<KnowledgeWorkspace />);
    fireEvent.change(screen.getByLabelText("Knowledge search"), { target: { value: "nothing" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(screen.getByText('No results for "nothing"')).toBeInTheDocument(),
    );
  });

  it("shows an error state when the backend search fails", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeSearch.mockRejectedValueOnce(new ApiError("server", 500, "index unavailable"));
    render(<KnowledgeWorkspace />);
    fireEvent.change(screen.getByLabelText("Knowledge search"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByText("Search failed")).toBeInTheDocument();
  });

  it("pages through results using backend offset pagination", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    let searchCount = 0;
    const responses: Array<Record<string, unknown>> = [
      { items: searchResponse.items.slice(0, 1), total: 40, latency_ms: 10 },
      { items: searchResponse.items.slice(1, 2), total: 40, latency_ms: 11 },
      { items: searchResponse.items.slice(0, 1), total: 40, latency_ms: 12 },
    ];
    api.knowledgeSearch.mockImplementation(async () => {
      const pick = responses[Math.min(searchCount, responses.length - 1)] ?? responses[0];
      searchCount += 1;
      return { ...searchResponse, ...pick, query_id: `q${searchCount}` };
    });
    render(<KnowledgeWorkspace />);
    await searchHello();
    expect(screen.getByText("page 1 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await waitFor(() =>
      expect(
        (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).knowledgeSearch,
      ).toHaveBeenLastCalledWith("test-token", "hello", expect.objectContaining({ offset: 20 })),
    );
    expect(screen.getByText("page 2 of 2")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    await waitFor(() => expect(screen.getByText("page 1 of 2")).toBeInTheDocument());
  });

  it("opens a result, fetches the real document, and renders content read-only", async () => {
    render(<KnowledgeWorkspace />);
    await searchHello();

    fireEvent.click(screen.getByRole("button", { name: /Payment auth guide/ }));
    await waitFor(() =>
      expect(screen.getByText("Document detail")).toBeInTheDocument(),
    );
    expect(
      (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).knowledgeGetDocument,
    ).toHaveBeenCalledWith("test-token", "d1");
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText(/Verify token expiry/)).toBeInTheDocument();

    // Content is displayed read-only — never an editable control, and the
    // search bar/filters are locked so focus stays on the detail.
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("renders backend citation links safely (no javascript: URLs as anchors)", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeSearch.mockResolvedValueOnce({
      ...searchResponse,
      items: [
        {
          document_id: "d9",
          chunk_id: "c9",
          title: "Unsafe citation",
          snippet: "snippet",
          score: 0.5,
          source_type: "documents",
          classification: "INTERNAL",
          freshness_score: 0.5,
          citations: [
            { source_name: "Safe Runbook", doc_type: "document", version: "1.0", url: "https://docs.example.com/safe" },
            { source_name: "Unsafe Target", doc_type: "document", version: "1.0", url: "javascript:alert(1)" },
          ],
          retrieval_method: "hybrid",
        },
      ],
      total: 1,
    });
    render(<KnowledgeWorkspace />);
    await searchHello();
    fireEvent.click(screen.getByRole("button", { name: /Unsafe citation/ }));
    await waitFor(() => expect(screen.getByText("Citations / provenance")).toBeInTheDocument());

    const safeLink = screen.getByRole("link", { name: "Safe Runbook" });
    expect(safeLink).toHaveAttribute("href", "https://docs.example.com/safe");
    expect(safeLink).toHaveAttribute("rel", "noopener noreferrer");

    // javascript: URL is NOT rendered as a clickable anchor.
    expect(screen.queryByRole("link", { name: "Unsafe Target" })).toBeNull();
    expect(screen.getByText("Unsafe Target")).toBeInTheDocument();
  });

  it("shows an honest partial-content state when full content is unavailable", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeGetDocument.mockResolvedValueOnce({
      document_id: "d1",
      title: "Payment auth guide",
      content: null,
      summary: null,
      doc_type: "guide",
      version: "1.2",
      classification: "INTERNAL",
    });
    render(<KnowledgeWorkspace />);
    await searchHello();
    fireEvent.click(screen.getByRole("button", { name: /Payment auth guide/ }));
    await waitFor(() =>
      expect(screen.getByText("Content not available")).toBeInTheDocument(),
    );
    expect(screen.getByText(/full source content is not available/)).toBeInTheDocument();
  });

  it("restores the search query and results from the Back action", async () => {
    render(<KnowledgeWorkspace />);
    await searchHello();
    fireEvent.click(screen.getByRole("button", { name: /Payment auth guide/ }));
    await waitFor(() => expect(screen.getByText("Document detail")).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /Back to results/ }));
    await waitFor(() => expect(screen.getByText("Payment auth guide")).toBeInTheDocument());
    expect(screen.getByLabelText("Knowledge search")).toHaveValue("hello");
    expect(window.location.search).toContain("q=hello");
  });

  it("renders malicious document content as inert text (no script execution)", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeGetDocument.mockResolvedValueOnce({
      ...documentDetail,
      content: "<script>window.__pwned = true</script><img src=x onerror=alert(1)>",
    });
    render(<KnowledgeWorkspace />);
    await searchHello();
    fireEvent.click(screen.getByRole("button", { name: /Payment auth guide/ }));
    await waitFor(() =>
      expect(screen.getByText(/window.__pwned/)).toBeInTheDocument(),
    );
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(document.querySelector("script")).not.toBeInTheDocument();
    expect((window as unknown as Record<string, unknown>).__pwned).toBeUndefined();
  });

  it("escalates a 401 on document detail to a login redirect", async () => {
    const fakeLocation = { href: "", pathname: "/knowledge", search: "" };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      api.knowledgeGetDocument.mockRejectedValueOnce(unauthorized("expired"));
      render(<KnowledgeWorkspace />);
      await searchHello();
      fireEvent.click(screen.getByRole("button", { name: /Payment auth guide/ }));
      await waitFor(() => expect(apiModule.clearToken).toHaveBeenCalled());
      expect(fakeLocation.href).toBe("/auth/login");
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("resets and reloads on tenant switch without cross-workspace leakage", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    render(<KnowledgeWorkspace />);
    await waitFor(() => expect(screen.getByText("Payments KB")).toBeInTheDocument());
    expect(api.knowledgeListSources).toHaveBeenCalledTimes(1);

    await searchHello();
    expect(screen.getByText("Payment auth guide")).toBeInTheDocument();

    await act(async () => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() => expect(api.knowledgeListSources).toHaveBeenCalledTimes(2));
    // Old results and any selection are cleared; search bar is blank again.
    expect(screen.queryByText("Payment auth guide")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Knowledge search")).toHaveValue("");
  });

  it("deep-links to a document view when the URL carries a document id", async () => {
    window.history.replaceState(null, "", "/knowledge/document/d1");
    render(<KnowledgeWorkspace />);
    await waitFor(() =>
      expect(screen.getByText("Document detail")).toBeInTheDocument(),
    );
    expect(
      (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).knowledgeGetDocument,
    ).toHaveBeenCalledWith("test-token", "d1");
  });

  it("only enables the Search button when a query is present", () => {
    render(<KnowledgeWorkspace />);
    expect(screen.getByRole("button", { name: "Search" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Knowledge search"), { target: { value: "auth" } });
    expect(screen.getByRole("button", { name: "Search" })).toBeEnabled();
  });
});