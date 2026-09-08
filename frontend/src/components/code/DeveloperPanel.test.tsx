import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DeveloperPanel } from "@/components/code/DeveloperPanel";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

const fileExplain = {
  kind: "file",
  file_path: "src/budget/parse_amount.py",
  language: "python",
  line_count: 40,
  symbols: [{ name: "parse_amount", type: "FUNCTION", line_start: 4, line_end: 10 }],
  imports: ["decimal"],
  snippets: [{ content: "def parse_amount(raw):\n    return int(raw)", line_start: 1, line_end: 2 }],
};

const agent = {
  id: "run1",
  repository_id: "r1",
  agent_type: "refactor",
  name: "refactor-agent",
  goal: "Clean up the parser module",
  model: "gpt-4o",
  status: "running",
  created_at: "2026-09-08T00:00:00Z",
};

const plan = {
  id: "plan1",
  agent_run_id: "run1",
  plan_type: "refactor",
  name: "Plan: rename variable",
  steps: [{ step: 1, action: "rename" }],
  rationale: "Shorter identifier, safer scope.",
  approved: false,
  rejected: false,
};

const patch = {
  id: "p1",
  repository_id: "r1",
  title: "Add parser tests",
  branch: "patch/tests",
  status: "pending",
  files: [],
  diffs: { "tests/test_parser.py": "--- a/tests/test_parser.py\n+++ b/tests/test_parser.py\n+assert parse_amount(\"1.5\")" },
  source: "ai",
  base_commit_sha: "abc123",
};

const reviewDetail = {
  review: { summary: "Added input validation for amounts", status: "completed" },
  findings: [
    {
      id: "f1",
      file_path: "src/main.py",
      line_start: 3,
      line_end: 5,
      category: "security",
      severity: "high",
      message: "Unsafe eval of user input",
      reason: "raw input reaches eval",
      confidence: 0.9,
      status: "open",
      suggested_fix: "replace eval with int()",
    },
  ],
};

function installApiMock() {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
    aiDevExplain: vi.fn().mockResolvedValue(fileExplain),
    aiDevChangesSummary: vi.fn().mockResolvedValue({
      repository_id: "r1",
      commit_sha: null,
      commit_message: "fix: parse amounts",
      author: "a@b.io",
      stats: { files: 1, additions: 3, deletions: 1 },
      notes: ["Consider f-strings"],
    }),
    aiDevTestGenerate: vi.fn().mockResolvedValue({
      id: "tr1",
      repository_id: "r1",
      status: "planned",
      framework: "pytest",
      command: "pytest -q",
      test_plan: [{ test: "parse valid amount" }],
    }),
    ciGraph: vi.fn().mockResolvedValue({ nodes: [], edges: [], stats: {} }),
    aiDevListAgents: vi.fn().mockResolvedValue({ items: [], count: 0 }),
    aiDevGetAgent: vi.fn().mockResolvedValue(agent),
    aiDevAgentPlans: vi.fn().mockResolvedValue({ items: [plan], count: 1 }),
    aiDevAgentCheckpoints: vi.fn().mockResolvedValue({
      items: [{ id: "c1", sequence: 1, summary: "repo loaded", state: {}, is_final: false }],
      count: 1,
    }),
    aiDevAgentCancel: vi.fn().mockResolvedValue(agent),
    aiDevAgentApprovePlan: vi.fn().mockResolvedValue(plan),
    aiDevListPatches: vi.fn().mockResolvedValue({ items: [patch], count: 1 }),
    aiDevGetPatch: vi.fn().mockResolvedValue(patch),
    aiDevGetReview: vi.fn().mockResolvedValue(reviewDetail),
  };
  for (const [key, value] of Object.entries(defaults)) {
    api[key] = value;
  }
  return api;
}

describe("DeveloperPanel (developer intelligence)", () => {
  beforeEach(() => {
    installApiMock();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders developer tabs, a11y semantics and the honest capability note", async () => {
    render(
      <DeveloperPanel key="r1" repoId="r1" defaultBranch="main" />,
    );

    const tablist = screen.getByRole("tablist", { name: /developer intelligence/i });
    expect(tablist).toBeInTheDocument();

    const tabs = within(tablist).getAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual([
      "Explain",
      "Changes",
      "Tests",
      "Graph",
      "Agents",
      "Patches",
    ]);
    expect(within(tablist).getByRole("tab", { name: "Explain" })).toHaveAttribute(
      "aria-selected",
      "true",
    );

    fireEvent.click(screen.getByRole("tab", { name: "Patches" }));
    await waitFor(() =>
      expect(
        screen.getByText(/backend only starts reviews from inlined file content/i),
      ).toBeInTheDocument(),
    );
    expect(screen.queryByRole("button", { name: /^apply/i })).not.toBeInTheDocument();
  });

  it("explains a file against the real backend", async () => {
    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);
    const api = installApiMock();

    fireEvent.change(screen.getByLabelText("Target"), {
      target: { value: "src/budget/parse_amount.py" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));

    await waitFor(() =>
      expect(api.aiDevExplain).toHaveBeenCalledWith("test-token", {
        repository_id: "r1",
        kind: "file",
        target: "src/budget/parse_amount.py",
        top: 20,
      }),
    );
    expect(await screen.findByText("src/budget/parse_amount.py")).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
    expect(screen.getByText("decimal")).toBeInTheDocument();
    expect(screen.getByText(/parse_amount \(FUNCTION\)/)).toBeInTheDocument();
    expect(screen.getByText(/lines 4–10/)).toBeInTheDocument();
    expect(screen.getByText(/def parse_amount/)).toBeInTheDocument();
  });

  it("renders explanation snippets and imports as inert text (XSS safe)", async () => {
    const api = installApiMock();
    api.aiDevExplain.mockResolvedValueOnce({
      kind: "file",
      file_path: "evil.py",
      language: "python",
      line_count: 1,
      symbols: [],
      imports: ["<script>window.pwned=1</script>"],
      snippets: [{ content: "<img src=x onerror=alert(1)>", line_start: 1, line_end: 1 }],
    });
    const { container } = render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "evil.py" } });
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));

    await waitFor(() => expect(screen.getByText(/<img src=x/)).toBeInTheDocument());
    expect(screen.getByText(/<script>window\.pwned/)).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("analyzes changes for a specific commit", async () => {
    const api = installApiMock();
    api.aiDevChangesSummary.mockResolvedValueOnce({
      repository_id: "r1",
      commit_sha: "abc123",
      commit_message: "fix: parse amounts",
      author: "a@b.io",
      stats: { files: 1, additions: 3, deletions: 1 },
      notes: ["Consider f-strings"],
    });
    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.click(screen.getByRole("tab", { name: "Changes" }));
    fireEvent.change(screen.getByLabelText("Commit SHA (optional)"), { target: { value: "abc123" } });
    fireEvent.click(screen.getByRole("button", { name: "Analyze changes" }));

    await waitFor(() =>
      expect(api.aiDevChangesSummary).toHaveBeenCalledWith("test-token", {
        repository_id: "r1",
        commit_sha: "abc123",
      }),
    );
    expect(await screen.findByText("fix: parse amounts")).toBeInTheDocument();
    expect(screen.getByText(/\+3 −1/)).toBeInTheDocument();
    expect(screen.getByText("Consider f-strings")).toBeInTheDocument();
  });

  it("suggests tests against the backend", async () => {
    const api = installApiMock();
    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.click(screen.getByRole("tab", { name: "Tests" }));
    fireEvent.click(screen.getByRole("button", { name: "Suggest tests" }));

    await waitFor(() =>
      expect(api.aiDevTestGenerate).toHaveBeenCalledWith("test-token", {
        repository_id: "r1",
        branch: "main",
        framework: null,
      }),
    );
    expect(await screen.findByText("planned")).toBeInTheDocument();
    expect(screen.getByText(/pytest -q/)).toBeInTheDocument();
    expect(screen.getByText(/parse valid amount/)).toBeInTheDocument();
  });

  it("loads a bounded dependency graph", async () => {
    const api = installApiMock();
    const nodes = Array.from({ length: 200 }, (_, i) => ({ id: `n${i}`, label: `n${i}`, type: "file", file_path: `src/f${i}.py` }));
    const edges = Array.from({ length: 150 }, (_, i) => ({ source: `n${i}`, target: `n${i + 1}`, edge_type: "import", weight: 1 }));
    api.ciGraph.mockResolvedValueOnce({ nodes, edges, stats: {} });

    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);
    fireEvent.click(screen.getByRole("tab", { name: "Graph" }));

    await waitFor(() =>
      expect(api.ciGraph).toHaveBeenCalledWith("test-token", "r1", 100),
    );
    expect(await screen.findByText(/bounded to the first 100/i)).toBeInTheDocument();
    expect(screen.getByText("200")).toBeInTheDocument();
    expect(screen.getByText("150")).toBeInTheDocument();
    expect(screen.getByText(/n0 → n1/)).toBeInTheDocument();
    expect(screen.getByText(/50 more edges truncated/)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").length).toBe(100);
  });

  it("lists agents, loads detail and approves a governed plan with the approver identity", async () => {
    const api = installApiMock();
    api.aiDevListAgents.mockResolvedValueOnce({ items: [agent], count: 1 });

    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);
    fireEvent.click(screen.getByRole("tab", { name: "Agents" }));

    expect(await screen.findByText("refactor-agent")).toBeInTheDocument();
    await waitFor(() =>
      expect(api.aiDevListAgents).toHaveBeenCalledWith("test-token", { repositoryId: "r1" }),
    );

    fireEvent.click(screen.getByRole("button", { name: /refactor-agent/i }));
    expect(await screen.findByText("Plan: rename variable")).toBeInTheDocument();
    await waitFor(() => expect(api.aiDevAgentPlans).toHaveBeenCalledWith("test-token", "run1"));
    await waitFor(() => expect(api.aiDevAgentCheckpoints).toHaveBeenCalledWith("test-token", "run1"));
    expect(screen.getByText("Clean up the parser module")).toBeInTheDocument();
    expect(screen.getByText("repo loaded")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Approve plan" }));
    await waitFor(() =>
      expect(api.aiDevAgentApprovePlan).toHaveBeenCalledWith(
        "test-token",
        "run1",
        "plan1",
        expect.objectContaining({ approved: true, approved_by: "a@b.io" }),
      ),
    );
  });

  it("cancels a running agent run via the governed endpoint", async () => {
    const api = installApiMock();
    api.aiDevListAgents.mockResolvedValueOnce({ items: [agent], count: 1 });

    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);
    fireEvent.click(screen.getByRole("tab", { name: "Agents" }));

    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(api.aiDevAgentCancel).toHaveBeenCalledWith("test-token", "run1", expect.any(String)),
    );
  });

  it("lists patches and shows read-only diff text without apply/rollback actions", async () => {
    const api = installApiMock();
    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.click(screen.getByRole("tab", { name: "Patches" }));
    expect(await screen.findByText("Add parser tests")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Add parser tests/i }));
    await waitFor(() => expect(api.aiDevGetPatch).toHaveBeenCalledWith("test-token", "p1"));
    expect(await screen.findByText(/assert parse_amount/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /roll.?back/i })).not.toBeInTheDocument();
  });

  it("looks up an existing governed review by id", async () => {
    const api = installApiMock();
    render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.click(screen.getByRole("tab", { name: "Patches" }));
    fireEvent.change(screen.getByLabelText("Review ID"), { target: { value: "rev-42" } });
    fireEvent.click(screen.getByRole("button", { name: "Load review" }));

    await waitFor(() => expect(api.aiDevGetReview).toHaveBeenCalledWith("test-token", "rev-42"));
    expect(await screen.findByText("Added input validation for amounts")).toBeInTheDocument();
    expect(screen.getByText("Unsafe eval of user input")).toBeInTheDocument();
    expect(screen.getByText("high")).toBeInTheDocument();
    expect(screen.getByText(/replace eval with int\(\)/)).toBeInTheDocument();
    expect(screen.getByText(/src\/main\.py:3–5/)).toBeInTheDocument();
  });

  it("renders review findings as inert text (no HTML injection)", async () => {
    const api = installApiMock();
    api.aiDevGetReview.mockResolvedValueOnce({
      review: { status: "completed" },
      findings: [
        {
          id: "f1",
          file_path: "src/main.py",
          line_start: 1,
          line_end: 1,
          category: "security",
          severity: "high",
          message: "<img src=x onerror=alert(1)>",
          reason: null,
          confidence: 1,
          status: "open",
          suggested_fix: null,
        },
      ],
    });
    const { container } = render(<DeveloperPanel repoId="r1" defaultBranch="main" />);

    fireEvent.click(screen.getByRole("tab", { name: "Patches" }));
    fireEvent.change(screen.getByLabelText("Review ID"), { target: { value: "rev-9" } });
    fireEvent.click(screen.getByRole("button", { name: "Load review" }));

    await waitFor(() => expect(screen.getByText(/<img src=x/)).toBeInTheDocument());
    expect(container.querySelector("img")).toBeNull();
  });

  it("escalates unauthorized errors to the login redirect", async () => {
    const api = installApiMock();
    api.aiDevListAgents.mockRejectedValueOnce(new ApiError("unauthorized", 401, "expired"));
    const fakeLocation = { href: "" };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      render(<DeveloperPanel repoId="r1" defaultBranch="main" />);
      fireEvent.click(screen.getByRole("tab", { name: "Agents" }));
      await waitFor(() => expect(fakeLocation.href).toBe("/auth/login"));
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("resets developer state when the repository changes (keyed remount)", async () => {
    installApiMock();
    const first = render(<DeveloperPanel key="r1" repoId="r1" defaultBranch="main" />);

    fireEvent.change(screen.getByLabelText("Target"), { target: { value: "src/a.py" } });
    fireEvent.click(screen.getByRole("button", { name: "Explain" }));
    expect(await screen.findByText("src/budget/parse_amount.py")).toBeInTheDocument();

    first.rerender(<DeveloperPanel key="r2" repoId="r2" defaultBranch="main" />);
    expect(screen.queryByText("src/budget/parse_amount.py")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Target")).toHaveValue("");
  });
});