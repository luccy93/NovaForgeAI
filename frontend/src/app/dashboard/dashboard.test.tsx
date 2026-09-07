import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import DashboardPage from "@/app/dashboard/page";
import * as apiModule from "@/lib/api";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    api: {
      ...actual.api,
      me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
      finopsSummary: vi.fn().mockResolvedValue({ spend_cents: 123, cost_records: 2, total_tokens: 1000, ai_executions: 5, ai_tokens: 500, ai_cost_cents: 50, tenant: "t1" }),
      healthDependencies: vi.fn().mockResolvedValue({ status: "healthy", checks: { database: { status: "healthy", latency_ms: 5 } } }),
      aiUsage: vi.fn().mockResolvedValue({ items: [{ id: "1", action: "chat", model: "gpt-4o", total_tokens: 100, created_at: new Date().toISOString() }], count: 1 }),
      workflowHealth: vi.fn().mockResolvedValue({ total: 10, success: 8, failed: 2, success_rate: 0.8 }),
      listWorkflowRuns: vi.fn().mockResolvedValue({ items: [{ run_id: "r1", status: "COMPLETED" }] }),
      securityDashboard: vi.fn().mockResolvedValue({ total: 5, open_findings: 2 }),
      governancePosture: vi.fn().mockResolvedValue({ posture_score: 85, violations: [] }),
      integrationsList: vi.fn().mockResolvedValue({ items: [{ id: "i1", name: "GitHub", provider: "github", status: "ACTIVE", health: "healthy" }], total: 1 }),
      recentActivity: vi.fn().mockResolvedValue({ events: [{ id: "e1", event_type: "test.event", source: "test", created_at: new Date().toISOString() }], count: 1 }),
      knowledgeSearch: vi.fn().mockResolvedValue({ items: [{ title: "Doc", snippet: "hello", score: 0.9 }], total: 1 }),
      knowledgeHistory: vi.fn().mockResolvedValue({ items: [], total: 3 }),
    },
  };
});

describe("Dashboard command center", () => {
  beforeEach(() => {
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  it("renders real API data", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /command center/i })).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Current spend")).toBeInTheDocument());
    expect(screen.getByText(/2 records/)).toBeInTheDocument();
  });

  it("shows platform health as operational", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("System status")).toBeInTheDocument());
    await waitFor(() => expect(screen.getAllByText("healthy").length).toBeGreaterThan(0));
  });

  it("handles tenant isolation - switches clear previous data", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByRole("heading", { name: /command center/i })).toBeInTheDocument());
    // Simulate organization switch - this dispatches tenant:switched which clears+refetches
    useTenantStore.getState().switchOrganization("org-2");
    expect(useTenantStore.getState().workspaceId).toBeNull();
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const summaryCalls = (mocked.finopsSummary as ReturnType<typeof vi.fn>).mock.calls.length;
    // Refetch should have happened after dispatch (initial + after switch)
    expect(summaryCalls).toBeGreaterThanOrEqual(2);
  });

  it("preserves existing FinOps and Knowledge behavior", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByPlaceholderText("Search the knowledge base…")).toBeInTheDocument());
    expect(screen.getAllByRole("button", { name: "Search" }).length).toBeGreaterThan(0);
  });

  it("shows honest NO DATA when empty", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    mocked.aiUsage.mockResolvedValueOnce({ items: [], count: 0 });
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getAllByText("AI activity").length).toBeGreaterThan(0));
    await waitFor(() => expect(screen.getByText("No data")).toBeInTheDocument());
  });

  it("shows temporarily unavailable on error", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    mocked.securityDashboard.mockRejectedValueOnce(new Error("Service down"));
    render(<DashboardPage />);
    await waitFor(() => expect(screen.getByText("Security posture")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("Temporarily unavailable")).toBeInTheDocument());
  });
});
