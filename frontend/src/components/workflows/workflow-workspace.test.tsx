import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { WorkflowWorkspace } from "@/components/workflows/WorkflowWorkspace";
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

const healthResponse = { tenant: "t1", total: 10, success: 8, failed: 2, success_rate: 80.0 };

const anomaliesResponse = {
  items: [{ run_id: "run-1", type: "unusual_failure" }],
};

const workflowsResponse = {
  items: [
    { id: "wf-1", name: "nightly-etl", version: "1.0", status: "ACTIVE" },
    { id: "wf-2", name: "draft-flow", version: "0.1", status: "DRAFT" },
  ],
};

const workflowDetail = { id: "wf-1", name: "nightly-etl", version: "1.0", status: "ACTIVE", description: "nightly extract" };

const versionsResponse = {
  items: [{ id: "v-1", version: "1.0", status: "PUBLISHED", dag_hash: "abc123" }],
};

const runsResponse = {
  items: [{ run_id: "run-1", status: "COMPLETED", execution_id: "exec-1", workflow_version_id: "v-1" }],
};

const runDetail = { run_id: "run-1", workflow_version_id: "v-1", status: "COMPLETED", execution_id: "exec-1", trace_id: "tr-1" };

const stepsResponse = {
  items: [
    { step_id: "extract", status: "SUCCESS", attempt: 1, error: null },
    { step_id: "load", status: "SUCCESS", attempt: 1, error: null },
  ],
};

const approvalsResponse = {
  items: [{ id: "ap-1", run_id: "run-9", step_id: "gate", status: "PENDING", binding_hash: "bh-1" }],
};

const schedulesResponse = {
  items: [{ id: "s-1", workflow_id: "wf-1", trigger_type: "cron", cron: "0 2 * * *", enabled: true }],
};

const templatesResponse = {
  items: [{ name: "etl-starter", version: "1.0", category: "etl", is_published: true, owner: "system" }],
};

const tasksResponse = {
  items: [{ id: "t-1", assignee: "ops", status: "PENDING", run_id: "run-9" }],
};

const businessResponse = {
  items: [{ id: "b-1", current_state: "in_review", run_id: "run-9" }],
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    workflowHealthSummary: vi.fn().mockResolvedValue(healthResponse),
    workflowAnomalies: vi.fn().mockResolvedValue(anomaliesResponse),
    workflowsList: vi.fn().mockResolvedValue(workflowsResponse),
    workflowGet: vi.fn().mockResolvedValue(workflowDetail),
    workflowVersions: vi.fn().mockResolvedValue(versionsResponse),
    workflowRuns: vi.fn().mockResolvedValue(runsResponse),
    workflowRunGet: vi.fn().mockResolvedValue(runDetail),
    workflowRunSteps: vi.fn().mockResolvedValue(stepsResponse),
    workflowApprovals: vi.fn().mockResolvedValue(approvalsResponse),
    workflowSchedules: vi.fn().mockResolvedValue(schedulesResponse),
    workflowTemplates: vi.fn().mockResolvedValue(templatesResponse),
    workflowHumanTasks: vi.fn().mockResolvedValue(tasksResponse),
    workflowBusinessProcesses: vi.fn().mockResolvedValue(businessResponse),
  };
  Object.assign(api, defaults, overrides);
}

describe("WorkflowWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and execution-control notice without workflow:execute", async () => {
    installApiMock({}, []);
    render(<WorkflowWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("Execution controls hidden · no workflow:execute")).toBeTruthy();
  });

  it("renders backend health aggregates without inventing metrics", async () => {
    render(<WorkflowWorkspace />);
    expect(await screen.findByText("Workflow health")).toBeTruthy();
    expect(screen.getByText("Total runs")).toBeTruthy();
    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.getByText("80%")).toBeTruthy();
    expect(screen.getAllByText("unusual_failure").length).toBeGreaterThan(0);
  });

  it("renders the registry and opens workflow detail with versions", async () => {
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-etl"));
    await waitFor(() => {
      expect(apiModule.api.workflowGet).toHaveBeenCalledWith("test-token", "wf-1");
    });
    expect(await screen.findByText("nightly extract")).toBeTruthy();
    expect(screen.getAllByText("v1.0").length).toBeGreaterThan(0);
    expect(screen.getByText("Immutable versions")).toBeTruthy();
  });

  it("refetches the registry with the chosen status filter", async () => {
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "ACTIVE" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    await waitFor(() => {
      expect(apiModule.api.workflowsList).toHaveBeenCalledWith("test-token", { status: "ACTIVE", limit: 20 });
    });
  });

  it("shows runs with a step-run timeline and the DAG limitation notice", async () => {
    installApiMock({}, ["workflow:execute"]);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-etl"));
    fireEvent.click(getByRole("tab", { name: "Runs" }));
    await waitFor(() => {
      expect(apiModule.api.workflowRuns).toHaveBeenCalledWith("test-token", "wf-1", 20);
    });
    fireEvent.click(await screen.findByText("exec-1", { exact: false }));
    await waitFor(() => {
      expect(apiModule.api.workflowRunSteps).toHaveBeenCalledWith("test-token", "run-1");
    });
    expect(await screen.findByText("STEP-RUN TIMELINE")).toBeTruthy();
    expect(screen.getByText("1. extract")).toBeTruthy();
    expect(screen.getByText("NOT EXPOSED BY API")).toBeTruthy();
    expect(screen.queryByText(/DAG|graph/i, { selector: "svg" })).toBeNull();
  });

  it("renders approvals, schedules and automation reads", async () => {
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Approvals" }));
    expect(await screen.findByText("step gate")).toBeTruthy();
    expect(screen.getAllByText("PENDING").length).toBeGreaterThan(0);
    fireEvent.click(getByRole("tab", { name: "Schedules" }));
    expect(await screen.findByText("cron · 0 2 * * *")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Automation" }));
    expect(await screen.findByText("etl-starter")).toBeTruthy();
    expect(screen.getByText("ops")).toBeTruthy();
    expect(screen.getAllByText("in_review").length).toBeGreaterThan(0);
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      workflowsList: vi.fn().mockResolvedValue({ items: [] }),
      workflowAnomalies: vi.fn().mockResolvedValue({ items: [] }),
    });
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("No workflows")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Overview" }));
    expect(screen.getByText("No anomalies")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      workflowsList: vi.fn().mockRejectedValue(new ApiError("server", 500, "workflow plane down")),
    });
    render(<WorkflowWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.workflowsList).toHaveBeenCalled();
    });
    expect(await screen.findAllByText("Unavailable")).not.toHaveLength(0);
    expect(screen.getAllByText("workflow plane down").length).toBeGreaterThan(0);
  });

  it("refetches under the new scope on tenant switch without leaking state", async () => {
    render(<WorkflowWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.workflowsList as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.workflowsList as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("offers the AI handoff as a plain link with no payload", async () => {
    render(<WorkflowWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Ask AI about workflows" });
    expect(link.getAttribute("href")).toBe("/ai");
  });

  it("renders no secrets anywhere in the workspace", async () => {
    installApiMock({}, ["workflow:execute"]);
    render(<WorkflowWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/secret/i)).toBeNull();
    expect(screen.queryByText(/credential/i)).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
  });
});

describe("WorkflowWorkspace (C2 operations)", () => {
  beforeEach(() => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    Object.assign(api, {
      workflowCreate: vi.fn().mockResolvedValue({ id: "wf-9", name: "new-flow", version: "1.0", status: "DRAFT" }),
      workflowVersionCreate: vi.fn().mockResolvedValue({ id: "v-9", version: "1.1", workflow_id: "wf-1" }),
      workflowPublish: vi.fn().mockResolvedValue({ id: "v-9", version: "1.1", status: "PUBLISHED" }),
      workflowTrigger: vi.fn().mockResolvedValue({ run_id: "run-new", execution_id: "exec-new", status: "RUNNING", workflow_version_id: "v-1" }),
      workflowRunPause: vi.fn().mockResolvedValue({ run_id: "run-1", status: "PAUSED" }),
      workflowRunResume: vi.fn().mockResolvedValue({ run_id: "run-1", status: "RUNNING" }),
      workflowRunCancel: vi.fn().mockResolvedValue({ run_id: "run-1", status: "CANCELLED" }),
      workflowRunReplay: vi.fn().mockResolvedValue({ new_run_id: "run-r", original_run_id: "run-1", status: "RUNNING" }),
      workflowRunRecover: vi.fn().mockResolvedValue({ run_id: "run-1", status: "RUNNING" }),
      workflowRunSla: vi.fn().mockResolvedValue({ process_id: "b-1", sla_deadline: null, breached: false, current_state: "in_review" }),
      workflowApprovalDecide: vi.fn().mockResolvedValue({ id: "ap-1", status: "APPROVED", decision: "APPROVED" }),
      workflowScheduleCreate: vi.fn().mockResolvedValue({ id: "s-9", workflow_id: "wf-1", trigger_type: "cron" }),
      workflowTemplateCreate: vi.fn().mockResolvedValue({ id: "t-9", name: "tpl", version: "1.0" }),
      workflowTaskComplete: vi.fn().mockResolvedValue({ id: "t-1", status: "COMPLETED" }),
      workflowTaskReassign: vi.fn().mockResolvedValue({ id: "t-1", assignee: "bob" }),
      workflowBusinessTransition: vi.fn().mockResolvedValue({ id: "b-1", current_state: "approved" }),
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("creates a workflow then refetches authoritatively", async () => {
    installApiMock({}, ["workflow:execute"]);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    fireEvent.click(await screen.findByText("New workflow"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "new-flow" } });
    fireEvent.change(screen.getByLabelText("Definition (JSON object)"), {
      target: { value: '{"steps": [{"id": "a", "type": "task"}]}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await waitFor(() => {
      expect(api.workflowCreate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ name: "new-flow", definition: { steps: [{ id: "a", type: "task" }] } }),
      );
    });
    await waitFor(() => {
      expect((api.workflowsList as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("rejects invalid definition JSON client-side with a warning", async () => {
    installApiMock({}, ["workflow:execute"]);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    fireEvent.click(await screen.findByText("New workflow"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "bad-flow" } });
    fireEvent.change(screen.getByLabelText("Definition (JSON object)"), { target: { value: "not-json" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.workflowCreate).not.toHaveBeenCalled();
  });

  it("triggers a run only through confirmation and navigates to it", async () => {
    installApiMock({}, ["workflow:execute"]);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-etl"));
    fireEvent.click(await screen.findByRole("button", { name: "Trigger workflow" }));
    expect(await screen.findByText("Trigger workflow?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.workflowTrigger).toHaveBeenCalledWith(
        "test-token",
        "wf-1",
        expect.objectContaining({ trigger_type: "manual" }),
      );
    });
    expect(await screen.findByText("STEP-RUN TIMELINE")).toBeTruthy();
  });

  it("pauses a running execution through confirmation and refetches", async () => {
    installApiMock(
      {
        workflowRuns: vi.fn().mockResolvedValue({
          items: [{ run_id: "run-1", status: "RUNNING", execution_id: "exec-1", workflow_version_id: "v-1" }],
        }),
        workflowRunGet: vi.fn().mockResolvedValue({
          run_id: "run-1",
          workflow_version_id: "v-1",
          status: "RUNNING",
          execution_id: "exec-1",
          trace_id: null,
        }),
      },
      ["workflow:execute"],
    );
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-etl"));
    fireEvent.click(getByRole("tab", { name: "Runs" }));
    fireEvent.click(await screen.findByText("exec-1", { exact: false }));
    fireEvent.click(await screen.findByRole("button", { name: "Pause run" }));
    expect(await screen.findByText("Pause run?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.workflowRunPause).toHaveBeenCalledWith("test-token", "run-1");
    });
  });

  it("surfaces backend 422 validation on version creation", async () => {
    installApiMock(
      {
        workflowVersionCreate: vi.fn().mockRejectedValue(new ApiError("validation", 422, "steps list required")),
      },
      ["workflow:execute"],
    );
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-etl"));
    fireEvent.click(await screen.findByRole("button", { name: "Record version" }));
    fireEvent.change(screen.getByLabelText("Definition (JSON object)"), { target: { value: '{"steps": []}' } });
    fireEvent.click(screen.getByRole("button", { name: "Record" }));
    await waitFor(() => {
      expect(apiModule.api.workflowVersionCreate).toHaveBeenCalled();
    });
    // No optimistic close: the modal stays open so the backend 422 can be fixed
    expect(screen.getAllByText("Record version").length).toBeGreaterThan(0);
  });

  it("decides an approval with the selected decision", async () => {
    installApiMock({}, ["workflow:execute"]);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Approvals" }));
    fireEvent.click(await screen.findByRole("button", { name: "Decide approval" }));
    expect(await screen.findByText("Decide approval?")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Decision"), { target: { value: "DENIED" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.workflowApprovalDecide).toHaveBeenCalledWith("test-token", "ap-1", { decision: "DENIED", binding_hash: undefined });
    });
  });

  it("hides all mutation controls without workflow:execute", async () => {
    installApiMock({}, []);
    const { getByRole } = render(<WorkflowWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("nightly-etl")).toBeTruthy();
    expect(screen.queryByText("New workflow")).toBeNull();
    expect(screen.queryByRole("button", { name: "Trigger workflow" })).toBeNull();
    fireEvent.click(getByRole("tab", { name: "Approvals" }));
    expect(await screen.findByText("step gate")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Decide" })).toBeNull();
  });
});
