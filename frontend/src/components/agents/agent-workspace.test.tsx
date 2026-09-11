import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AgentWorkspace } from "@/components/agents/AgentWorkspace";
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

const catalogResponse = [
  { name: "planner", role: "planner", version: "1.0.0", description: "Plans work", goals: ["plan"] },
  { name: "reviewer", role: "code_reviewer", version: "2.1.0", description: "Reviews code", goals: [] },
];

const agentInfo = {
  name: "planner",
  role: "planner",
  version: "1.0.0",
  description: "Plans work",
  goals: ["plan"],
  model: "gpt-4o",
  temperature: 0.3,
  permissions: ["read", "plan"],
  require_human_approval: true,
};

const v2Runs = [
  { id: "r-1", agent: "planner", status: "completed", duration_ms: 1200, tokens_used: 300, model_used: "gpt-4o", error: null, created_at: "2026-09-09T10:00:00Z" },
  { id: "r-2", agent: "reviewer", status: "failed", duration_ms: 400, tokens_used: 50, model_used: "gpt-4o", error: "timeout", created_at: "2026-09-09T11:00:00Z" },
];

const v2RunDetail = {
  id: "r-1",
  agent: "planner",
  status: "completed",
  duration_ms: 1200,
  tokens_used: 300,
  model_used: "gpt-4o",
  error: null,
  created_at: "2026-09-09T10:00:00Z",
  pipeline: null,
  input: { task: "plan it" },
  output: "done",
  extra: {
    confidence: 0.9,
    risk: "low",
    files_affected: ["a.py"],
    tool_calls: [{ success: true, duration_ms: 100 }, { success: false, duration_ms: 50 }],
  },
};

const aiRuns = {
  items: [
    {
      id: "a-1",
      repository_id: "repo-1",
      agent_type: "refactor",
      name: "cleanup",
      goal: "tidy module",
      status: "completed",
      model: "gpt-4o",
      result: "refactored 3 files",
      last_error: null,
      created_at: "2026-09-09T10:00:00Z",
      start_time: "2026-09-09T10:00:00Z",
      end_time: "2026-09-09T10:05:00Z",
      tokens_used: 1200,
      attempts: 1,
    },
  ],
  count: 1,
};

const aiRunDetail = { ...aiRuns.items[0] };
const plansResponse = {
  items: [
    {
      id: "p-1",
      agent_run_id: "a-1",
      plan_type: "PLAN",
      name: "Phase one",
      steps: [{ name: "scan" }],
      rationale: "Start with a scan because the module is large and unwieldy in places.",
      approved: true,
      approved_by: "ops@acme.test",
      rejected: false,
    },
  ],
  count: 1,
};
const checkpointsResponse = {
  items: [{ id: "c-1", sequence: 1, summary: "scan done", state: { cursor: 5 }, is_final: false }],
  count: 1,
};
const feedbackResponse = {
  items: [{ id: "f-1", feedback_type: "CONTINUE", message: "looks good", patch_id: null, checkpoint_id: null, created_by: "ops", created_at: "2026-09-09T10:03:00Z" }],
  count: 1,
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    agentsV2Catalog: vi.fn().mockResolvedValue(catalogResponse),
    agentsV2Info: vi.fn().mockResolvedValue(agentInfo),
    agentsV2Runs: vi.fn().mockResolvedValue(v2Runs),
    agentsV2RunGet: vi.fn().mockResolvedValue(v2RunDetail),
    aiDevListAgents: vi.fn().mockResolvedValue(aiRuns),
    aiDevGetAgent: vi.fn().mockResolvedValue(aiRunDetail),
    aiDevAgentPlans: vi.fn().mockResolvedValue(plansResponse),
    aiDevAgentCheckpoints: vi.fn().mockResolvedValue(checkpointsResponse),
    agentsAiDevFeedback: vi.fn().mockResolvedValue(feedbackResponse),
  };
  Object.assign(api, defaults, overrides);
}

describe("AgentWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and read-only notice without permissions", async () => {
    installApiMock({}, []);
    render(<AgentWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("Read-only view · no repository permissions")).toBeTruthy();
  });

  it("renders backend-backed overview counts without totals", async () => {
    render(<AgentWorkspace />);
    expect(await screen.findByText("Registered agents")).toBeTruthy();
    expect(screen.getByText("Agents listed")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Listed count only — the backend reports no totals.")).toBeTruthy();
  });

  it("renders the catalog and agent detail with guardrails", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Catalog" }));
    expect(await screen.findByRole("button", { name: "View agent planner" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View agent planner" }));
    await waitFor(() => {
      expect(apiModule.api.agentsV2Info).toHaveBeenCalledWith("planner");
    });
    expect(await screen.findByText("Human approval")).toBeTruthy();
    expect(screen.getByText("required")).toBeTruthy();
    expect(screen.getByText("read, plan")).toBeTruthy();
  });

  it("renders run history and safe run detail without reasoning", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Runs" }));
    expect(await screen.findByRole("button", { name: "View run r-2" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Agent"), { target: { value: "planner" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(apiModule.api.agentsV2Runs).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ agentName: "planner" }),
      );
    });
    fireEvent.click(getByRole("tab", { name: "Runs" }));
    fireEvent.click(await screen.findByRole("button", { name: "View run r-1" }));
    await waitFor(() => {
      expect(apiModule.api.agentsV2RunGet).toHaveBeenCalledWith("test-token", "r-1");
    });
    expect(await screen.findByText("Decision metadata")).toBeTruthy();
    expect(screen.getByText("2 recorded · 1 succeeded")).toBeTruthy();
    expect(screen.queryByText(/reasoning/i)).toBeNull();
  });

  it("renders executions with plans, checkpoints and feedback", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    await waitFor(() => {
      expect(apiModule.api.aiDevGetAgent).toHaveBeenCalledWith("test-token", "a-1");
    });
    expect(await screen.findByText("Phase one")).toBeTruthy();
    expect(screen.getByText("approved")).toBeTruthy();
    expect(screen.getByText("#1 · scan done")).toBeTruthy();
    expect(screen.getByText("looks good")).toBeTruthy();
    expect(screen.queryByText(/cursor/i)).toBeNull();
  });

  it("renders plan rationale as labeled plain text, never reasoning", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    expect(await screen.findByText("PLAN RATIONALE")).toBeTruthy();
    expect(screen.getByText(/Start with a scan/)).toBeTruthy();
    expect(screen.queryByText(/model reasoning|chain-of-thought/i)).toBeNull();
  });

  it("builds the timeline from returned records only", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    await waitFor(() => {
      expect(apiModule.api.aiDevAgentPlans).toHaveBeenCalled();
    });
    fireEvent.click(getByRole("tab", { name: "Timeline" }));
    expect(await screen.findByText("RUN CREATED")).toBeTruthy();
    expect(screen.getByText(/PLAN 1/)).toBeTruthy();
    expect(screen.getByText(/CHECKPOINT #1/)).toBeTruthy();
    expect(screen.getByText(/FEEDBACK/)).toBeTruthy();
  });

  it("declares unexposed capabilities honestly", async () => {
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Timeline" }));
    expect(await screen.findByText("Memory")).toBeTruthy();
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(4);
    expect(screen.getByText("Version history")).toBeTruthy();
    expect(screen.getByText("Schedules / triggers")).toBeTruthy();
    expect(screen.getByText("Audit history")).toBeTruthy();
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      agentsV2Catalog: vi.fn().mockResolvedValue([]),
      agentsV2Runs: vi.fn().mockResolvedValue([]),
    });
    render(<AgentWorkspace />);
    expect(await screen.findByText("No agents registered")).toBeTruthy();
    expect(screen.getByText("No runs")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      agentsV2Catalog: vi.fn().mockRejectedValue(new ApiError("server", 500, "agent plane down")),
    });
    render(<AgentWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.agentsV2Catalog).toHaveBeenCalled();
    });
    expect(await screen.findAllByText("Unavailable")).not.toHaveLength(0);
    expect(screen.getByText("agent plane down")).toBeTruthy();
  });

  it("refetches under the new scope on tenant switch without leaking state", async () => {
    render(<AgentWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.agentsV2Runs as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.agentsV2Runs as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("offers the AI handoff as a plain link with no payload", async () => {
    render(<AgentWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Ask AI about agents" });
    expect(link.getAttribute("href")).toBe("/ai");
  });

  it("renders no secrets anywhere in the workspace", async () => {
    installApiMock({}, ["repository:read", "repository:write"]);
    render(<AgentWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/secret/i)).toBeNull();
    expect(screen.queryByText(/credential/i)).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
    expect(screen.queryByText(/api[_-]?key/i)).toBeNull();
  });
});

describe("AgentWorkspace (C2 operations)", () => {
  beforeEach(() => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    Object.assign(api, {
      agentsEnqueue: vi.fn().mockResolvedValue({ id: "a-9", name: "new-run", status: "pending" }),
      agentsExecute: vi.fn().mockResolvedValue({ id: "a-1", status: "completed" }),
      agentsPlanCreate: vi.fn().mockResolvedValue({ id: "p-9", name: "Phase two", approved: false }),
      agentsCheckpointSave: vi.fn().mockResolvedValue({ id: "c-9", sequence: 2, summary: "mid", state: {}, is_final: false }),
      agentsFeedbackSubmit: vi.fn().mockResolvedValue({ id: "f-9", feedback_type: "CONTINUE" }),
      agentsV2RunAgent: vi.fn().mockResolvedValue({ run_id: "r-9", agent: "planner", status: "completed", decision: { confidence: 0.8 } }),
      agentsV2Pipeline: vi.fn().mockResolvedValue({ workflow_id: "w-9", status: "completed", steps: [], errors: [] }),
      aiDevAgentCancel: vi.fn().mockResolvedValue({ id: "a-1", status: "cancelled" }),
      aiDevAgentApprovePlan: vi.fn().mockResolvedValue({ id: "p-1", approved: true }),
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("hides execution controls without repository:write", async () => {
    installApiMock({}, ["repository:read"]);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    expect(await screen.findByText("Execution controls require repository:write")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Enqueue agent" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Execute run" })).toBeNull();
  });

  it("enqueues an agent then refetches authoritatively", async () => {
    installApiMock({}, ["repository:read", "repository:write"]);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "Enqueue agent" }));
    const enqueueDialog = await screen.findByRole("dialog");
    const { within: withinDialog } = await import("@testing-library/react");
    fireEvent.change(withinDialog(enqueueDialog).getByLabelText("Repository ID"), { target: { value: "repo-1" } });
    fireEvent.change(withinDialog(enqueueDialog).getByLabelText("Goal"), { target: { value: "tidy up" } });
    fireEvent.click(withinDialog(enqueueDialog).getByRole("button", { name: "Enqueue" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await waitFor(() => {
      expect(api.agentsEnqueue).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ repository_id: "repo-1", goal: "tidy up" }),
      );
    });
    await waitFor(() => {
      expect((api.aiDevListAgents as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("runs a v2 agent only after confirmation with a long-running warning", async () => {
    installApiMock({}, []);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Catalog" }));
    fireEvent.click(await screen.findByRole("button", { name: "View agent planner" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run agent planner" }));
    expect(await screen.findByText("Run agent?")).toBeTruthy();
    expect(screen.getByText(/may take several minutes/)).toBeTruthy();
    // Not executed before confirmation
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.agentsV2RunAgent).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "plan the release" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(api.agentsV2RunAgent).toHaveBeenCalledWith(
        "test-token",
        "planner",
        expect.objectContaining({ task: "plan the release" }),
      );
    });
    expect(await screen.findByText("SERVER-SIDE", { exact: false })).toBeTruthy();
  });

  it("states timeout explicitly without claiming cancellation", async () => {
    installApiMock({}, []);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Catalog" }));
    fireEvent.click(await screen.findByRole("button", { name: "View agent planner" }));
    fireEvent.click(await screen.findByRole("button", { name: "Run agent planner" }));
    fireEvent.change(screen.getByLabelText("Task"), { target: { value: "slow task" } });
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    (api.agentsV2RunAgent as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("timeout", 0, "Request timed out after 300000ms"),
    );
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/EXECUTION REQUEST TIMED OUT/)).toBeTruthy();
    expect(screen.getByText(/may still be processing/)).toBeTruthy();
  });

  it("approves a plan through confirmation and refetches", async () => {
    installApiMock(
      {
        aiDevAgentPlans: vi.fn().mockResolvedValue({
          items: [
            {
              id: "p-9",
              agent_run_id: "a-1",
              plan_type: "PLAN",
              name: "Phase two",
              steps: [],
              rationale: null,
              approved: false,
              approved_by: null,
              rejected: false,
            },
          ],
          count: 1,
        }),
      },
      ["repository:read", "repository:write"],
    );
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve plan" }));
    expect(await screen.findByText("Approve plan?")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Approved by"), { target: { value: "ops@acme.test" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.aiDevAgentApprovePlan).toHaveBeenCalledWith("test-token", "a-1", "p-9", {
        approved: true,
        approved_by: "ops@acme.test",
      });
    });
  });

  it("cancels a run through confirmation", async () => {
    installApiMock({}, ["repository:read", "repository:write"]);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel run" }));
    expect(await screen.findByText("Cancel execution?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.aiDevAgentCancel).toHaveBeenCalled();
    });
  });

  it("records a plan and submits feedback", async () => {
    installApiMock({}, ["repository:read", "repository:write"]);
    const { getByRole } = render(<AgentWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Executions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View execution a-1" }));
    fireEvent.click(await screen.findByRole("button", { name: "Record plan" }));
    const planDialog = await screen.findByRole("dialog");
    const { within: withinPlan } = await import("@testing-library/react");
    fireEvent.change(withinPlan(planDialog).getByLabelText("Name"), { target: { value: "Phase two" } });
    fireEvent.click(withinPlan(planDialog).getByRole("button", { name: "Record" }));
    await waitFor(() => {
      expect(apiModule.api.agentsPlanCreate).toHaveBeenCalledWith(
        "test-token",
        "a-1",
        expect.objectContaining({ name: "Phase two" }),
      );
    });
    fireEvent.click(await screen.findByRole("button", { name: "Feedback" }));
    fireEvent.change(screen.getByLabelText("Message"), { target: { value: "keep going" } });
    fireEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => {
      expect(apiModule.api.agentsFeedbackSubmit).toHaveBeenCalledWith(
        "test-token",
        "a-1",
        expect.objectContaining({ message: "keep going" }),
      );
    });
  });
});
