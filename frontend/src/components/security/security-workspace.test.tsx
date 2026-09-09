import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { SecurityWorkspace } from "@/components/security/SecurityWorkspace";
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

const dashboard = {
  tenant: "t1",
  alerts: { total: 3, by_status: { OPEN: 2, RESOLVED: 1 }, by_severity: { HIGH: 2, LOW: 1 } },
  findings: { total: 1 },
  cases: { total: 2 },
  indicators: { total: 4 },
};

const posture = {
  tenant: "t1",
  indicators: { rules_enabled: 5, rules_total: 6, alerts_open: 2, findings_open: 1, cases_open: 1, has_mfa: false, has_logging: true },
  note: "Posture indicators — not certification",
};

const coverage = {
  tenant: "t1",
  asset_coverage: { categories_covered: 5, total: 12 },
  event_coverage: 3,
  rule_coverage: 6,
  response_coverage: 6,
  gaps: [],
};

const slo = {
  tenant: "t1",
  slo_targets: { alert_processing_seconds: 60, detection_latency_seconds: 30, response_latency_seconds: 300 },
  observed: { detection_latency_avg_seconds: 2.5, alerts_measured: 1 },
};

const risk = { risk_score: 42, severity: "MEDIUM", calculated_at: "2026-09-01T10:00:00Z" };

const eventsResponse = {
  items: [
    {
      event_id: "evt-1",
      source: "cloudtrail",
      category: "AUTH",
      severity: "HIGH",
      action: "logon",
      actor: "svc-acct",
      created_at: "2026-09-01T10:00:00Z",
    },
  ],
  total: 1,
  tenant: "t1",
};

const alertsResponse = {
  items: [{ id: "a1", rule_name: "Impossible travel", severity: "HIGH", status: "OPEN", confidence: 0.9 }],
  total: 1,
};

const findingsResponse = {
  items: [{ id: "f1", finding: "S3 bucket public", resource: "bucket-x", severity: "MEDIUM", status: "OPEN" }],
};

const responsesResponse = {
  items: [{ id: "r1", action: "revoke_credentials", status: "REQUESTED", requested_by: "analyst" }],
  total: 1,
};

const ztPosture = {
  identity: { compromise_risk_high: 0 },
  access: { policy_links: 12, net_zone: "prod" },
  machine: { enrolled: 8, patched: 6 },
};

const privilegedResponse = {
  items: [{ id: "pa1", identity: "svc-acct", resource: "prod-db", status: "ACTIVE", privilege_level: "HIGH" }],
};

const accessRequestsResponse = {
  items: [{ id: "ar1", identity: "dev@corp", resource: "prod-db", action: "read", status: "PENDING", binding_hash: "hash-123" }],
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []): void {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    secOpsDashboard: vi.fn().mockResolvedValue(dashboard),
    secOpsPosture: vi.fn().mockResolvedValue(posture),
    secOpsCoverage: vi.fn().mockResolvedValue(coverage),
    secOpsSlo: vi.fn().mockResolvedValue(slo),
    secOpsRisk: vi.fn().mockResolvedValue(risk),
    secOpsEvents: vi.fn().mockResolvedValue(eventsResponse),
    secOpsAlerts: vi.fn().mockResolvedValue(alertsResponse),
    secOpsFindings: vi.fn().mockResolvedValue(findingsResponse),
    secOpsResponses: vi.fn().mockResolvedValue(responsesResponse),
    zeroTrustPosture: vi.fn().mockResolvedValue(ztPosture),
    zeroTrustPrivilegedAccess: vi.fn().mockResolvedValue(privilegedResponse),
    zeroTrustAccessRequests: vi.fn().mockResolvedValue(accessRequestsResponse),
    secOpsUpdateAlertStatus: vi.fn().mockResolvedValue({ id: "a1", status: "RESOLVED" }),
    secOpsUpdateFindingStatus: vi.fn().mockResolvedValue({ id: "f1", status: "OPEN" }),
    secOpsApproveResponse: vi.fn().mockResolvedValue({}),
    secOpsExecuteResponse: vi.fn().mockResolvedValue({}),
    secOpsVerifyResponse: vi.fn().mockResolvedValue({}),
    zeroTrustApproveAccessRequest: vi.fn().mockResolvedValue({ id: "ar1", status: "APPROVED", expires_at: null }),
  };
  Object.assign(api, defaults, overrides);
}

describe("SecurityWorkspace", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge, refresh control and read-only notice without permissions", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeTruthy();
    expect(screen.getByText("Read-only view · no secops permissions")).toBeTruthy();
  });

  it("renders security overview counts from the dashboard response", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Security overview")).toBeTruthy();
    expect(screen.getByText("Open alerts")).toBeTruthy();
    expect(screen.getAllByText("Findings").length).toBeGreaterThan(0);
    expect(screen.getByText("Cases")).toBeTruthy();
    expect(screen.getByText("Indicators")).toBeTruthy();
    expect(screen.getAllByText("HIGH").length).toBeGreaterThan(0);
    expect(apiModule.api.secOpsDashboard).toHaveBeenCalled();
  });

  it("renders risk snapshot and posture indicators verbatim", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Risk score")).toBeTruthy();
    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("Posture indicators")).toBeTruthy();
    expect(screen.getByText("rules enabled")).toBeTruthy();
    expect(screen.getAllByText("5").length).toBeGreaterThan(0);
  });

  it("renders coverage and SLO values from the backend payload", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Asset coverage")).toBeTruthy();
    expect(screen.getByText("categories covered")).toBeTruthy();
    expect(screen.getByText("Observed")).toBeTruthy();
    expect(screen.getByText("detection latency avg seconds")).toBeTruthy();
    expect(screen.getByText("alerts measured")).toBeTruthy();
  });

  it("renders zero-trust posture sections and JIT access requests", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Identity · access · machine posture")).toBeTruthy();
    expect(screen.getByText("compromise risk high")).toBeTruthy();
    expect(screen.getByText("policy links")).toBeTruthy();
    expect(screen.getByText("Privileged sessions")).toBeTruthy();
    expect(screen.getAllByText(/prod-db/).length).toBeGreaterThan(0);
    expect(screen.getAllByText("ACTIVE").length).toBeGreaterThan(0);
    expect(screen.getByText("PENDING")).toBeTruthy();
  });

  it("renders security events audit trail with filters", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Security events · audit trail")).toBeTruthy();
    expect(screen.getByText("evt-1")).toBeTruthy();
    expect(screen.getByText(/actor svc-acct/)).toBeTruthy();
    expect(screen.getByLabelText("Event category filter")).toBeTruthy();
    expect(screen.getByLabelText("Event severity filter")).toBeTruthy();
  });

  it("renders alerts and findings; read-only view hides mutation buttons", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Impossible travel")).toBeTruthy();
    expect(screen.getByText("S3 bucket public")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Update" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Approve" })).toBeNull();
  });

  it("shows alert mutation controls when secops:write is granted", async () => {
    installApiMock({}, ["secops:write"]);
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Impossible travel")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Update" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Approve" })).toBeTruthy();
  });

  it("updates an alert status through the confirmation modal", async () => {
    installApiMock({}, ["secops:write"]);
    render(<SecurityWorkspace />);
    const updateButtons = await screen.findAllByRole("button", { name: "Update" });
    fireEvent.click(updateButtons[0]);
    expect(await screen.findByText("Update alert status?")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Target status"), { target: { value: "RESOLVED" } });
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "confirmed benign" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.secOpsUpdateAlertStatus).toHaveBeenCalledWith("test-token", "a1", "RESOLVED", "confirmed benign");
    });
  });

  it("approves a JIT access request passing its binding hash", async () => {
    installApiMock({}, ["zero_trust:write"]);
    render(<SecurityWorkspace />);
    const approveButtons = await screen.findAllByRole("button", { name: "Approve" });
    expect(approveButtons.length).toBeGreaterThan(0);
    fireEvent.click(approveButtons[0]);
    expect(await screen.findByText("binding hash · hash-123")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(apiModule.api.zeroTrustApproveAccessRequest).toHaveBeenCalledWith("test-token", "ar1", "hash-123");
    });
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      secOpsAlerts: vi.fn().mockResolvedValue({ items: [] }),
      zeroTrustAccessRequests: vi.fn().mockResolvedValue({ items: [] }),
    });
    render(<SecurityWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.secOpsAlerts).toHaveBeenCalled();
    });
    expect(await screen.findByText("No security alerts")).toBeTruthy();
    expect(screen.getByText("No access requests")).toBeTruthy();
  });

  it("shows an error state when a feed fails", async () => {
    installApiMock({
      secOpsEvents: vi.fn().mockRejectedValue(new ApiError("server", 500, "security events down")),
    });
    render(<SecurityWorkspace />);
    expect(await screen.findByText("security events down")).toBeTruthy();
  });

  it("renders unavailable capability tiles honestly", async () => {
    render(<SecurityWorkspace />);
    expect(await screen.findByText("Realtime")).toBeTruthy();
    expect(screen.getByText("IAM Audit Log")).toBeTruthy();
    expect(screen.getByText("Blast Radius")).toBeTruthy();
    expect(screen.getByText("Attack Simulation")).toBeTruthy();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(4);
  });
});