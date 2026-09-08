import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ObservabilityWorkspace } from "@/components/observability/ObservabilityWorkspace";
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
  services: 3,
  health: { "api-gateway": "healthy", "auth-svc": "degraded" },
};

const statusSummary = {
  overall: "operational",
  components: 4,
  by_status: { operational: 4 },
};

const statusComponents = {
  total: 2,
  items: [
    {
      id: "1",
      component_id: "status-api",
      service_id: "api-gateway",
      name: "API Gateway",
      description: "",
      status: "operational",
      region: "us-east-1",
      public: true,
      history: [],
    },
    {
      id: "2",
      component_id: "status-auth",
      service_id: "auth-svc",
      name: "Auth Service",
      description: "",
      status: "degraded",
      region: "us-east-1",
      public: false,
      history: [],
    },
  ],
};

const aiopsStatus = {
  tenant: "t1",
  pipeline: [],
  stages: ["telemetry", "detection", "correlation"],
  disclaimer: "AIOps status is hypothesis-driven; verify before action",
  capacity: {},
  quality: {
    tenant: "t1",
    service: "all",
    overall_score: 0.72,
    grade: "good",
    breakdown: {
      completeness: { score: 0.8, weight: 0.3, note: "..." },
      freshness: { score: 0.6, weight: 0.25, note: "..." },
    },
    recommendations: [null, null],
    scored_at: "2026-01-01T00:00:00Z",
  },
};

const analytics = {
  period_days: 30,
  incidents: {
    total: 2,
    mttd_hours: 1.5,
    mtta_hours: 1.5,
    mttm_hours: 2.0,
    mttr_hours: 3.5,
    open: 1,
  },
  deployments: { total: 10, failed: 1, change_failure_rate: 0.1 },
  alerts: { total: 6, firing: 2 },
};

const alertsResponse = {
  items: [
    { id: "a1", resource: "api-gateway", status: "FIRING", severity: "WARNING", fingerprint: "fp-1" },
    { id: "a2", resource: "auth-svc", status: "RESOLVED", severity: "CRITICAL", fingerprint: "fp-2" },
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

function installApiMock(overrides: Record<string, unknown> = {}): void {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    observabilityDashboard: vi.fn().mockResolvedValue(dashboard),
    sreStatusSummary: vi.fn().mockResolvedValue(statusSummary),
    sreStatusComponents: vi.fn().mockResolvedValue(statusComponents),
    observabilityAiopsStatus: vi.fn().mockResolvedValue(aiopsStatus),
    sreAnalytics: vi.fn().mockResolvedValue(analytics),
    observabilityAlerts: vi.fn().mockResolvedValue(alertsResponse),
    observabilityAlertFatigue: vi.fn().mockResolvedValue(fatigue),
  };
  Object.assign(api, defaults, overrides);
}

describe("ObservabilityWorkspace", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and manual refresh", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByRole("button", { name: /refresh/i })).toBeTruthy();
  });

  it("renders service health summary from the backend response", async () => {
    render(<ObservabilityWorkspace />);
    expect((await screen.findAllByText("OPERATIONAL")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Components|Status page/).length).toBeGreaterThan(0);
    expect(apiModule.api.observabilityDashboard).toHaveBeenCalled();
    expect(apiModule.api.sreStatusSummary).toHaveBeenCalled();
  });

  it("renders registered services health map", async () => {
    render(<ObservabilityWorkspace />);
    expect((await screen.findAllByText("api-gateway")).length).toBeGreaterThan(0);
    expect(screen.getByText("Service count")).toBeTruthy();
  });

  it("renders status page components with badges", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("API Gateway")).toBeTruthy();
    expect(screen.getByText("Auth Service")).toBeTruthy();
    expect(screen.getAllByText(/OPERATIONAL|DEGRADED/).length).toBeGreaterThan(0);
  });

  it("renders AIOps pipeline stages and quality grade, never raw pipeline", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("telemetry")).toBeTruthy();
    expect(screen.getByText("detection")).toBeTruthy();
    expect(screen.getByText("correlation")).toBeTruthy();
    expect(screen.getByText("GOOD")).toBeTruthy();
  });

  it("renders incident analytics including the backend MTTD quirk verbatim", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("Incident analytics · 30 days")).toBeTruthy();
    expect(screen.getByText("MTTD (hours)")).toBeTruthy();
    expect(screen.getByText("MTTA (hours)")).toBeTruthy();
    expect(screen.getByText("MTTM (hours)")).toBeTruthy();
    expect(screen.getByText("MTTR (hours)")).toBeTruthy();
    expect(screen.getByText("Change failure rate")).toBeTruthy();
    expect(screen.getByText("10.0%").textContent).toBe("10.0%");
  });

  it("renders alerts with backend statuses", async () => {
    render(<ObservabilityWorkspace />);
    expect((await screen.findAllByText("api-gateway")).length).toBeGreaterThan(0);
    expect(screen.getByText("FIRING")).toBeTruthy();
    expect(screen.getByText("RESOLVED")).toBeTruthy();
  });

  it("renders alert fatigue signals", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText(/DEDUPLICATION/)).toBeTruthy();
    expect(screen.getByText(/TUNE FINGERPRINT_FIELDS/)).toBeTruthy();
  });

  it("renders unavailable capability tiles", async () => {
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("Realtime")).toBeTruthy();
    expect(screen.getByText("Traces")).toBeTruthy();
    expect(screen.getByText("Events Feed")).toBeTruthy();
    expect(screen.getAllByText("UNAVAILABLE").length).toBeGreaterThanOrEqual(6);
  });

  it("shows an error state when the alerts feed fails", async () => {
    installApiMock({
      observabilityAlerts: vi.fn().mockRejectedValue(new ApiError("server", 500, "backend down")),
    });
    render(<ObservabilityWorkspace />);
    expect(await screen.findByText("backend down")).toBeTruthy();
  });

  it("renders empty states for feeds without data", async () => {
    installApiMock({
      observabilityAlerts: vi.fn().mockResolvedValue({ items: [] }),
    });
    render(<ObservabilityWorkspace />);
    await waitFor(() => {
      expect(apiModule.api.observabilityAlerts).toHaveBeenCalled();
    });
    expect(screen.getByText("No alerts")).toBeTruthy();
  });
});