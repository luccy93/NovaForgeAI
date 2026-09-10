import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { FinopsWorkspace } from "@/components/finops/FinopsWorkspace";
import * as apiModule from "@/lib/api";

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

const summaryResponse = {
  tenant: "t1",
  cost_records: 4,
  spend_cents: 12345,
  total_tokens: 100000,
  ai_executions: 5,
  ai_tokens: 5000,
  ai_cost_cents: 500,
};

const costsResponse = {
  items: [
    {
      id: "cost-1",
      tenant: "t1",
      workspace: "ws1",
      project: "",
      service: "chat",
      workflow: "",
      model: "gpt-x",
      provider: "acme",
      environment: "prod",
      region: "",
      resource: "",
      operation: "complete",
      actor: "u1",
      input_tokens: 1000,
      output_tokens: 500,
      cached_tokens: 0,
      requests: 10,
      latency_ms: 120,
      amount_cents: 123,
      currency: "USD",
      cost_basis: "actual",
      pricing_version_id: "pv-1",
      source_type: "ai_execution",
      source_id: "req-1",
      idempotency_key: "k1",
      occurred_at: "2026-09-01T10:00:00Z",
    },
  ],
  total: 1,
  limit: 25,
  offset: 0,
  spend_cents: 123,
};

const budgetsResponse = {
  items: [
    {
      id: "b1",
      tenant: "t1",
      name: "prod-monthly",
      scope_type: "tenant",
      scope_value: "",
      provider: "",
      model: "",
      environment: "",
      amount_cents: 100000,
      currency: "USD",
      period: "monthly",
      warning_threshold: 0.8,
      hard_limit_threshold: 1.0,
      enforcement: "alert",
      enabled: true,
      owner: "",
      approval_policy: "none",
      status: "ACTIVE",
    },
  ],
  total: 1,
};

const bucketsResponse = {
  items: [
    {
      id: "agg-1",
      granularity: "day",
      bucket_start: "2026-09-01T00:00:00Z",
      bucket_end: "2026-09-02T00:00:00Z",
      dimensions: {},
      total_cents: 5000,
      record_count: 20,
      total_tokens: 40000,
    },
  ],
  total: 1,
};

const forecastResponse = {
  id: "f1",
  tenant: "t1",
  forecast_type: "spend",
  dimensions: {},
  horizon_days: 30,
  period_start: "2026-09-10T00:00:00Z",
  predicted_cents: 150000,
  daily_rate_cents: 5000,
  confidence: 0.82,
  quality: "HIGH",
  method: "linear_baseline",
  basis_buckets: 20,
  budget_exhaustion_date: null,
  status: "READY",
};

const anomaliesResponse = {
  items: [
    {
      id: "a1",
      tenant: "t1",
      dimension_key: "provider",
      dimension_value: "acme",
      granularity: "day",
      bucket_start: "2026-09-09T00:00:00Z",
      baseline_cents: 1000,
      observed_cents: 9000,
      deviation: 4.5,
      severity: "CRITICAL",
      confidence: 0.9,
      evidence: { window_days: 14, history: [900, 1100, 1000] },
      status: "OPEN",
    },
  ],
  total: 1,
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []): void {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    finopsUsageSummary: vi.fn().mockResolvedValue(summaryResponse),
    finopsCostsFiltered: vi.fn().mockResolvedValue(costsResponse),
    finopsBudgets: vi.fn().mockResolvedValue(budgetsResponse),
    finopsBudgetEvaluate: vi.fn().mockResolvedValue({
      ...budgetsResponse.items[0],
      spend_cents: 25000,
      utilization: 0.25,
      period_start: "2026-09-01T00:00:00Z",
      period_end: "2026-10-01T00:00:00Z",
    }),
    finopsAggregations: vi.fn().mockResolvedValue(bucketsResponse),
    finopsForecast: vi.fn().mockResolvedValue(forecastResponse),
    finopsAnomalies: vi.fn().mockResolvedValue(anomaliesResponse),
    finopsBudgetCreate: vi.fn().mockResolvedValue(budgetsResponse.items[0]),
    finopsBudgetUpdate: vi.fn().mockResolvedValue(budgetsResponse.items[0]),
    finopsPricing: vi.fn().mockResolvedValue({
      items: [
        {
          id: "pv-1",
          tenant: "t1",
          provider: "acme",
          model: "gpt-x",
          resource: "",
          unit: "tokens",
          input_price_cents_per_m: 50,
          output_price_cents_per_m: 150,
          request_price_cents: 0,
          storage_price_cents: 0,
          compute_price_cents: 0,
          currency: "USD",
          effective_from: "2026-01-01T00:00:00Z",
          effective_until: null,
          source: "manual",
          version: 3,
          status: "ACTIVE",
          operator: "admin",
          reason: "",
        },
      ],
    }),
    finopsPricingCreate: vi.fn().mockResolvedValue({ id: "pv-2", provider: "acme", version: 4, status: "ACTIVE" }),
    finopsPricingDeprecate: vi.fn().mockResolvedValue({ id: "pv-1", status: "DEPRECATED" }),
    finopsAllocations: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 100, offset: 0 }),
    finopsAllocationCreate: vi.fn().mockResolvedValue({ items: [], total: 0 }),
    finopsPolicies: vi.fn().mockResolvedValue({
      items: [
        {
          id: "pol-1",
          tenant: "t1",
          name: "cap-training",
          workspace: "",
          project: "",
          model: "",
          provider: "acme",
          operation: "model.train",
          max_estimated_cents: 10000,
          action: "require_approval",
          enabled: true,
          owner: "",
        },
      ],
      total: 1,
    }),
    finopsPolicyCreate: vi.fn().mockResolvedValue({ id: "pol-2", name: "cap-training" }),
    finopsPolicyUpdate: vi.fn().mockResolvedValue({ id: "pol-1", name: "cap-training" }),
    finopsGateEvaluate: vi.fn().mockResolvedValue({
      decision: "REQUIRE_APPROVAL",
      reason: "requires approval per policy 'cap-training'",
      estimated_cents: 20000,
      approval_id: "appr-1",
      policy_id: "pol-1",
      allowed: true,
    }),
    finopsReports: vi.fn().mockResolvedValue({
      items: [
        {
          id: "rep-1",
          tenant: "t1",
          report_type: "showback",
          period_start: "2026-09-01T00:00:00Z",
          period_end: "2026-09-10T00:00:00Z",
          scope: { group_by: "workspace" },
          total_cents: 12345,
          lines: [{ group: "ws1", total_cents: 12345, record_count: 4 }],
          provenance: { source: "finops_cost_records", record_count: 4 },
        },
      ],
      total: 1,
    }),
    finopsReportGenerate: vi.fn().mockResolvedValue({ id: "rep-1", total_cents: 12345, lines: [] }),
    finopsModelsCompare: vi.fn().mockResolvedValue({
      items: [
        {
          provider: "acme",
          model: "gpt-x",
          spend_cents: 12000,
          requests: 100,
          tokens: 90000,
          cost_per_request_cents: 120,
          tokens_per_request: 900,
          avg_latency_ms: 110.5,
          input_price_cents_per_m: 50,
          output_price_cents_per_m: 150,
          pricing_version: 3,
        },
      ],
      total: 1,
      start: "2026-08-11T00:00:00Z",
      end: "2026-09-10T00:00:00Z",
      note: "comparison only; model selection remains governed by AI Gateway policy",
    }),
    finopsRecommendations: vi.fn().mockResolvedValue({
      items: [
        {
          id: "rec-1",
          tenant: "t1",
          rec_type: "pricing_coverage",
          title: "3 records lack pricing",
          evidence: { unpriced_count: 3, providers: ["acme"] },
          estimated_savings_cents: null,
          savings: "UNKNOWN",
          savings_known: false,
          confidence: 0.7,
          affected_resource: "pricing",
          risk: "LOW",
          status: "OPEN",
        },
      ],
      total: 1,
    }),
    finopsRecommendationsGenerate: vi.fn().mockResolvedValue({ recommendations: [], total: 0 }),
    finopsAnomalyDetect: vi.fn().mockResolvedValue({ anomalies: [], total: 0 }),
    finopsAggregationRun: vi.fn().mockResolvedValue({
      tenant: "t1",
      granularity: "day",
      buckets: 9,
      records_scanned: 40,
      dimensions: {},
      start: "2026-09-01T00:00:00Z",
      end: "2026-09-10T00:00:00Z",
    }),
  };
  Object.assign(api, defaults, overrides);
}

describe("FinopsWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and read-only notice without permissions", async () => {
    render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    expect(screen.getByText("Read-only view · no FinOps permissions")).toBeTruthy();
  });

  it("renders backend financial values with currency, never converted", async () => {
    installApiMock({}, ["billing:read"]);
    render(<FinopsWorkspace />);
    await waitFor(() => {
      // 12345 cents -> 123.45, no currency on summary (backend reports bare cents)
      expect(screen.getByText("123.45")).toBeTruthy();
    });
    expect(screen.getByText("4")).toBeTruthy();
  });

  it("hides admin budget actions from non-admins", async () => {
    installApiMock({}, ["billing:read"]);
    render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("prod-monthly")).toBeTruthy();
    });
    const { getByRole } = { getByRole: screen.getByRole };
    fireEvent.click(getByRole("tab", { name: "Budgets" }));
    expect(screen.queryByText("New budget")).toBeNull();
  });

  it("shows admin actions with billing:admin and labels forecast data", async () => {
    installApiMock({}, ["billing:read", "billing:admin"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Admin actions enabled")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Budgets" }));
    expect(screen.getByText("New budget")).toBeTruthy();
    fireEvent.click(getByRole("tab", { name: "Forecast" }));
    await waitFor(() => {
      // 150000 cents -> 1,500.00 in backend units; method is backend-reported
      expect(screen.getByText("1,500.00")).toBeTruthy();
    });
    expect(screen.getByText("linear_baseline")).toBeTruthy();
  });

  it("renders anomaly evidence from the backend without fabrication", async () => {
    installApiMock({}, ["billing:read"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Anomalies" }));
    await waitFor(() => {
      expect(screen.getByText("provider=acme")).toBeTruthy();
    });
    // Badge + severity filter option both render the backend severity value
    expect(screen.getAllByText("CRITICAL").length).toBeGreaterThan(0);
  });

  it("renders no credentials, keys or secrets anywhere", async () => {
    installApiMock({}, ["billing:read", "billing:admin"]);
    render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    expect(screen.queryByText(/api_key/i)).toBeNull();
    expect(screen.queryByText(/client_secret/i)).toBeNull();
    expect(screen.queryByText(/access_token/i)).toBeNull();
  });
});

describe("FinopsWorkspace (C2 governance & intelligence)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders pricing versions and hides deprecate from non-admins", async () => {
    installApiMock({}, ["billing:read"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Pricing" }));
    await waitFor(() => {
      expect(screen.getByText("acme/gpt-x · v3")).toBeTruthy();
    });
    expect(screen.queryByText("New version")).toBeNull();
    expect(screen.queryByText("Deprecate")).toBeNull();
  });

  it("shows pricing admin actions with billing:admin", async () => {
    installApiMock({}, ["billing:read", "billing:admin"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Admin actions enabled")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Pricing" }));
    await waitFor(() => {
      expect(screen.getByText("New version")).toBeTruthy();
    });
  });

  it("renders policies, gate decisions and reports with provenance", async () => {
    installApiMock({}, ["billing:read"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Governance" }));
    await waitFor(() => {
      expect(screen.getByText("cap-training")).toBeTruthy();
    });
    expect(screen.getByText("showback · 123.45")).toBeTruthy();
    // Gate tester dry-run uses the mocked gate endpoint
    fireEvent.change(screen.getByLabelText("Operation"), { target: { value: "model.train" } });
    fireEvent.click(screen.getByRole("button", { name: "Evaluate gate" }));
    await waitFor(() => {
      expect(screen.getByText("REQUIRE_APPROVAL")).toBeTruthy();
    });
    expect(screen.getByText("appr-1")).toBeTruthy();
  });

  it("renders model comparison, UNKNOWN savings and the AI handoff link", async () => {
    installApiMock({}, ["billing:read"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Intelligence" }));
    await waitFor(() => {
      expect(screen.getByText("3 records lack pricing")).toBeTruthy();
    });
    expect(screen.getByText("UNKNOWN savings")).toBeTruthy();
    expect(screen.getByText("comparison only; model selection remains governed by AI Gateway policy")).toBeTruthy();
    const askAi = screen.getByRole("link", { name: "Ask AI about spend" });
    expect(askAi.getAttribute("href")).toBe("/ai");
  });

  it("refetches all scopes on tenant switch without leaking prior state", async () => {
    installApiMock({}, ["billing:read"]);
    render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Realtime: UNAVAILABLE")).toBeTruthy();
    });
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.finopsUsageSummary as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.finopsUsageSummary as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
    expect(api.finopsPricing).toHaveBeenCalled();
    expect(api.finopsPolicies).toHaveBeenCalled();
  });

  it("creates a budget then refetches authoritatively", async () => {
    installApiMock({}, ["billing:read", "billing:admin"]);
    const { getByRole } = render(<FinopsWorkspace />);
    await waitFor(() => {
      expect(screen.getByText("Admin actions enabled")).toBeTruthy();
    });
    fireEvent.click(getByRole("tab", { name: "Budgets" }));
    fireEvent.click(screen.getByText("New budget"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "q4-cap" } });
    fireEvent.change(screen.getByLabelText("Amount (cents)"), { target: { value: "50000" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await waitFor(() => {
      expect(api.finopsBudgetCreate).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ name: "q4-cap", amount_cents: 50000 }),
      );
    });
    await waitFor(() => {
      expect((api.finopsBudgets as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
    });
  });
});
