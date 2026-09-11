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
