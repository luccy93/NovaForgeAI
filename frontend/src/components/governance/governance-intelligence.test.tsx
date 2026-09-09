import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { GovernanceIntelligence } from "@/components/governance/GovernanceIntelligence";
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

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []) {
  apiModule.api.whoami = vi.fn().mockResolvedValue({ email: "ops@acme.test", permissions });
  apiModule.api.governancePosture = vi.fn().mockResolvedValue(posture);
  apiModule.api.governanceEvidenceCoverage = vi.fn().mockResolvedValue(evidenceCoverage);
  apiModule.api.governancePolicies = vi.fn().mockResolvedValue(policiesResponse);
  apiModule.api.governanceBindings = vi.fn().mockResolvedValue(bindingsResponse);
  apiModule.api.governanceDecisions = vi.fn().mockResolvedValue(decisionsResponse);
  apiModule.api.governanceExceptions = vi.fn().mockResolvedValue(exceptionsResponse);
  apiModule.api.governanceEvidence = vi.fn().mockResolvedValue(evidenceResponse);
  apiModule.api.governanceDrift = vi.fn().mockResolvedValue(driftResponse);
  apiModule.api.governanceTrends = vi.fn().mockResolvedValue(trendsResponse);
  apiModule.api.governanceApproveException = vi.fn().mockResolvedValue({ id: "e1", status: "APPROVED" });
  apiModule.api.governanceDenyException = vi.fn().mockResolvedValue({ id: "e1", status: "DENIED" });
  apiModule.api.governanceRevokeException = vi.fn().mockResolvedValue({ id: "e2", status: "REVOKED" });
  apiModule.api.governanceResolveDrift = vi.fn().mockResolvedValue({ id: "f1", status: "RESOLVED" });
  apiModule.api.governanceDetectDrift = vi.fn().mockResolvedValue({ findings: [], total: 0 });
  apiModule.api.governanceRegisterEvidence = vi.fn().mockResolvedValue({ id: "evd-3", control_key: "iam-1", source_system: "aws-config", source_ref: "rule-42", source_version: "1.0", collected_at: "2026-09-09T10:00:00Z", valid_until: "2026-12-09T10:00:00Z", integrity_hash: "h3", result: "PASS", expired: false });
  Object.assign(apiModule.api, overrides);
}

beforeEach(() => {
  installApiMock();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("GovernanceIntelligence", () => {
  it("renders the honest realtime badge, refresh control and permission notices", async () => {
    installApiMock({}, []);
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getAllByText("Refresh").length).toBeGreaterThan(0);
    expect(screen.getByText("Read-only view · no governance read permissions")).toBeTruthy();
    expect(screen.getByText("Admin actions hidden · no settings:admin")).toBeTruthy();
  });

  it("renders policy posture values from the posture payload", async () => {
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Policy posture")).toBeTruthy();
    expect(screen.getByText("Total policies")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getByText("Active policies")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(screen.getByText("Failing controls")).toBeTruthy();
    expect(screen.getByText("Violations 24h")).toBeTruthy();
  });

  it("renders evidence coverage counts from the backend payload", async () => {
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Evidence coverage")).toBeTruthy();
    expect(screen.getByText("Total evidence")).toBeTruthy();
    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("Valid")).toBeTruthy();
    expect(screen.getAllByText("6").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Expired").length).toBeGreaterThan(0);
  });

  it("renders policies and bindings from the backend payload", async () => {
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Production access")).toBeTruthy();
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThan(0);
    expect(screen.getByText("Data egress")).toBeTruthy();
    expect(screen.getAllByText("DRAFT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("tenant:acme").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Mandatory").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Enabled").length).toBeGreaterThan(0);
  });

  it("renders decisions feed and refetches with the chosen decision filter", async () => {
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Recent decisions")).toBeTruthy();
    expect(screen.getAllByText("DENY").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ALLOW").length).toBeGreaterThan(0);
    fireEvent.change(await screen.findByLabelText("Decision"), { target: { value: "ALLOW" } });
    await waitFor(() => {
      expect(apiModule.api.governanceDecisions).toHaveBeenCalledWith("test-token", { decision: "ALLOW", limit: 50 });
    });
  });

  it("renders policy exceptions and hides mutation controls without settings:admin", async () => {
    installApiMock({}, ["organization:read"]);
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("emergency access")).toBeTruthy();
    expect(screen.getAllByText("PENDING").length).toBeGreaterThan(0);
    expect(screen.queryAllByRole("button", { name: "Approve exception" }).length).toBe(0);
    expect(screen.queryAllByRole("button", { name: "Deny exception" }).length).toBe(0);
  });

  it("approves a pending exception through the confirmation modal", async () => {
    installApiMock({}, ["settings:admin"]);
    render(<GovernanceIntelligence />);
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

  it("denies a pending exception through the confirmation modal", async () => {
    installApiMock({}, ["settings:admin"]);
    render(<GovernanceIntelligence />);
    const denyButtons = await screen.findAllByRole("button", { name: "Deny exception" });
    fireEvent.click(denyButtons[0]);
    expect(await screen.findByText("Deny exception?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceDenyException).toHaveBeenCalledWith("test-token", "e1", {
        approver: "ops@acme.test",
        approval_type: "jit",
      });
    });
  });

  it("revokes an approved exception through the confirmation modal", async () => {
    installApiMock({}, ["settings:admin"]);
    render(<GovernanceIntelligence />);
    const revokeButtons = await screen.findAllByRole("button", { name: "Revoke exception" });
    expect(revokeButtons.length).toBeGreaterThan(0);
    fireEvent.click(revokeButtons[0]);
    expect(await screen.findByText("Revoke exception?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceRevokeException).toHaveBeenCalledWith("test-token", "e2");
    });
  });

  it("registers evidence through the form modal and passes the draft", async () => {
    installApiMock({}, ["settings:admin"]);
    render(<GovernanceIntelligence />);
    fireEvent.click(await screen.findByRole("button", { name: "Register evidence" }));
    expect(await screen.findByText("Register evidence")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Control key"), { target: { value: "iam-1" } });
    fireEvent.change(screen.getByLabelText("Source system"), { target: { value: "aws-config" } });
    fireEvent.change(screen.getByLabelText("Source reference"), { target: { value: "rule-42" } });
    fireEvent.change(screen.getByLabelText("Source version"), { target: { value: "1.0" } });
    fireEvent.change(screen.getByLabelText("Validity days"), { target: { value: "90" } });
    fireEvent.click(screen.getByRole("button", { name: "Register" }));
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
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("Evaluations without an enabled binding")).toBeTruthy();
    expect(screen.getAllByText("OPEN").length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Resolve drift" }));
    expect(await screen.findByText("Resolve drift finding?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceResolveDrift).toHaveBeenCalledWith("test-token", "f1");
    });
  });

  it("runs drift detection through the confirmation modal", async () => {
    installApiMock({}, ["settings:admin"]);
    render(<GovernanceIntelligence />);
    fireEvent.click(await screen.findByRole("button", { name: "Detect drift" }));
    expect(await screen.findByText("Detect configuration drift?")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.governanceDetectDrift).toHaveBeenCalledWith("test-token");
    });
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      governanceDecisions: vi.fn().mockResolvedValue({ items: [], total: 0 }),
      governanceTrends: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    });
    render(<GovernanceIntelligence />);
    expect(await screen.findByText("No decisions")).toBeTruthy();
    expect(screen.getByText("No trend points")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      governancePolicies: vi.fn().mockRejectedValue(new ApiError("server", 500, "governance plane down")),
    });
    render(<GovernanceIntelligence />);
    await waitFor(() => {
      expect(apiModule.api.governancePolicies).toHaveBeenCalled();
    });
    expect(await screen.findByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("governance plane down")).toBeTruthy();
  });
});