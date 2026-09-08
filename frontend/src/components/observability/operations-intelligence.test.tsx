import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { OperationsIntelligence } from "@/components/observability/OperationsIntelligence";
import { useToastStore } from "@/stores/toast";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import type { ObservabilityAlertsResponse } from "@/types/observability";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

const incident = {
  id: "inc-1",
  incident_id: "INC-001",
  organization_id: "org-1",
  title: "API gateway latency spike",
  description: "Elevated latency observed on api-gateway.",
  severity: "SEV2",
  status: "detected",
  service_id: "api-gateway",
  region: "us-east-1",
  commander: "u1",
  impact: (null as unknown) as Record<string, unknown>,
  root_cause: "Pending investigation",
  detection: "Latency SLO breach on api-gateway",
  related_deployments: [],
  related_changes: [],
  related_alerts: [],
  postmortem_id: "",
  detected_at: "2026-01-01T10:00:00Z",
  acknowledged_at: null,
  mitigated_at: null,
  resolved_at: null,
  closed_at: null,
  created_at: "2026-01-01T10:00:00Z",
};

const incident2 = { ...incident, id: "inc-2", incident_id: "INC-002", title: "Auth service errors", status: "resolved" };

const timeline = {
  incident_id: "inc-1",
  events: [
    { event_type: "detected", actor: "system", message: "Alert fired for api-gateway latency", occurred_at: "2026-01-01T10:00:00Z", metadata: {} },
    { event_type: "acknowledged", actor: "u1", message: "Acknowledged the incident", occurred_at: "2026-01-01T10:05:00Z" },
  ],
};

const service = {
  id: "svc-1",
  service_id: "api-gateway",
  name: "API Gateway",
  description: "Edge gateway",
  owner: "u1",
  team: "platform",
  tier: "T1",
  criticality: "critical",
  deployment_strategy: "blue-green",
  scaling_strategy: "hpa",
  backup_strategy: "none",
  rto_minutes: 30,
  rpo_minutes: 5,
  runbook_id: "rb-1",
  on_call: "u2",
  status: "operational",
  metadata: undefined,
  created_at: "2025-01-01T00:00:00Z",
  updated_at: "2025-06-01T00:00:00Z",
};

const deps = {
  service_id: "api-gateway",
  dependencies: [
    { depends_on: "auth-svc", kind: "network", critical: true },
    { depends_on: "payments-cache", kind: "cache", critical: false },
  ],
  edges: {},
};

const alerts: ObservabilityAlertsResponse = {
  items: [
    { id: "a1", resource: "api-gateway", status: "FIRING", severity: "WARNING", fingerprint: "fp-1" },
    { id: "a2", resource: "auth-svc", status: "ACKNOWLEDGED", severity: "CRITICAL", fingerprint: "fp-2" },
  ],
};

const fatigue = {
  window_hours: 24,
  total: 6,
  duplicates: { "fp-1": 6 },
  high_frequency: ["fp-1"],
  flapping: [],
  recommendations: [{ type: "deduplication", action: "tune fingerprint_fields", evidence: {} }],
};

function installApiMock(permissions: string[] = ["admin:all"], overrides: Record<string, unknown> = {}): void {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions }),
    sreListIncidents: vi.fn().mockResolvedValue({ total: 2, items: [incident, incident2] }),
    sreGetIncident: vi.fn().mockResolvedValue(incident),
    sreIncidentTimeline: vi.fn().mockResolvedValue(timeline),
    sreListServices: vi.fn().mockResolvedValue({ total: 1, items: [service] }),
    sreGetService: vi.fn().mockResolvedValue(service),
    sreServiceDependencies: vi.fn().mockResolvedValue(deps),
    incidentTransition: vi.fn().mockResolvedValue({ ...incident, status: "investigating" }),
    acknowledgeAlert: vi.fn().mockResolvedValue({ id: "a1", status: "ACKNOWLEDGED" }),
    resolveAlert: vi.fn().mockResolvedValue({ id: "a1", status: "RESOLVED" }),
  };
  Object.assign(api, defaults, overrides);
}

function renderWorkspace() {
  const onAlertsChanged = vi.fn();
  const result = render(
    <OperationsIntelligence alerts={alerts} fatigue={fatigue} onAlertsChanged={onAlertsChanged} />,
  );
  return { onAlertsChanged, ...result };
}

describe("OperationsIntelligence", () => {
  beforeEach(() => {
    installApiMock();
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows admin mutation controls for ops admins", async () => {
    renderWorkspace();
    expect(await screen.findByText("API gateway latency spike")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Advance status" })).toBeTruthy();
    expect(screen.queryByText(/Read-only view/)).toBeNull();
  });

  it("hides mutation controls for non-admins", async () => {
    installApiMock(["settings:admin"]);
    renderWorkspace();
    expect(await screen.findByText("API gateway latency spike")).toBeTruthy();
    expect(screen.getByText(/Read-only view/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Advance status" })).toBeNull();
  });

  it("loads incident detail and audit trail when an incident is selected", async () => {
    renderWorkspace();
    await screen.findByText("API gateway latency spike");
    expect(await screen.findByText("Audit trail")).toBeTruthy();
    expect(await screen.findByText(/Alert fired for api-gateway latency/)).toBeTruthy();
    expect(screen.getAllByText("detected").length).toBeGreaterThan(0);
    expect(screen.getByText(/Root cause/)).toBeTruthy();
  });

  it("transitions an incident via the confirm modal", async () => {
    installApiMock();
    renderWorkspace();
    await screen.findByText("API gateway latency spike");
    fireEvent.click(screen.getByRole("button", { name: "Advance status" }));
    await screen.findByText("Transition incident?");
    expect(screen.getByLabelText("Target status")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Target status"), { target: { value: "investigating" } });
    fireEvent.change(screen.getByLabelText("Note"), { target: { value: "Investigating root cause" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm transition" }));
    await waitFor(() =>
      expect(apiModule.api.incidentTransition).toHaveBeenCalledWith("test-token", "inc-1", {
        target: "investigating",
        note: "Investigating root cause",
      }),
    );
    expect(useToastStore.getState().toasts.some((t) => t.tone === "success")).toBe(true);
  });

  it("shows a permission warning when the backend rejects a transition with 403", async () => {
    installApiMock(["admin:all"], {
      incidentTransition: vi.fn().mockRejectedValue(new ApiError("forbidden", 403, "Forbidden")),
    });
    renderWorkspace();
    await screen.findByText("API gateway latency spike");
    fireEvent.click(screen.getByRole("button", { name: "Advance status" }));
    await screen.findByText("Transition incident?");
    fireEvent.click(screen.getByRole("button", { name: "Confirm transition" }));
    await waitFor(() =>
      expect(useToastStore.getState().toasts.some((t) => t.tone === "warning")).toBe(true),
    );
    expect(useToastStore.getState().toasts.some((t) => t.message.includes("don't have permission"))).toBe(true);
  });

  it("acknowledges an alert and refreshes the feed", async () => {
    const { onAlertsChanged } = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Alert fatigue" }));
    expect((await screen.findAllByText("fp-1")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole("button", { name: "Ack" }));
    await waitFor(() => expect(apiModule.api.acknowledgeAlert).toHaveBeenCalledWith("test-token", "a1"));
    expect(onAlertsChanged).toHaveBeenCalled();
    expect(useToastStore.getState().toasts.some((t) => t.tone === "success")).toBe(true);
  });

  it("resolves an alert via the confirm modal", async () => {
    const { onAlertsChanged } = renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Alert fatigue" }));
    expect((await screen.findAllByText("fp-1")).length).toBeGreaterThan(0);
    fireEvent.click(screen.getAllByRole("button", { name: "Resolve" })[0]);
    await screen.findByText("Resolve alert?");
    fireEvent.click(screen.getByRole("button", { name: "Confirm resolve alert" }));
    await waitFor(() => expect(apiModule.api.resolveAlert).toHaveBeenCalledWith("test-token", "a1"));
    expect(onAlertsChanged).toHaveBeenCalled();
  });

  it("renders services with dependencies on the services tab", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Services" }));
    expect(await screen.findByText("API Gateway")).toBeTruthy();
    expect(await screen.findByText("RTO")).toBeTruthy();
    expect(await screen.findByText("auth-svc")).toBeTruthy();
    expect(screen.getByText("CRITICAL")).toBeTruthy();
    expect(screen.getByText("OPTIONAL")).toBeTruthy();
  });

  it("renders fatigue report detail on the fatigue tab", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "Alert fatigue" }));
    expect(await screen.findByText(/DEDUPLICATION/)).toBeTruthy();
    expect(screen.getByText("High frequency")).toBeTruthy();
    expect(screen.getByText("Duplicate noise")).toBeTruthy();
  });

  it("offers an AI handoff with operational context", async () => {
    renderWorkspace();
    fireEvent.click(screen.getByRole("button", { name: "AI handoff" }));
    expect((await screen.findAllByText(/AI handoff/)).length).toBeGreaterThan(1);
    const link = screen.getByRole("link", { name: /Open AI workspace/ });
    expect(link.getAttribute("href")).toBe("/ai");
    expect(screen.getByText(/2 live alerts/)).toBeTruthy();
  });
});