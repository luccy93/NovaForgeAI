import { render, screen, waitFor, cleanup, fireEvent, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GovernanceWorkspace } from "@/components/governance/GovernanceWorkspace";
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

const posture = {
  snapshot_id: "snap-1",
  total_policies: 6,
  active_policies: 4,
  violations_24h: 2,
  open_exceptions: 1,
  verified_controls: 9,
  failing_controls: 3,
  computed_at: "2026-09-09T09:00:00Z",
};

const postureHistory = {
  items: [
    {
      id: "snap-1",
      scope_type: "tenant",
      scope_value: "",
      domain: "general",
      total_policies: 6,
      active_policies: 4,
      violations_24h: 2,
      open_exceptions: 1,
      verified_controls: 9,
      failing_controls: 3,
      computed_at: "2026-09-09T09:00:00Z",
      metadata: {},
    },
  ],
  total: 1,
};

const evidenceCoverage = { total: 7, valid: 6, expired: 1 };

const trendsResponse = {
  items: [
    { computed_at: "2026-09-09T09:00:00Z", domain: "general", active_policies: 4, violations_24h: 2, open_exceptions: 1, verified_controls: 9, failing_controls: 3 },
    { computed_at: "2026-09-08T09:00:00Z", domain: "general", active_policies: 3, violations_24h: 1, open_exceptions: 1, verified_controls: 8, failing_controls: 4 },
  ],
  total: 2,
};

const policiesResponse = {
  items: [
    { id: "p1", tenant: "t1", name: "Production access", domain: "identity", description: "", owner: "ops", status: "ACTIVE", active_version_id: "v1" },
    { id: "p2", tenant: "t1", name: "Data egress", domain: "data", description: "", owner: "sre", status: "DRAFT", active_version_id: null },
  ],
  total: 2,
};

const versionsResponse = {
  items: [
    {
      id: "v1",
      tenant: "t1",
      policy_id: "p1",
      version: 2,
      status: "ACTIVE",
      effective_from: "2026-09-01T00:00:00Z",
      effective_until: null,
      rules: [{ name: "deny-egress", effect: "deny", condition: {}, priority: 1 }],
      default_effect: "deny",
      checksum: "abc123def456",
      reason: "tighten egress",
      created_by: "ops",
    },
  ],
  total: 1,
};

const bindingsResponse = {
  items: [
    { id: "b1", tenant: "t1", policy_id: "p1", version_id: "v1", scope_type: "tenant", scope_value: "acme", mandatory: true, enabled: true },
  ],
  total: 1,
};

const decisionsResponse = {
  items: [
    { id: "d1", evaluation_id: "ev1", tenant: "t1", policy_id: "p1", version_id: "v1", binding_id: "b1", rule_index: 2, decision: "DENY", scope_type: "tenant", scope_value: "acme", priority: 1, reason: "rule 3 matched", obligations: [], approval_id: "", actor: "dev" },
    { id: "d2", evaluation_id: "ev2", tenant: "t1", policy_id: "p1", version_id: "v1", binding_id: "b1", rule_index: 0, decision: "ALLOW", scope_type: "tenant", scope_value: "acme", priority: 1, reason: "allowed", obligations: [], approval_id: "", actor: "ci" },
  ],
  total: 2,
};

const explainResponse = {
  id: "d1",
  tenant: "t1",
  explanation: {
    decision: "DENY",
    reason: "rule 3 matched",
    scope: { scope_type: "tenant", scope_value: "acme" },
    priority: 1,
    obligations: [],
    approval_id: "",
    actor: "dev",
    policy: { id: "p1", name: "Production access", domain: "identity", status: "ACTIVE" },
    version: { id: "v1", version: 2, status: "ACTIVE", checksum: "abc123def456" },
    rule: { index: 2, name: "deny-egress", effect: "deny", priority: 1, obligations: [] },
    binding: { id: "b1", scope_type: "tenant", scope_value: "acme", mandatory: true },
    evaluation_id: "ev1",
    why: "denied: rule 3 matched",
  },
};

const exceptionsResponse = {
  items: [
    { id: "e1", tenant: "t1", policy_id: "p1", scope_type: "tenant", scope_value: "acme", justification: "emergency access", requester: "alice", approver: "", start_at: null, end_at: null, max_duration_hours: 24, high_risk: true, status: "PENDING" },
    { id: "e2", tenant: "t1", policy_id: "p2", scope_type: "workspace", scope_value: "sandbox", justification: "vendor validation", requester: "bob", approver: "ops", start_at: null, end_at: null, max_duration_hours: 24, high_risk: false, status: "APPROVED" },
  ],
  total: 2,
};

const evidenceResponse = {
  items: [
    { id: "evd-1", tenant: "t1", control_key: "iam-1", source_system: "aws-config", source_ref: "rule-42", source_version: "1.0", collected_at: "2026-09-01T10:00:00Z", valid_until: "2026-12-01T10:00:00Z", integrity_hash: "h1", result: "PASS", expired: false },
    { id: "evd-2", tenant: "t1", control_key: "enc-2", source_system: "aws-config", source_ref: "rule-7", source_version: "", collected_at: "2026-01-01T10:00:00Z", valid_until: "2026-02-01T10:00:00Z", integrity_hash: "h2", result: "PASS", expired: true },
  ],
  total: 2,
};

const driftResponse = {
  items: [
    { id: "f1", finding_type: "unbound_scope", severity: "MEDIUM", resource_type: "scope", resource_id: "tenant:*", description: "Evaluations without an enabled binding", status: "OPEN" },
  ],
  total: 1,
};

const reportsResponse = {
  items: [
    {
      id: "r1",
      tenant: "t1",
      report_type: "posture",
      scope_type: "tenant",
      scope_value: "",
      period_start: "2026-08-10T00:00:00Z",
      period_end: "2026-09-09T00:00:00Z",
      summary: { violations: 2, open_exceptions: 1, open_drift: 1, top_risks: [{ area: "drift:unbound_scope", severity: "MEDIUM", resource: "tenant:*" }] },
      sections: [{ name: "posture", items: [] }],
    },
  ],
  total: 1,
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ email: "ops@acme.test", permissions }),
    governancePosture: vi.fn().mockResolvedValue(posture),
    governancePostureHistory: vi.fn().mockResolvedValue(postureHistory),
    governanceEvidenceCoverage: vi.fn().mockResolvedValue(evidenceCoverage),
    governancePolicies: vi.fn().mockResolvedValue(policiesResponse),
    governancePolicyVersions: vi.fn().mockResolvedValue(versionsResponse),
    governanceBindings: vi.fn().mockResolvedValue(bindingsResponse),
    governanceDecisions: vi.fn().mockResolvedValue(decisionsResponse),
    governanceExplainDecision: vi.fn().mockResolvedValue(explainResponse),
    governanceExceptions: vi.fn().mockResolvedValue(exceptionsResponse),
    governanceEvidence: vi.fn().mockResolvedValue(evidenceResponse),
    governanceDrift: vi.fn().mockResolvedValue(driftResponse),
    governanceTrends: vi.fn().mockResolvedValue(trendsResponse),
    governanceReports: vi.fn().mockResolvedValue(reportsResponse),
    governanceGenerateReport: vi.fn().mockResolvedValue(reportsResponse.items[0]),
    governanceCreatePolicy: vi.fn().mockResolvedValue(policiesResponse.items[0]),
    governanceCreateVersion: vi.fn().mockResolvedValue(versionsResponse.items[0]),
    governanceVersionStatus: vi.fn().mockResolvedValue(versionsResponse.items[0]),
    governanceCreateBinding: vi.fn().mockResolvedValue(bindingsResponse.items[0]),
    governanceDeleteBinding: vi.fn().mockResolvedValue({ id: "b1", deleted: true }),
    governanceApproveException: vi.fn().mockResolvedValue({ id: "e1", status: "APPROVED" }),
    governanceDenyException: vi.fn().mockResolvedValue({ id: "e1", status: "DENIED" }),
    governanceRevokeException: vi.fn().mockResolvedValue({ id: "e2", status: "REVOKED" }),
    governanceResolveDrift: vi.fn().mockResolvedValue({ id: "f1", status: "RESOLVED" }),
    governanceDetectDrift: vi.fn().mockResolvedValue({ findings: [], total: 0 }),
    governanceRegisterEvidence: vi.fn().mockResolvedValue({ id: "evd-3", control_key: "iam-1", source_system: "aws-config", source_ref: "rule-42", source_version: "1.0", collected_at: "2026-09-09T10:00:00Z", valid_until: "2026-12-09T10:00:00Z", integrity_hash: "h3", result: "PASS", expired: false }),
  };
  Object.assign(api, defaults, overrides);
}

describe("GovernanceWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge, refresh control and permission notices", async () => {
    installApiMock({}, []);
    render(<GovernanceWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getAllByText("Refresh").length).toBeGreaterThan(0);
    expect(screen.getByText("Read-only view · no governance read permissions")).toBeTruthy();
    expect(screen.getByText("Admin actions hidden · no settings:admin")).toBeTruthy();
  });

  it("renders policy posture values from the posture payload", async () => {
    render(<GovernanceWorkspace />);
    expect(await screen.findByText("Policy posture")).toBeTruthy();
    expect(screen.getByText("Total policies")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getByText("Active policies")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(screen.getByText("Failing controls")).toBeTruthy();
    expect(screen.getByText("Violations 24h")).toBeTruthy();
  });

  it("renders evidence coverage counts from the backend payload", async () => {
    render(<GovernanceWorkspace />);
    expect(await screen.findByText("Evidence coverage")).toBeTruthy();
    expect(screen.getByText("Total evidence")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("Valid")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(0);
  });

  it("renders policies with versions and the create action for admins", async () => {
    installApiMock({}, ["organization:read", "settings:admin"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Policies" }));
    expect(await screen.findByText("Production access")).toBeTruthy();
    expect(screen.getByText("Data egress")).toBeTruthy();
    expect(screen.getByText("New policy")).toBeTruthy();
    fireEvent.click(screen.getByText("Production access"));
    await waitFor(() => {
      expect(apiModule.api.governancePolicyVersions).toHaveBeenCalledWith("test-token", "p1");
    });
    expect(await screen.findByText("v2")).toBeTruthy();
    expect(screen.getByText("tighten egress")).toBeTruthy();
  });

  it("hides policy and binding mutations without settings:admin", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Policies" }));
    expect(await screen.findByText("Production access")).toBeTruthy();
    expect(screen.queryByText("New policy")).toBeNull();
    fireEvent.click(getByRole("tab", { name: "Bindings" }));
    expect(await screen.findByText("tenant:acme")).toBeTruthy();
    expect(screen.queryByText("New binding")).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete binding" })).toBeNull();
  });

  it("renders bindings with scope and mandatory badges", async () => {
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Bindings" }));
    expect(await screen.findByText("tenant:acme")).toBeTruthy();
    expect(screen.getAllByText("Mandatory").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Enabled").length).toBeGreaterThan(0);
  });

  it("renders decisions feed and refetches with the chosen decision filter", async () => {
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Decisions" }));
    expect(await screen.findByText("Recent decisions")).toBeTruthy();
    expect(screen.getAllByText("DENY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ALLOW").length).toBeGreaterThan(0);
    fireEvent.change(await screen.findByLabelText("Decision"), { target: { value: "ALLOW" } });
    await waitFor(() => {
      expect(apiModule.api.governanceDecisions).toHaveBeenCalledWith("test-token", { decision: "ALLOW", limit: 50 });
    });
  });

  it("shows the backend-composed explanation for a selected decision", async () => {
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Decisions" }));
    expect(await screen.findByText("Recent decisions")).toBeTruthy();
    fireEvent.click(screen.getAllByText("tenant:acme")[0]);
    await waitFor(() => {
      expect(apiModule.api.governanceExplainDecision).toHaveBeenCalledWith("test-token", "d1");
    });
    expect(await screen.findByText("denied: rule 3 matched")).toBeTruthy();
  });

  it("renders policy exceptions and hides mutation controls without settings:admin", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Exceptions" }));
    expect(await screen.findByText("emergency access")).toBeTruthy();
    expect(screen.getAllByText("PENDING").length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("button", { name: "Approve exception" }).length).toBe(0);
    expect(screen.queryAllByRole("button", { name: "Deny exception" }).length).toBe(0);
  });

  it("approves a pending exception through the confirmation modal", async () => {
    installApiMock({}, ["settings:admin"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Exceptions" }));
    const approveButtons = await screen.findAllByRole("button", { name: "Approve exception" });
    expect(approveButtons.length).toBeGreaterThan(0);
    fireEvent.click(approveButtons[0]);
    expect(await screen.findByText("Approve exception?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceApproveException).toHaveBeenCalledWith("test-token", "e1", {
        approver: "ops@acme.test",
        approval_type: "jit",
      });
    });
  });

  it("registers evidence through the form modal and passes the draft", async () => {
    installApiMock({}, ["settings:admin"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Evidence" }));
    fireEvent.click(await screen.findByRole("button", { name: "Register evidence" }));
    expect(await screen.findByText("Register evidence")).toBeTruthy();
    const dialog = screen.getByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Control key"), { target: { value: "iam-1" } });
    fireEvent.change(within(dialog).getByLabelText("Source system"), { target: { value: "aws-config" } });
    fireEvent.change(within(dialog).getByLabelText("Source reference"), { target: { value: "rule-42" } });
    fireEvent.change(within(dialog).getByLabelText("Source version"), { target: { value: "1.0" } });
    fireEvent.change(within(dialog).getByLabelText("Validity days"), { target: { value: "90" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Register" }));
    await waitFor(() => {
      expect(apiModule.api.governanceRegisterEvidence).toHaveBeenCalledWith("test-token", {
        control_key: "iam-1",
        source_system: "aws-config",
        source_ref: "rule-42",
        source_version: "1.0",
        result: "PASS",
        validity_days: 90,
      });
    });
  });

  it("renders drift findings and resolves an open finding", async () => {
    installApiMock({}, ["settings:admin"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Drift" }));
    expect(await screen.findByText("Evaluations without an enabled binding")).toBeTruthy();
    expect(screen.getAllByText("OPEN").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Resolve drift" }));
    expect(await screen.findByText("Resolve drift finding?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceResolveDrift).toHaveBeenCalledWith("test-token", "f1");
    });
  });

  it("generates a report and shows its backend-computed summary", async () => {
    installApiMock({}, ["settings:admin"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Reports" }));
    expect(await screen.findByText("posture")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText("Generate report")).toBeTruthy();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Generate" }));
    await waitFor(() => {
      expect(apiModule.api.governanceGenerateReport).toHaveBeenCalled();
    });
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      governanceDecisions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      governanceTrends: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      governancePostureHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    });
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Decisions" }));
    expect(await screen.findByText("No decisions")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Overview" }));
    expect(screen.getByText("No trend points")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      governancePolicies: vi.fn().mockRejectedValue(new ApiError("server", 500, "governance plane down")),
    });
    const { getByRole } = render(<GovernanceWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.governancePolicies).toHaveBeenCalled();
    });
    fireEvent.click(getByRole("tab", { name: "Policies" }));
    expect((await screen.findAllByText("Unavailable")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("governance plane down").length).toBeGreaterThan(0);
  });

  it("refetches under the new scope on tenant switch", async () => {
    render(<GovernanceWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const callsBefore = (apiModule.api.governancePolicies as ReturnType<typeof vi.fn>).mock.calls.length;
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((apiModule.api.governancePolicies as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("renders no secrets anywhere in the workspace", async () => {
    installApiMock({}, ["organization:read", "settings:admin"]);
    render(<GovernanceWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/secret/i)).toBeNull();
    expect(screen.queryByText(/token/i)).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
  });
});

describe("GovernanceWorkspace (C2 intelligence)", () => {
  beforeEach(() => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    Object.assign(api, {
      governAi: vi.fn().mockResolvedValue({
        decision: "ALLOW",
        reason: "allowed by default effect",
        allowed: true,
        layer: "governance+finops",
        policy_id: "p1",
        finops_gate: "ALLOW",
      }),
      governData: vi.fn().mockResolvedValue({ decision: "ALLOW", reason: "ok", allowed: true, layer: "governance" }),
      governanceEvaluate: vi.fn().mockResolvedValue({
        decision: "DENY",
        reason: "no allow rule matched",
        policy_id: null,
        version_id: null,
        binding_id: null,
        rule_index: null,
        priority: 0,
        obligations: [],
        exception_id: null,
        scope_type: "tenant",
        scope_value: "",
        effective_at: "2026-09-10T00:00:00Z",
        latency_ms: 3,
        allowed: false,
      }),
      governanceSimulate: vi.fn().mockResolvedValue({
        items: [
          {
            decision: "ALLOW",
            reason: "allowed",
            policy_id: "p1",
            version_id: "v1",
            binding_id: "b1",
            rule_index: 0,
            priority: 1,
            obligations: [],
            scope_type: "tenant",
            scope_value: "",
            simulated_at: "2026-09-10T00:00:00Z",
            side_effects: false,
          },
        ],
        total: 1,
        summary: { ALLOW: 1 },
      }),
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("runs an AI domain check and renders the backend verdict verbatim", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "AI Governance" }));
    expect(await screen.findByText("Domain check")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "gpt-x" } });
    fireEvent.click(screen.getByRole("button", { name: "Run domain check" }));
    await waitFor(() => {
      expect(apiModule.api.governAi).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ model: "gpt-x", operation: "ai.invoke", classification: "INTERNAL" }),
      );
    });
    expect(await screen.findByText("governance+finops")).toBeTruthy();
    expect(screen.getByText("FinOps gate")).toBeTruthy();
  });

  it("evaluates with enforcement off and labels the dry run honestly", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Advanced" }));
    fireEvent.change(screen.getByLabelText("Operation"), { target: { value: "data.export" } });
    fireEvent.click(screen.getByRole("button", { name: "Evaluate" }));
    await waitFor(() => {
      expect(apiModule.api.governanceEvaluate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ operation: "data.export", enforce: false }),
      );
    });
    expect(await screen.findByText("no allow rule matched")).toBeTruthy();
  });

  it("simulates a batch and renders the backend summary counts", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Advanced" }));
    fireEvent.click(screen.getByRole("button", { name: "Batch" }));
    fireEvent.change(screen.getByLabelText("Requests (JSON array)"), {
      target: { value: '[{"scope_type": "tenant", "operation": "data.export"}]' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
    await waitFor(() => {
      expect(apiModule.api.governanceSimulate).toHaveBeenCalledWith("test-token", {
        requests: [{ scope_type: "tenant", operation: "data.export" }],
      });
    });
    expect(await screen.findByText("1 simulated · ALLOW: 1")).toBeTruthy();
  });

  it("simulates a single request with no side effects", async () => {
    installApiMock(
      {
        governanceSimulate: vi.fn().mockResolvedValue({
          decision: "ALLOW",
          reason: "allowed",
          policy_id: "p1",
          version_id: "v1",
          binding_id: "b1",
          rule_index: 0,
          priority: 1,
          obligations: [],
          scope_type: "tenant",
          scope_value: "",
          simulated_at: "2026-09-10T00:00:00Z",
          side_effects: false,
        }),
      },
      ["organization:read"],
    );
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Advanced" }));
    fireEvent.change(screen.getByLabelText("Simulated operation"), { target: { value: "data.export" } });
    fireEvent.click(screen.getByRole("button", { name: "Simulate" }));
    await waitFor(() => {
      expect(apiModule.api.governanceSimulate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ operation: "data.export", scope_type: "tenant" }),
      );
    });
    expect(await screen.findByText("side_effects: off")).toBeTruthy();
  });

  it("surfaces the rate-limit state when evaluation is throttled", async () => {
    installApiMock(
      {
        governanceEvaluate: vi.fn().mockRejectedValue(new ApiError("rate_limited", 429, "rate limit exceeded")),
      },
      ["organization:read"],
    );
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Advanced" }));
    fireEvent.change(screen.getByLabelText("Operation"), { target: { value: "data.export" } });
    fireEvent.click(screen.getByRole("button", { name: "Evaluate" }));
    expect(await screen.findByText("rate limit exceeded")).toBeTruthy();
  });

  it("offers the AI handoff as a plain link with no payload", async () => {
    installApiMock({}, ["organization:read"]);
    const { getByRole } = render(<GovernanceWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Advanced" }));
    const link = await screen.findByRole("link", { name: "Ask AI about governance" });
    expect(link.getAttribute("href")).toBe("/ai");
  });
});
