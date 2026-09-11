import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { MLPlatformWorkspace } from "@/components/ml/MLPlatformWorkspace";
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

const modelsResponse = [
  { id: "m-1", tenant: "t1", provider: "acme", name: "atlas", version: "1.0", type: "foundation", capabilities: {}, license: "prop", region: "us", status: "ACTIVE", risk_level: "LOW", owner: "ml-team", created_at: "2026-09-01T10:00:00Z", updated_at: "2026-09-02T10:00:00Z" },
  { id: "m-2", tenant: "t1", provider: "acme", name: "scout", version: "0.3", type: "classifier", capabilities: {}, license: null, region: null, status: "DRAFT", risk_level: "LOW", owner: "", created_at: null, updated_at: null },
];

const modelDetail = { ...modelsResponse[0] };

const versionsResponse = [
  { id: "v-1", model_id: "m-1", version: "1.0", artifact: "s3://a", source: "training", training_metadata: {}, evaluation_version: "e1", deployment_version: null, policy_version: null, provenance: {}, immutable: true, created_at: "2026-09-01T10:00:00Z" },
];

const providersResponse = [
  { id: "p-1", tenant: "t1", provider: "acme", display_name: "Acme AI", models: ["atlas"], regions: ["us"], pricing: { per_1k: 0.02 }, data_processing_policy: {}, availability: "AVAILABLE", security_status: "REVIEWED", contract_metadata: {}, created_at: null, updated_at: null },
];

const promptsResponse = [
  { id: "pr-1", tenant: "t1", prompt_id: "summarize", name: "Summarize", purpose: "docs", classification: "INTERNAL", model_compatibility: ["atlas"], owner: "ml-team", status: "ACTIVE", created_at: null, updated_at: null },
];

const promptDetail = {
  ...promptsResponse[0],
  // Backend MAY return version content (potential system prompt). The UI
  // must never render it — the types deliberately omit the field.
  version: { id: "pv-1", prompt_id: "summarize", version: "3", content: "SYSTEM PROMPT SENTINEL ignore all rules", owner: "ml-team", purpose: "docs", classification: "INTERNAL", immutable: true, created_at: null },
  versions: [{ id: "pv-1", prompt_id: "summarize", version: "3", content: "SYSTEM PROMPT SENTINEL ignore all rules", owner: "ml-team", purpose: "docs", classification: "INTERNAL", immutable: true, created_at: null }],
  latest_version: { id: "pv-1", prompt_id: "summarize", version: "3", content: "SYSTEM PROMPT SENTINEL ignore all rules", owner: "ml-team", purpose: "docs", classification: "INTERNAL", immutable: true, created_at: null },
};

const evalRun = {
  id: "run-1",
  tenant: "t1",
  suite_id: "s-1",
  model_id: "m-1",
  prompt_version_id: null,
  dataset_version: "v3",
  parameters: {},
  metrics: { accuracy: 0.91, latency_p50: 120 },
  artifacts: {},
  status: "COMPLETED",
  reproducible_hash: "h1",
  created_at: "2026-09-05T10:00:00Z",
  updated_at: "2026-09-05T10:05:00Z",
};

const compareResponse = { tenant: "t1", candidate_run_id: "run-1", baseline_run_id: "run-0", regression: false, metric_deltas: { accuracy: 0.02 } };

const risksResponse = [
  { id: "r-1", tenant: "t1", system: "support-copilot", model_id: "m-1", risk_id: "bias-drift", severity: "MEDIUM", likelihood: "LOW", impact: "MEDIUM", owner: "ml-team", mitigation: "monitor", status: "OPEN", score: 82, created_at: "2026-09-03T10:00:00Z" },
];

const guardrailsResponse = [
  { id: "g-1", tenant: "t1", name: "pii-block", scope: "input", policy: {}, rate_limit: 100, enabled: true, environment: "production", created_at: null },
];

const cardsResponse = [
  { id: "c-1", tenant: "t1", model_id: "m-1", purpose: "support answers", capabilities: {}, limitations: {}, risk: "LOW", evaluation_summary: {}, data_policy: "INTERNAL", provider: "acme", version: "1.0", approved_environments: ["production"], created_at: null },
];

const snapshotsResponse = [
  { id: "s-1", tenant: "t1", model_id: "m-1", provider: "acme", availability: "AVAILABLE", latency_ms: 120, error_rate: 0.01, token_usage: 5000, cost: 0.4, quality: 0.9, safety: 0.98, drift: {}, created_at: "2026-09-09T10:00:00Z" },
];

const provenanceResponse = {
  model_id: "m-1",
  tenant: "t1",
  provider: "acme",
  name: "atlas",
  version: "1.0",
  versions: [{ id: "v-1", version: "1.0" }],
  provenance: {},
  latest_provenance: {},
  training_metadata: { dataset: "docs-v3" },
  found: true,
};

const decisionsResponse = {
  tenant: "t1",
  count: 1,
  decisions: [{ id: "d-1", name: "pii-guard", type: "guardrail", effect: "DENY", priority: 10, status: "ACTIVE", version: "2" }],
  resource: null,
};

const systemCardsResponse = [
  { id: "sc-1", tenant: "t1", system: "support-copilot", purpose: "support", inputs: {}, outputs: {}, models: ["atlas"], tools: ["search"], permissions: ["read"], human_oversight: "required", failure_modes: ["hallucination"], evaluation: {}, deployment_scope: "production", created_at: null },
];

function installApiMock(overrides: Record<string, unknown> = {}) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions: [], user: { id: "u1", email: "u@c.io", username: "u" } }),
    mlModels: vi.fn().mockResolvedValue(modelsResponse),
    mlModel: vi.fn().mockResolvedValue(modelDetail),
    mlModelVersions: vi.fn().mockResolvedValue(versionsResponse),
    mlProviders: vi.fn().mockResolvedValue(providersResponse),
    mlProvider: vi.fn().mockResolvedValue(providersResponse[0]),
    mlPrompts: vi.fn().mockResolvedValue(promptsResponse),
    mlPrompt: vi.fn().mockResolvedValue(promptDetail),
    mlEvalRun: vi.fn().mockResolvedValue(evalRun),
    mlEvalCompare: vi.fn().mockResolvedValue(compareResponse),
    mlGuardrails: vi.fn().mockResolvedValue(guardrailsResponse),
    mlPolicyDecisions: vi.fn().mockResolvedValue(decisionsResponse),
    mlRisks: vi.fn().mockResolvedValue(risksResponse),
    mlModelCards: vi.fn().mockResolvedValue(cardsResponse),
    mlSystemCards: vi.fn().mockResolvedValue(systemCardsResponse),
    mlMonitoring: vi.fn().mockResolvedValue(snapshotsResponse),
    mlProvenance: vi.fn().mockResolvedValue(provenanceResponse),
  };
  Object.assign(api, defaults, overrides);
}

describe("MLPlatformWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge with manual refresh", async () => {
    render(<MLPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Refresh" })).toBeTruthy();
  });

  it("renders backend-backed overview counts without totals", async () => {
    render(<MLPlatformWorkspace />);
    expect(await screen.findByText("Models listed")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("Listed count only — the backend reports no totals.")).toBeTruthy();
  });

  it("renders the registry and opens model detail with versions", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View model atlas" }));
    await waitFor(() => {
      expect(apiModule.api.mlModel).toHaveBeenCalledWith("test-token", "m-1");
    });
    expect(await screen.findByText("ml-team")).toBeTruthy();
    expect(screen.getAllByText("v1.0").length).toBeGreaterThan(0);
    expect(screen.getByText("Immutable versions")).toBeTruthy();
  });

  it("refetches the registry with the chosen status filter", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "ACTIVE" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Apply" })[0]);
    await waitFor(() => {
      expect(apiModule.api.mlModels).toHaveBeenCalledWith("test-token", expect.objectContaining({ status: "ACTIVE" }));
    });
  });

  it("renders prompt metadata without ever rendering prompt content", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Prompts" }));
    expect(await screen.findByText("Summarize")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View prompt summarize" }));
    await waitFor(() => {
      expect(apiModule.api.mlPrompt).toHaveBeenCalledWith("test-token", "summarize");
    });
    expect(await screen.findByText("Versions (content withheld)")).toBeTruthy();
    expect(screen.queryByText(/SYSTEM PROMPT SENTINEL/i)).toBeNull();
  });

  it("looks up an evaluation run and compares two runs verbatim", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Evaluations" }));
    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await waitFor(() => {
      expect(apiModule.api.mlEvalRun).toHaveBeenCalledWith("test-token", "run-1");
    });
    expect(await screen.findByText("metric accuracy")).toBeTruthy();
    expect(screen.getByText("0.91")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Candidate run ID"), { target: { value: "run-1" } });
    fireEvent.change(screen.getByLabelText("Baseline run ID"), { target: { value: "run-0" } });
    fireEvent.click(screen.getByRole("button", { name: "Compare" }));
    await waitFor(() => {
      expect(apiModule.api.mlEvalCompare).toHaveBeenCalledWith("test-token", "run-1", "run-0");
    });
    expect(await screen.findByText("false")).toBeTruthy();
  });

  it("renders the risk score only with the verbatim caveat", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Risks" }));
    expect(await screen.findByText("bias-drift")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View risk bias-drift" }));
    expect(await screen.findByText("82")).toBeTruthy();
    expect(screen.getByText("governance heuristic — not a legal conclusion")).toBeTruthy();
    expect(screen.queryByText(/compliant|non-compliant|^safe$|illegal/i)).toBeNull();
  });

  it("renders monitoring snapshots verbatim with no health scores", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View model atlas" }));
    fireEvent.click(getByRole("tab", { name: "Monitoring" }));
    expect(await screen.findByText("120")).toBeTruthy();
    expect(screen.queryByText(/health score|availability %|uptime/i)).toBeNull();
  });

  it("marks deployments as not exposed without fabricating state", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Deployments" }));
    expect(await screen.findByText("NOT EXPOSED BY API")).toBeTruthy();
    expect(screen.getByText(/process memory/)).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("renders policy decisions and system cards on demand", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Governance" }));
    fireEvent.click(await screen.findByRole("button", { name: "Load" }));
    await waitFor(() => {
      expect(apiModule.api.mlPolicyDecisions).toHaveBeenCalled();
    });
    expect(await screen.findByText("pii-guard")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("System"), { target: { value: "support-copilot" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Look up" })[1]);
    await waitFor(() => {
      expect(apiModule.api.mlSystemCards).toHaveBeenCalledWith("test-token", "support-copilot");
    });
    expect(await screen.findByText("support-copilot")).toBeTruthy();
  });

  it("builds the lifecycle timeline from returned records only", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View model atlas" }));
    await waitFor(() => {
      expect(apiModule.api.mlModelVersions).toHaveBeenCalled();
    });
    fireEvent.click(getByRole("tab", { name: "Evaluations" }));
    fireEvent.change(screen.getByLabelText("Run ID"), { target: { value: "run-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await waitFor(() => {
      expect(apiModule.api.mlEvalRun).toHaveBeenCalled();
    });
    fireEvent.click(getByRole("tab", { name: "Timeline" }));
    expect(await screen.findByText("MODEL REGISTERED")).toBeTruthy();
    expect(screen.getByText("VERSION CREATED")).toBeTruthy();
    expect(screen.getByText("EVALUATION RUN RECORDED")).toBeTruthy();
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      mlModels: vi.fn().mockResolvedValue([]),
      mlRisks: vi.fn().mockResolvedValue([]),
    });
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("No models")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Risks" }));
    expect(await screen.findByText("No risks")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      mlModels: vi.fn().mockRejectedValue(new ApiError("server", 500, "ml plane down")),
    });
    render(<MLPlatformWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.mlModels).toHaveBeenCalled();
    });
    expect(await screen.findAllByText("Unavailable")).not.toHaveLength(0);
    expect(screen.getByText("ml plane down")).toBeTruthy();
  });

  it("refetches under the new scope on tenant switch without leaking state", async () => {
    render(<MLPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.mlModels as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.mlModels as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("offers the AI handoff as a plain link with no payload", async () => {
    render(<MLPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const link = screen.getByRole("link", { name: "Ask AI about models" });
    expect(link.getAttribute("href")).toBe("/ai");
  });

  it("renders no secrets anywhere in the workspace", async () => {
    render(<MLPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/secret/i)).toBeNull();
    expect(screen.queryByText(/credential/i)).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
    expect(screen.queryByText(/api[_-]?key/i)).toBeNull();
  });
});

describe("MLPlatformWorkspace (C2 operations)", () => {
  const C2_PERMS = ["aiml.model.create", "aiml.model.approve", "aiml.model.block", "aiml.model.update", "aiml.model.create_version", "aiml.deployment.create", "aiml.deployment.rollback", "aiml.gateway.invoke", "aiml.risk.assess", "aiml.approval.decide", "aiml.evaluation.create", "aiml.guardrail.create", "aiml.monitoring.create", "aiml.policy.create", "aiml.provider.create", "aiml.prompt.create", "aiml.card.create", "aiml.approval.create"];

  beforeEach(() => {
    installApiMock({});
    // Upgrade whoami in place so the initial loadAll (triggered by mount)
    // already sees the richer permission set — avoids a mount→whoami race
    // where the first render's loadAll still thinks we're unpermissioned.
    (apiModule.api.whoami as ReturnType<typeof vi.fn>).mockResolvedValue({ permissions: C2_PERMS, user: { id: "u1", email: "u@c.io", username: "u" } });
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    Object.assign(api, {
      mlModelCreate: vi.fn().mockResolvedValue({ id: "m-9", name: "herald", status: "DRAFT" }),
      mlModelApprove: vi.fn().mockResolvedValue({ id: "m-1", status: "APPROVED" }),
      mlDeploymentCreate: vi.fn().mockResolvedValue({ id: "dep-1", status: "deployed", environment: "production" }),
      mlDeploymentRollback: vi.fn().mockResolvedValue({ id: "dep-1", status: "rolled_back" }),
      mlGatewayInvoke: vi.fn().mockResolvedValue({ model_id: "m-1", model_name: "atlas", provider: "acme", output: "mocked answer", provider_call: { mocked: true } }),
      mlGatewayRoute: vi.fn().mockResolvedValue({ decision: "ALLOW", reason: "selected", model_name: "atlas" }),
      mlMonitoringDrift: vi.fn().mockResolvedValue({ drift_detected: false, sufficient_data: true, sample_count: 40 }),
      mlRiskAssess: vi.fn().mockResolvedValue({ id: "r-1", assessed_score: 74, note: "score is a governance heuristic — not a legal conclusion" }),
      mlApprovalDecide: vi.fn().mockResolvedValue({ id: "ap-1", status: "decided" }),
      mlEvalRunCreate: vi.fn().mockResolvedValue({ id: "run-9", status: "PENDING" }),
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("registers a model then refetches authoritatively", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    fireEvent.click(await screen.findByRole("button", { name: "New model" }));
    expect(await screen.findByText("Register model")).toBeTruthy();
    const dialog = screen.getByRole("dialog");
    const { within: withinDialog } = await import("@testing-library/react");
    fireEvent.change(withinDialog(dialog).getByLabelText("Provider"), { target: { value: "acme" } });
    fireEvent.change(withinDialog(dialog).getByLabelText("Name"), { target: { value: "herald" } });
    fireEvent.change(withinDialog(dialog).getByLabelText("Version"), { target: { value: "1.0" } });
    fireEvent.click(withinDialog(dialog).getByRole("button", { name: "Register" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await waitFor(() => {
      expect(api.mlModelCreate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ provider: "acme", name: "herald", version: "1.0" }),
      );
    });
    await waitFor(() => {
      expect((api.mlModels as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("hides model mutations without the exact aiml permission", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    (api.whoami as ReturnType<typeof vi.fn>).mockResolvedValue({ permissions: [], user: { id: "u1" } });
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "New model" })).toBeNull();
    fireEvent.click(getByRole("tab", { name: "Deployments" }));
    expect(await screen.findByText("NOT EXPOSED BY API")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /deploy selected model/i })).toBeNull();
  });

  it("approves a model through confirmation and refetches", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View model atlas" }));
    const approveBtn = await screen.findByRole("button", { name: "Approve model" });
    fireEvent.click(approveBtn);
    expect(await screen.findByText("Approve model?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.mlModelApprove).toHaveBeenCalledWith("test-token", "m-1");
    });
  });

  it("deploys with the returned ID and rolls back with 409 honesty", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    (api.mlDeploymentRollback as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("unknown", 409, "Deployment already rolled back"),
    );
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Registry" }));
    expect(await screen.findByText("atlas")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View model atlas" }));
    fireEvent.click(getByRole("tab", { name: "Deployments" }));
    fireEvent.click(await screen.findByRole("button", { name: /deploy selected model/i }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(api.mlDeploymentCreate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ model_id: "m-1", environment: "production" }),
      );
    });
    expect(await screen.findByText("dep-1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Roll back" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(api.mlDeploymentRollback).toHaveBeenCalledWith("test-token", "dep-1");
    });
  });

  it("invokes the gateway only after confirmation with mocked labeling", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Gateway" }));
    fireEvent.click(await screen.findByRole("button", { name: "Route" }));
    await waitFor(() => {
      expect(apiModule.api.mlGatewayRoute).toHaveBeenCalled();
    });
    fireEvent.click(await screen.findByRole("button", { name: "Invoke model" }));
    expect(await screen.findByText("Invoke model?")).toBeTruthy();
    expect(screen.getByText(/MOCKED \/ NON-PRODUCTION/)).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.mlGatewayInvoke).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "m-1" } });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "summarize this" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(api.mlGatewayInvoke).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ model_id: "m-1", prompt: "summarize this" }),
      );
    });
    expect(await screen.findByText("AI GATEWAY RESULT")).toBeTruthy();
    expect(screen.getAllByText("MOCKED / NON-PRODUCTION").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("mocked answer")).toBeTruthy();
  });

  it("states gateway timeout explicitly without claiming cancellation", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    (api.mlGatewayInvoke as ReturnType<typeof vi.fn>).mockRejectedValueOnce(
      new ApiError("timeout", 0, "Request timed out after 180000ms"),
    );
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Gateway" }));
    fireEvent.click(await screen.findByRole("button", { name: "Invoke model" }));
    fireEvent.change(screen.getByLabelText("Model ID"), { target: { value: "m-1" } });
    fireEvent.change(screen.getByLabelText("Prompt"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText(/REQUEST TIMED OUT/)).toBeTruthy();
    expect(screen.getByText(/may still be processing/)).toBeTruthy();
  });

  it("assesses a risk and keeps the caveat attached to the score", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Risks" }));
    expect(await screen.findByText("bias-drift")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View risk bias-drift" }));
    fireEvent.click(await screen.findByRole("button", { name: "Assess risk" }));
    expect(await screen.findByText("Assess risk?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.mlRiskAssess).toHaveBeenCalled();
    });
    expect(await screen.findByText("74")).toBeTruthy();
    expect(screen.getAllByText(/governance heuristic — not a legal conclusion/).length).toBeGreaterThanOrEqual(2);
  });

  it("decides an approval with the backend decision vocabulary", async () => {
    const { getByRole } = render(<MLPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Governance" }));
    fireEvent.change(screen.getByLabelText("Approval ID"), { target: { value: "ap-1" } });
    fireEvent.change(screen.getByLabelText("Approver"), { target: { value: "ops@acme.test" } });
    fireEvent.click(await screen.findByRole("button", { name: "Decide" }));
    await waitFor(() => {
      expect(apiModule.api.mlApprovalDecide).toHaveBeenCalledWith("test-token", "ap-1", {
        approver: "ops@acme.test",
        decision: "approved",
      });
    });
  });
});
