import { render, screen, waitFor, fireEvent, within, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import CodePage from "@/app/code/page";
import { CodeWorkspace } from "@/components/code/CodeWorkspace";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";
import type { RepositoryOut } from "@/types/code";

vi.mock("next/navigation", () => ({
  usePathname: () => "/code",
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

// Deterministic plain highlighting — never loads shiki in tests.
vi.mock("@/lib/highlight", () => ({
  detectLanguage: vi.fn().mockReturnValue(null),
  isLanguageSupported: vi.fn().mockReturnValue(true),
  highlightCode: vi
    .fn()
    .mockResolvedValue({
      lines: [{ tokens: [{ content: "console.log", color: null }] }],
      highlighted: false,
      backgroundColor: null,
      foregroundColor: null,
    }),
  __resetHighlightMemo: vi.fn(),
}));

function notFound() {
  return new ApiError("unknown", 404, "No index found");
}

function makeRepo(id: string, name: string, fullName: string): RepositoryOut {
  return {
    id,
    name,
    full_name: fullName,
    private: false,
    default_branch: "main",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

const repo1 = makeRepo("r1", "novaforge", "acme/novaforge");
const repo2 = makeRepo("r2", "fintrack", "acme/fintrack");

const readyIndex = {
  id: "ix1",
  repository_id: "r1",
  status: "ready",
  branch: "main",
  file_count: 42,
  symbol_count: 300,
  index_size_bytes: 1024,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const fileDetail = {
  file: {
    id: "f1",
    index_id: "ix1",
    path: "src/budget/parse_amount.py",
    language: "python",
    size_bytes: 4096,
    line_count: 40,
    symbol_count: 3,
    status: "indexed",
  },
  symbols: [
    {
      id: "s1",
      name: "parse_amount",
      symbol_type: "FUNCTION",
      line_start: 4,
      line_end: 10,
      signature: "def parse_amount(raw: str) -> int",
    },
  ],
  references: [{ id: "ref1", reference_type: "call", line: 22 }],
  imports: [{ id: "imp1", module_path: "decimal", line: 1 }],
};

const symbolDetail = {
  id: "s1",
  file_id: "f1",
  name: "parse_amount",
  symbol_type: "FUNCTION",
  line_start: 4,
  line_end: 10,
  column_start: 0,
  column_end: 12,
  signature: "def parse_amount(raw: str) -> int",
  complexity: 2,
  calls: [{ callee_id: "s2", caller_id: "s1", call_type: "call", line: 7 }],
  called_by: [{ caller_id: "s0", callee_id: "s1", call_type: "call", line: 22 }],
  references: [{ id: "ref1", reference_type: "call", line: 22 }],
  children: [],
};

const impact = {
  affected_files: 3,
  affected_symbols: 5,
  breaking_changes: [
    { symbol_name: "parse_amount", symbol_type: "FUNCTION", file_path: "src/budget/parse_amount.py", line: 4, reason: "signature changed", severity: "high" },
  ],
  unused_items: [],
  impact_score: 0.4,
  risk_level: "medium",
};

function installApiMock() {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
    listRepositories: vi.fn().mockResolvedValue([repo1, repo2]),
    getRepository: vi.fn().mockImplementation(async (_t: string, id: string) =>
      id === "r1" ? repo1 : repo2,
    ),
    ciGetIndex: vi
      .fn()
      .mockImplementation(async (_t: string, id: string) =>
        id === "r1" ? readyIndex : Promise.reject(notFound()),
      ),
    ciRebuildIndex: vi.fn().mockResolvedValue(readyIndex),
    ciCreateIndex: vi.fn().mockResolvedValue(readyIndex),
    ciSearch: vi.fn().mockResolvedValue({
      query: "hello",
      total_results: 1,
      results: [
        {
          id: "f1",
          name: "parse_amount",
          result_type: "function",
          file_path: "src/budget/parse_amount.py",
          line: 4,
          score: 0.9,
          snippet: "def parse_amount(raw):\n    return int(raw)",
        },
      ],
      search_time_ms: 12,
    }),
    ciSymbolSearch: vi.fn().mockResolvedValue({
      total: 1,
      results: [
        { id: "s1", file_id: "f1", name: "parse_amount", symbol_type: "FUNCTION", line_start: 4, line_end: 10, column_start: 0, column_end: 12, complexity: 2 },
      ],
    }),
    ciFileDetail: vi.fn().mockResolvedValue(fileDetail),
    ciSymbolDetail: vi.fn().mockResolvedValue(symbolDetail),
    ciImpactAnalyze: vi.fn().mockResolvedValue(impact),
    ciGraph: vi.fn().mockResolvedValue({ nodes: [], edges: [], stats: {} }),
    aiDevExplain: vi.fn().mockResolvedValue({
      kind: "file",
      file_path: "src/budget/parse_amount.py",
      language: "python",
      line_count: 40,
      symbols: [],
      imports: [],
      snippets: [],
    }),
    aiDevChangesSummary: vi.fn().mockResolvedValue({
      repository_id: "r1",
      commit_sha: null,
      commit_message: "fix: parse amounts",
      author: "a@b.io",
      stats: { files: 1, additions: 3, deletions: 1 },
      notes: [],
    }),
    aiDevTestGenerate: vi.fn().mockResolvedValue({
      id: "tr1",
      repository_id: "r1",
      status: "planned",
      framework: "pytest",
      command: "pytest -q",
      test_plan: [],
    }),
    aiDevListAgents: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    aiDevGetAgent: vi.fn().mockResolvedValue({}),
    aiDevAgentPlans: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    aiDevAgentCheckpoints: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    aiDevAgentCancel: vi.fn().mockResolvedValue({}),
    aiDevAgentApprovePlan: vi.fn().mockResolvedValue({}),
    aiDevListPatches: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    aiDevGetPatch: vi.fn().mockResolvedValue({}),
    aiDevGetReview: vi.fn().mockResolvedValue({}),
  };
  for (const [key, value] of Object.entries(defaults)) {
    // Always override: the real api object already contains all code-*
    // methods, so an existence guard would keep the unmocked implementations.
    api[key] = value;
  }
  return api;
}

describe("Code Workspace", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the page shell with workspace title", async () => {
    render(<CodePage />);
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: "Code Intelligence" })).toBeInTheDocument(),
    );
    expect(screen.getAllByText(/novaforge/).length).toBeGreaterThan(0);
  });

  it("renders repositories with resolved index states", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    expect(screen.getByText("fintrack")).toBeInTheDocument();
    // r1 has a ready index; r2 404s → no data
    await waitFor(() => expect(screen.getByText("Indexed")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("No data")).toBeInTheDocument());
  });

  it("shows an empty state when no repositories exist", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.listRepositories.mockResolvedValueOnce([]);
    render(<CodeWorkspace />);
    await waitFor(() =>
      expect(screen.getByText(/No repositories are available in this workspace/)).toBeInTheDocument(),
    );
  });

  it("enables search and loads intelligence after selecting a repository", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    expect(screen.getByLabelText("Code search")).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());
    // Impact tab loads on selection
    await waitFor(() =>
      expect(
        (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).ciImpactAnalyze,
      ).toHaveBeenCalled(),
    );
    await waitFor(() => expect(screen.getByText("medium")).toBeInTheDocument());
  });

  it("runs hybrid search and renders the backend snippet as a read-only preview", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());

    fireEvent.change(screen.getByLabelText("Code search"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/parse_amount/)).toBeInTheDocument());
    expect(
      (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).ciSearch,
    ).toHaveBeenCalledWith("test-token", "r1", "hello", expect.anything());

    fireEvent.click(screen.getByRole("button", { name: /parse_amount/ }));
    await waitFor(() =>
      expect(screen.getByText(/Showing indexed code snippets/)).toBeInTheDocument(),
    );
    // Preview region is read-only — never an editable control
    const preview = screen.getByRole("region", { name: /code preview/i });
    expect(preview).toBeInTheDocument();
    expect(within(preview).queryByRole("textbox")).not.toBeInTheDocument();
  });

  it("loads file structure (symbols, references, imports) when a result is opened", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Code search"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/parse_amount/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /parse_amount/ }));

    await waitFor(() => expect(screen.getByText("Symbols")).toBeInTheDocument());
    expect(screen.getByText("References")).toBeInTheDocument();
    expect(screen.getByText("Imports")).toBeInTheDocument();
    expect(screen.getByText(/decimal/)).toBeInTheDocument();
  });

  it("shows the honest no-preview state when the backend carries no snippet", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.ciSearch.mockResolvedValueOnce({
      query: "hello",
      total_results: 1,
      results: [
        {
          id: "f1",
          name: "no_snippet_fn",
          result_type: "function",
          file_path: "src/budget/silent.py",
          score: 0.5,
          snippet: null,
        },
      ],
      search_time_ms: 4,
    });
    api.ciFileDetail.mockResolvedValueOnce({
      ...fileDetail,
      file: { ...fileDetail.file, path: "src/budget/silent.py" },
    });
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());
    fireEvent.change(screen.getByLabelText("Code search"), { target: { value: "hello" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(screen.getByText(/no_snippet_fn/)).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /no_snippet_fn/ }));
    await waitFor(() => expect(screen.getByText("Code preview unavailable")).toBeInTheDocument());
  });

  it("performs symbol-only search and loads symbol detail on selection", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());

    fireEvent.click(screen.getByLabelText("Symbols only"));
    fireEvent.change(screen.getByLabelText("Code search"), { target: { value: "parse" } });
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() =>
      expect(
        (apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>).ciSymbolSearch,
      ).toHaveBeenCalledWith("test-token", "r1", "parse"),
    );

    fireEvent.click(screen.getByRole("button", { name: /parse_amount/i }));
    await waitFor(() =>
      expect(screen.getByRole("region", { name: /symbol detail/i })).toBeInTheDocument(),
    );
    await waitFor(() => expect(screen.getByText("Callees (calls)")).toBeInTheDocument());
    expect(screen.getByText("Callers (called by)")).toBeInTheDocument();
    expect(screen.getByText("References")).toBeInTheDocument();
  });

  it("escalates 401s on repository load to a login redirect", async () => {
    const fakeLocation = { href: "" };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      api.getRepository.mockRejectedValueOnce(new ApiError("unauthorized", 401, "expired"));
      render(<CodeWorkspace />);
      await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
      await waitFor(() => expect(apiModule.clearToken).toHaveBeenCalled());
      expect(fakeLocation.href).toBe("/auth/login");
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("resets and reloads on tenant switch, without cross-workspace leakage", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    expect(api.listRepositories).toHaveBeenCalledTimes(1);

    await act(async () => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() => expect(api.listRepositories).toHaveBeenCalledTimes(2));
    // A previous selection must not carry across context switches
    expect(screen.getByLabelText("Code search")).toBeDisabled();
  });

  it("reindexes a stale index and creates a missing one", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.ciGetIndex.mockImplementation(async (_t: string, id: string) =>
      id === "r1" ? { ...readyIndex, status: "stale" } : Promise.reject(notFound()),
    );
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^reindex$/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /^reindex$/i }));
    await waitFor(() => expect(api.ciRebuildIndex).toHaveBeenCalledWith("test-token", "r1"));

    // Now select a repo with no index → Reindex turns into create
    fireEvent.click(screen.getByRole("button", { name: /fintrack/i }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /^reindex$/i })).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /^reindex$/i }));
    await waitFor(() =>
      expect(api.ciCreateIndex).toHaveBeenCalledWith("test-token", "r2", expect.anything(), true),
    );
  });

  it("keeps search results scoped to the selected repository panel", async () => {
    render(<CodeWorkspace />);
    await waitFor(() => expect(screen.getByText("novaforge")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: /novaforge/i }));
    await waitFor(() => expect(screen.getByLabelText("Code search")).toBeEnabled());
    expect(screen.getByText("Search indexed code")).toBeInTheDocument();
  });
});