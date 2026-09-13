import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { ExecutiveAnalytics } from "@/components/analytics/ExecutiveAnalytics";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

const api = apiModule.api;

function installDefaults() {
  Object.assign(api, {
    adminOverview: vi.fn().mockResolvedValue({
      total_organizations: 3,
      total_users: 12,
      total_repositories: 5,
      active_subscriptions: 2,
      total_agent_runs: 40,
    }),
    analyticsDashboardOverview: vi.fn().mockResolvedValue({
      tenant: "default",
      events: { total: 100, processed: 95, duplicates: 2, late: 1, invalid: 2 },
      total_cost_usd: 12.5,
      dora: { deployment_frequency: 1.2, lead_time_minutes: 0, change_failure_rate: 0.1, mttr_minutes: 50 },
      alerts: { total_alerts: 4, active: 2, triggered_today: 1 },
    }),
    analyticsDashboard: vi.fn().mockResolvedValue({
      tenant: "default",
      costs: { total_usd: 10, entry_count: 20 },
      dora: { deployment_frequency: 1.5, lead_time_minutes: 0, change_failure_rate: 0.1, mttr_minutes: 45 },
      security: { total_findings: 7, open: 3 },
      alerts: { total_alerts: 4, active: 2, triggered_today: 0 },
    }),
    analyticsDora: vi.fn().mockResolvedValue({
      deployment_frequency: 2.1,
      lead_time_minutes: 0,
      change_failure_rate: 0.05,
      mttr_minutes: 30,
    }),
    analyticsCostsSummary: vi.fn().mockResolvedValue({
      tenant: "default",
      group_by: "organization",
      total_usd: 42.5,
      entry_count: 10,
      estimated_usd: 2.5,
      actual_usd: 40,
      groups: [{ value: "org-a", total_usd: 42.5, count: 10 }],
    }),
    analyticsCostsTrend: vi.fn().mockResolvedValue({
      trend: [
        { period: "2026-09-01", granularity: "day", total_usd: 5, entry_count: 4 },
        { period: "2026-09-02", granularity: "day", total_usd: 7, entry_count: 6 },
      ],
      count: 2,
    }),
    analyticsAiModelComparison: vi.fn().mockResolvedValue({
      comparison: [{ model: "gpt-x", calls: 100, success_rate: 99.1, avg_latency_ms: 320, total_cost_usd: 3.2 }],
      count: 1,
    }),
    analyticsAiBreakdown: vi.fn().mockResolvedValue({
      tenant: "default",
      total_ai_cost_usd: 8.75,
      entry_count: 30,
    }),
    securityDashboardFull: vi.fn().mockResolvedValue({
      generated_at: "2026-09-13T00:00:00Z",
      period_days: 30,
      severity_breakdown: { critical: 1, high: 2 },
      status_breakdown: { open: 3 },
      total_findings: 3,
      top_risks: [{ id: "r1", severity: "critical", rule: "R1", risk_score: 9.1 }],
      scan_history: [],
      gate_status: { pass_rate: 80, total_evaluations: 10, blocked: 1, warned: 1, passed: 8 },
      compliance_score: 75,
      summary: { critical: 1 },
    }),
    analyticsSecuritySummary: vi.fn().mockResolvedValue({
      total_findings: 9,
      open: 4,
      open_critical: 1,
      scans_count: 6,
    }),
    securityFindingsSummary: vi.fn().mockResolvedValue({ total: 9, by_severity: { high: 2 } }),
    securityRiskSummary: vi.fn().mockResolvedValue({
      total_findings: 9,
      by_severity: { high: 2 },
      risk_score: 4.5,
      risk_level: "high",
    }),
    securityRiskScore: vi.fn().mockResolvedValue({ score: 62.5, level: "high" }),
    analyticsAlertsSummary: vi.fn().mockResolvedValue({ total_alerts: 6, active: 3, triggered_today: 1 }),
    analyticsBudgetsStatus: vi.fn().mockResolvedValue({ budgets: [], count: 0 }),
    analyticsSloStatus: vi.fn().mockResolvedValue({
      api: { total_measurements: 100, compliant: 99, compliance_rate: 0.99 },
    }),
    analyticsSloBreaches: vi.fn().mockResolvedValue({ breaches: [], count: 0 }),
    analyticsQualityIssues: vi.fn().mockResolvedValue({ issues: [], count: 0 }),
    analyticsRecommendations: vi.fn().mockResolvedValue({
      recommendations: [
        { recommendation_id: "rec-1", title: "Rightsize batch", priority: "HIGH", estimated_impact_usd: 120 },
      ],
      count: 1,
    }),
    analyticsMarketplaceSummary: vi.fn().mockResolvedValue({
      total_events: 11,
      unique_packages: 4,
      unique_users: 3,
      by_type: { install: 11 },
    }),
    analyticsMetricsList: vi.fn().mockResolvedValue({ metrics: ["http_requests", "job_duration"], count: 2 }),
    analyticsMetricsTrend: vi.fn().mockResolvedValue({
      trend: [
        { metric_name: "http_requests", period_start: "2026-09-01", value: 100, count: 10, avg: 10 },
        { metric_name: "job_duration", period_start: "2026-09-01", value: 5, count: 5, avg: 1 },
      ],
      count: 2,
    }),
    secOpsDashboard: vi.fn().mockResolvedValue({
      tenant: "t",
      alerts: { total: 5, by_status: { OPEN: 2 }, by_severity: { HIGH: 1 } },
      findings: { total: 6 },
      cases: { total: 2 },
      indicators: { total: 9 },
    }),
    secOpsRisk: vi.fn().mockResolvedValue({ risk_score: 3.2, severity: "medium", calculated_at: "2026-09-13T00:00:00Z" }),
    secOpsRiskSnapshots: vi.fn().mockResolvedValue({
      items: [
        { id: "s1", risk_score: 3.2, severity: "medium" },
        { id: "s2", risk_score: 2.1, severity: "low" },
      ],
    }),
    sreAnalytics: vi.fn().mockResolvedValue({
      period_days: 30,
      incidents: { total: 4, mttd_hours: 0.5, mtta_hours: 0.5, mttm_hours: 2, mttr_hours: 5, open: 1 },
      deployments: { total: 20, failed: 1, change_failure_rate: 0.05 },
      alerts: { total: 9, firing: 2 },
    }),
    sreDashboard: vi.fn().mockResolvedValue({
      services: { total: 6, degraded: 1 },
      slos: { total: 3, exhausted_budgets: 0 },
      alerts: { firing: 2 },
      incidents: { active: 1, severe: 0 },
      generated_at: "2026-09-13T00:00:00Z",
    }),
    sreReliabilityScore: vi.fn().mockResolvedValue({
      service_id: null,
      days: 30,
      score: 82.5,
      grade: "C",
      components: {
        change_failure_rate: { score: 90, weight: 0.2, explanation: "1/20 deployments failed -> 90/100" },
      },
      methodology: { note: "Score is only as good as its measurements." },
    }),
    observabilityDashboard: vi.fn().mockResolvedValue({
      tenant: "t",
      services: 6,
      health: { api: "HEALTHY", worker: "DEGRADED" },
    }),
    observabilityAnomalies: vi.fn().mockResolvedValue({
      tenant: "t",
      window_hours: 720,
      total: 1,
      items: [{ anomaly_id: "a1", metric_name: "cpu", severity: "high", deviation: 3.1, is_hypothesis: true }],
    }),
    observabilityAiopsStatus: vi.fn().mockResolvedValue({
      tenant: "t",
      pipeline: {},
      quality: {},
      capacity: {},
      stages: ["detect", "triage"],
      disclaimer: "Hypothesis-driven.",
    }),
    observabilityAlertFatigue: vi.fn().mockResolvedValue({ rules_evaluated: 12 }),
    governancePosture: vi.fn().mockResolvedValue({
      snapshot_id: "s",
      total_policies: 10,
      active_policies: 8,
      violations_24h: 2,
      open_exceptions: 1,
      verified_controls: 20,
      failing_controls: 1,
      computed_at: "2026-09-13T00:00:00Z",
    }),
    governanceTrends: vi.fn().mockResolvedValue({
      items: [
        {
          computed_at: "2026-09-01",
          domain: "general",
          active_policies: 8,
          violations_24h: 2,
          open_exceptions: 1,
          verified_controls: 20,
          failing_controls: 1,
        },
      ],
      total: 1,
    }),
    governancePostureHistory: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    governanceEvidenceCoverage: vi.fn().mockResolvedValue({ total: 20, expired: 2, valid: 18 }),
    governanceDrift: vi.fn().mockResolvedValue({
      items: [
        { id: "d1", finding_type: "policy", severity: "MEDIUM", resource_type: "svc", resource_id: "r1", description: "drift", status: "OPEN" },
      ],
      total: 1,
    }),
    datagovDashboard: vi.fn().mockResolvedValue({
      tenant: "t",
      assets_total: 14,
      assets_by_classification: { INTERNAL: 14 },
      classifications_total: 5,
      retention_expiring: 1,
    }),
    finopsUsageSummary: vi.fn().mockResolvedValue({
      tenant: "t",
      cost_records: 40,
      spend_cents: 12345,
      total_tokens: 9000,
      ai_executions: 5,
      ai_tokens: 8000,
      ai_cost_cents: 11000,
    }),
    finopsAggregations: vi.fn().mockResolvedValue({
      items: [
        { id: "b1", granularity: "day", bucket_start: "2026-09-01", bucket_end: "2026-09-02", dimensions: {}, total_cents: 4000, record_count: 12, total_tokens: 3000 },
      ],
      total: 1,
    }),
    finopsForecast: vi.fn().mockResolvedValue({
      id: "f",
      tenant: "t",
      forecast_type: "spend",
      dimensions: {},
      horizon_days: 30,
      period_start: "2026-09-13",
      predicted_cents: 20000,
      daily_rate_cents: 500,
      confidence: 0.8,
      quality: "MEDIUM",
      method: "linear_baseline",
      basis_buckets: 10,
      status: "READY",
      budget_exhaustion_date: null,
    }),
    finopsAnomalies: vi.fn().mockResolvedValue({
      items: [
        { id: "a1", tenant: "t", dimension_key: "provider", dimension_value: "acme", granularity: "day", bucket_start: "2026-09-01", baseline_cents: 1000, observed_cents: 5000, deviation: 4, severity: "HIGH", confidence: 0.9, evidence: {}, status: "OPEN" },
      ],
      total: 1,
    }),
    finopsModelsCompare: vi.fn().mockResolvedValue({
      items: [
        { provider: "acme", model: "m1", spend_cents: 9000, requests: 100, tokens: 5000, cost_per_request_cents: 90, tokens_per_request: 50, avg_latency_ms: 200, input_price_cents_per_m: null, output_price_cents_per_m: null, pricing_version: null },
      ],
      total: 1,
      start: "2026-08-14",
      end: "2026-09-13",
      note: "n",
    }),
    knowledgeFreshnessStats: vi.fn().mockResolvedValue({ total: 50, fresh: 40, aging: 7, stale: 3 }),
    knowledgeUsageStats: vi.fn().mockResolvedValue({
      total_queries: 120,
      by_type: { search: 100 },
      avg_latency_ms: 42.5,
      unique_users: 6,
      top_terms: ["deploy", "auth"],
    }),
    workflowHealthSummary: vi.fn().mockResolvedValue({ tenant: "t", total: 30, success: 27, failed: 3, success_rate: 90 }),
    workflowAnomalies: vi.fn().mockResolvedValue({ items: [{ run_id: "r1", type: "unusual_failure" }] }),
    workflowsList: vi.fn().mockResolvedValue({ items: [{ id: "w1", name: "Deploy", version: "1.0", status: "ACTIVE" }] }),
    mlModels: vi.fn().mockResolvedValue([{ id: "m1", status: "ACTIVE", provider: "acme", name: "m1" }]),
    mlRisks: vi.fn().mockResolvedValue([{ id: "rk1", severity: "HIGH", status: "OPEN" }]),
    mlProviders: vi.fn().mockResolvedValue([{ id: "p1", provider: "acme" }]),
    aiUsage: vi.fn().mockResolvedValue({
      items: [{ id: "u1", action: "chat" }],
      count: 1,
      totals: { requests: 25, total_tokens: 10000 },
    }),
    dataDatasets: vi.fn().mockResolvedValue({
      items: [{ id: "d1", name: "events", status: "READY", classification: "INTERNAL" }],
    }),
    dataPipelines: vi.fn().mockResolvedValue({ items: [{ id: "p1", name: "etl", status: "ACTIVE" }] }),
    enterpriseIntegrationsMetrics: vi.fn().mockResolvedValue({
      total_integrations: 4,
      active_integrations: 3,
      total_connections: 9,
      active_connections: 8,
      revoked_connections: 1,
      total_sync_jobs: 12,
      providers: ["github"],
    }),
    integrationsList: vi.fn().mockResolvedValue({ items: [{ id: "i1", name: "GitHub", status: "active" }], total: 1 }),
    whoami: vi.fn().mockResolvedValue({ permissions: ["billing:read", "billing:admin", "organization:read"] }),
    finopsReports: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    governanceReports: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    finopsReportGenerate: vi.fn().mockResolvedValue({
      id: "rep-1",
      tenant: "t",
      report_type: "showback",
      period_start: "2026-08-14",
      period_end: "2026-09-13",
      scope: { group_by: "workspace" },
      total_cents: 5000,
      lines: [],
      provenance: {},
    }),
    governanceGenerateReport: vi.fn().mockResolvedValue({
      id: "grep-1",
      tenant: "t",
      report_type: "posture",
      scope_type: "tenant",
      scope_value: "",
      period_start: "2026-08-14",
      period_end: "2026-09-13",
      summary: { violations: 2, open_exceptions: 1 },
      sections: [],
    }),
    finopsAggregationRun: vi.fn().mockResolvedValue({
      tenant: "t",
      granularity: "day",
      buckets: 30,
      records_scanned: 40,
      dimensions: {},
      start: "2026-08-14",
      end: "2026-09-13",
    }),
    finopsAnomalyDetect: vi.fn().mockResolvedValue({ anomalies: [], total: 0 }),
  });
}

describe("ExecutiveAnalytics", () => {
  beforeEach(() => {
    installDefaults();
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the executive overview with real backend numbers", async () => {
    render(<ExecutiveAnalytics />);
    expect(await screen.findByText("Organization at a glance")).toBeInTheDocument();
    expect(screen.getByText("$12.5")).toBeInTheDocument();
    expect(screen.getByText("$123.45")).toBeInTheDocument();
    expect(screen.getByText("2.1 / day")).toBeInTheDocument();
  });

  it("labels every domain with source attribution and scope badges", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText("Source: Analytics (DORA)")).toBeInTheDocument();
    expect(screen.getByText("Source: SecOps")).toBeInTheDocument();
    expect(screen.getByText("Source: FinOps")).toBeInTheDocument();
    expect(screen.getAllByText("Backend scope: default / unauthenticated").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Tenant-scoped").length).toBeGreaterThan(0);
    expect(screen.getByText("Backend scope: global — not tenant-filtered")).toBeInTheDocument();
    expect(screen.getByText("Not tenant-scoped — API authorization required")).toBeInTheDocument();
  });

  it("renders backend-provided trend buckets exactly", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByRole("img", { name: /Cost trend in USD/ })).toHaveAttribute(
      "aria-label",
      expect.stringContaining("2026-09-01 to 2026-09-02"),
    );
    expect(screen.getByRole("img", { name: /Recorded metric http_requests/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Governance violations trend/ })).toBeInTheDocument();
  });

  it("shows honest empty states when buckets are missing", async () => {
    (api.finopsAggregations as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [], total: 0 });
    (api.analyticsMetricsList as ReturnType<typeof vi.fn>).mockResolvedValue({ metrics: [], count: 0 });
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText(/No aggregation buckets/)).toBeInTheDocument();
    expect(screen.getByText("No recorded metrics exposed by /analytics/metrics/list.")).toBeInTheDocument();
  });

  it("renders forecast insufficiency without inventing a value", async () => {
    (api.finopsForecast as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "INSUFFICIENT_DATA",
      reason: "fewer than 7 spend days",
      basis_buckets: 2,
    });
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText(/fewer than 7 spend days/)).toBeInTheDocument();
  });

  it("maps the 7D preset to backend integer parameters", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "7D" }));
    await waitFor(() => expect(api.sreAnalytics as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("test-token", 7));
    expect(api.knowledgeUsageStats as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("test-token", { since_hours: 168 });
    expect(api.observabilityAnomalies as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
      "test-token",
      expect.objectContaining({ window_hours: 168 }),
    );
    expect(api.securityDashboardFull as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("test-token", 7);
  });

  it("marks 90D as unsupported where the backend caps the window", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "90D" }));
    await waitFor(() =>
      expect(
        screen.getAllByText(/90D is not supported by this source/).length,
      ).toBeGreaterThan(0),
    );
    expect(api.sreAnalytics as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("test-token", 90);
  });

  it("keeps unrelated domains available when one domain is forbidden", async () => {
    (api.secOpsDashboard as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("forbidden", 403, "Forbidden"),
    );
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText(/additional authorization is required/)).toBeInTheDocument();
    expect(screen.getByText("$12.5")).toBeInTheDocument();
    expect(screen.getByText("$123.45")).toBeInTheDocument();
  });

  it("marks expired sessions and redirects to login on 401", async () => {
    (api.analyticsDora as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("unauthorized", 401, "Unauthorized"),
    );
    render(<ExecutiveAnalytics />);
    await waitFor(() => expect(useAuthStore.getState().status).toBe("expired"));
  });

  it("reports backend 404 as not found without blanking the page", async () => {
    (api.datagovDashboard as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("server", 404, "Not found"),
    );
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText("Not found on the backend.")).toBeInTheDocument();
    expect(screen.getByText("$12.5")).toBeInTheDocument();
  });

  it("surfaces server errors per panel", async () => {
    (api.sreDashboard as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("server", 500, "boom"),
    );
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText("boom")).toBeInTheDocument();
    expect(screen.getByText("$123.45")).toBeInTheDocument();
  });

  it("refreshes authoritatively on demand", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    const calls = (api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() =>
      expect((api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(calls),
    );
  });

  it("refetches on tenant and workspace switches", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    const calls = (api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length;
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() =>
      expect((api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(calls),
    );
    const afterTenant = (api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length;
    window.dispatchEvent(new CustomEvent("workspace:switched"));
    await waitFor(() =>
      expect((api.adminOverview as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(afterTenant),
    );
  });

  it("declares realtime unavailable and offers safe AI handoffs", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
    const handoffs = screen.getAllByRole("link", { name: "Ask AI" });
    expect(handoffs.length).toBeGreaterThan(0);
    for (const link of handoffs) {
      expect(link).toHaveAttribute("href", "/ai");
    }
  });

  it("links each domain to its authoritative workspace", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    for (const href of ["/code", "/observability", "/security", "/governance", "/data", "/finops", "/workflows", "/ml", "/knowledge", "/integrations", "/ai"]) {
      expect(screen.getAllByRole("link").some((link) => link.getAttribute("href") === href)).toBe(true);
    }
  });

  it("never fabricates overall health or zero values", async () => {
    (api.securityRiskScore as ReturnType<typeof vi.fn>).mockResolvedValue({});
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.queryByText(/overall health/i)).toBeNull();
    expect(screen.queryByText(/org health/i)).toBeNull();
  });

  it("states executive insights are not exposed by the API", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(screen.getByText("Not exposed by API")).toBeInTheDocument();
  });

  it("never calls mutations during read-only load", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    expect(api.finopsReportGenerate as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
    expect(api.governanceGenerateReport as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
    expect(api.finopsAggregationRun as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
    expect(api.finopsAnomalyDetect as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("generates a FinOps report with confirmation and refetches the list", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "Generate FinOps report" }));
    expect(screen.getByRole("dialog", { name: "Generate FinOps report" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm generation" }));
    await waitFor(() =>
      expect(api.finopsReportGenerate as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        "test-token",
        "showback",
        expect.objectContaining({ group_by: "workspace" }),
      ),
    );
    await waitFor(() =>
      expect((api.finopsReports as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1),
    );
    expect(
      useToastStore.getState().toasts.some((t) => t.tone === "success" && t.message.includes("showback")),
    ).toBe(true);
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Generate FinOps report" })).toBeNull(),
    );
  });

  it("generates a governance report with confirmation and refetches the list", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "Generate governance report" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm generation" }));
    await waitFor(() =>
      expect(api.governanceGenerateReport as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ report_type: "posture", scope_type: "tenant", days: 30 }),
      ),
    );
    await waitFor(() =>
      expect((api.governanceReports as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1),
    );
    expect(
      useToastStore.getState().toasts.some((t) => t.tone === "success" && t.message.includes("posture")),
    ).toBe(true);
  });

  it("runs aggregation and refreshes spend buckets", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    const calls = (api.finopsAggregations as ReturnType<typeof vi.fn>).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Run spend aggregation" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm aggregation run" }));
    await waitFor(() =>
      expect(api.finopsAggregationRun as ReturnType<typeof vi.fn>).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ granularity: "day" }),
      ),
    );
    await waitFor(() =>
      expect((api.finopsAggregations as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(calls),
    );
    expect(
      useToastStore.getState().toasts.some((t) => t.tone === "success" && t.message.includes("30 buckets")),
    ).toBe(true);
  });

  it("detects anomalies and refreshes the anomaly list", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    const calls = (api.finopsAnomalies as ReturnType<typeof vi.fn>).mock.calls.length;
    fireEvent.click(screen.getByRole("button", { name: "Detect spend anomalies" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm anomaly detection" }));
    await waitFor(() =>
      expect(api.finopsAnomalyDetect as ReturnType<typeof vi.fn>).toHaveBeenCalledWith("test-token", 14),
    );
    await waitFor(() =>
      expect((api.finopsAnomalies as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(calls),
    );
  });

  it("keeps the confirmation open when the backend denies the action", async () => {
    (api.finopsReportGenerate as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("forbidden", 403, "Forbidden"),
    );
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "Generate FinOps report" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm generation" }));
    expect(await screen.findByText(/additional authorization is required/)).toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Generate FinOps report" })).toBeInTheDocument();
    expect(api.finopsReports as ReturnType<typeof vi.fn>).toHaveBeenCalledTimes(1);
  });

  it("validates anomaly lookback input before calling the backend", async () => {
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "Detect spend anomalies" }));
    fireEvent.change(screen.getByDisplayValue("14"), { target: { value: "abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm anomaly detection" }));
    expect(await screen.findByText(/Lookback must be between 1 and 90 days/)).toBeInTheDocument();
    expect(api.finopsAnomalyDetect as ReturnType<typeof vi.fn>).not.toHaveBeenCalled();
  });

  it("disables admin actions without billing:admin", async () => {
    (api.whoami as ReturnType<typeof vi.fn>).mockResolvedValue({ permissions: ["billing:read"] });
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Run spend aggregation" })).toBeDisabled(),
    );
    expect(screen.getByRole("button", { name: "Detect spend anomalies" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Generate FinOps report" })).toBeEnabled();
  });

  it("refreshes lists and warns when the backend reports a stale target", async () => {
    (api.finopsReportGenerate as ReturnType<typeof vi.fn>).mockRejectedValue(
      new ApiError("server", 409, "Conflict"),
    );
    render(<ExecutiveAnalytics />);
    await screen.findByText("Organization at a glance");
    fireEvent.click(screen.getByRole("button", { name: "Generate FinOps report" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm generation" }));
    await waitFor(() =>
      expect((api.finopsReports as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1),
    );
    expect(
      useToastStore.getState().toasts.some((t) => t.tone === "warning"),
    ).toBe(true);
  });
});
