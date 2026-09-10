import { render, screen, waitFor, cleanup, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DataPlatformWorkspace } from "@/components/data/DataPlatformWorkspace";
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

const datasetsResponse = {
  items: [
    { id: "ds-1", name: "events", status: "ACTIVE", classification: "INTERNAL", owner: "data-team", region: "eu-west" },
    { id: "ds-2", name: "archive-logs", status: "DRAFT", classification: "CONFIDENTIAL", owner: "", region: "" },
  ],
};

const datasetDetail = {
  id: "ds-1",
  name: "events",
  description: "raw event stream",
  status: "ACTIVE",
  classification: "INTERNAL",
  owner: "data-team",
  region: "eu-west",
  storage_location: "s3://lake/raw",
};

const sourcesResponse = {
  items: [{ id: "src-1", name: "warehouse", connector: "postgresql", region: "eu-west" }],
};

const schemasResponse = {
  items: [{ id: "sch-1", dataset_id: "ds-1", version: "1.0", is_published: true }],
};

const pipelinesResponse = {
  items: [{ id: "pipe-1", name: "nightly-sync", status: "ACTIVE", priority: "NORMAL" }],
};

const jobsResponse = {
  items: [{ run_id: "run-abc-123", status: "SUCCESS", records: 1000 }],
};

const qualityResults = {
  items: [{ rule_id: "rule-1", passed: 95, failed: 5, timestamp: "2026-09-09T10:00:00Z" }],
};

const lineageGraph = {
  node: "dataset:ds-1",
  upstream: [{ source: "source:src-1", target: "dataset:ds-1", transformation: "ingest" }],
  downstream: [{ source: "dataset:ds-1", target: "dataset:ds-2" }],
  provenance: [{ edge: 1 }],
};

const catalogResponse = {
  items: [
    { id: "ds-1", name: "events", owner: "data-team", classification: "INTERNAL", description: "raw events", score: 1.0, source: "postgresql" },
  ],
  total: 1,
  source: "postgresql",
  stale: false,
};

function installApiMock(overrides: Record<string, unknown> = {}, permissions: string[] = []) {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    whoami: vi.fn().mockResolvedValue({ permissions, user: { id: "u1", email: "u@c.io", username: "u" } }),
    dataDatasets: vi.fn().mockResolvedValue(datasetsResponse),
    dataDataset: vi.fn().mockResolvedValue(datasetDetail),
    dataDatasetCreate: vi.fn().mockResolvedValue({ id: "ds-3", name: "metrics", status: "DRAFT", classification: "INTERNAL" }),
    dataDatasetVersion: vi.fn().mockResolvedValue({ id: "v-1", version: "2.0", schema_version: "1.1" }),
    dataDatasetArchive: vi.fn().mockResolvedValue({ id: "ds-2", status: "ARCHIVED" }),
    dataSources: vi.fn().mockResolvedValue(sourcesResponse),
    dataSourceCreate: vi.fn().mockResolvedValue({ id: "src-2", name: "api-feed", connector: "api", status: "ACTIVE" }),
    dataSchemas: vi.fn().mockResolvedValue(schemasResponse),
    dataSchemaCreate: vi.fn().mockResolvedValue({ id: "sch-2", version: "1.0", fields: [] }),
    dataSchemaEvolve: vi.fn().mockResolvedValue({ id: "sch-1", version: "1.1" }),
    dataPipelines: vi.fn().mockResolvedValue(pipelinesResponse),
    dataPipelineCreate: vi.fn().mockResolvedValue({ id: "pipe-2", name: "hourly", status: "DRAFT", dag_hash: "abc" }),
    dataPipelineRun: vi.fn().mockResolvedValue({ run_id: "run-new-1", status: "RUNNING", idempotency_key: "k" }),
    dataPipelineRunComplete: vi.fn().mockResolvedValue({ run_id: "run-new-1", status: "SUCCESS", duration_ms: 1200 }),
    dataPipelineBackfill: vi.fn().mockResolvedValue({ run_id: "run-bf-1", status: "RUNNING", scope: {}, time_range: {} }),
    dataJobs: vi.fn().mockResolvedValue(jobsResponse),
    dataQualityRuleCreate: vi.fn().mockResolvedValue({ id: "rule-2", name: "email-required", version: "1.0" }),
    dataQualityJobRun: vi.fn().mockResolvedValue({ results: [{ rule_id: "rule-1", passed: 10, failed: 0 }] }),
    dataQualityResults: vi.fn().mockResolvedValue(qualityResults),
    dataQualityProfile: vi.fn().mockResolvedValue({ row_count: 100, null_rate: { email: 0.05 }, distinct_count: { email: 95 }, min_max: {} }),
    dataLineageCreate: vi.fn().mockResolvedValue({ id: "e-1", source: "source:src-1", target: "dataset:ds-1" }),
    dataLineageGraph: vi.fn().mockResolvedValue(lineageGraph),
    dataCatalogSearchFull: vi.fn().mockResolvedValue(catalogResponse),
    dataCatalogSnapshot: vi.fn().mockResolvedValue({ snapshot: "data/catalog_snapshot/t1.json", tenant: "t1" }),
    dataStreamCreate: vi.fn().mockResolvedValue({ id: "st-1", topic: "events", partition: 0 }),
    dataStreamIngest: vi.fn().mockResolvedValue({ event_id: "ev-1", topic: "events", partition: 0, idempotency_key: "k" }),
    dataStreamLag: vi.fn().mockResolvedValue({ topic: "events", consumer: "etl", lag: 42 }),
    dataStreamConsume: vi.fn().mockResolvedValue({ items: [{ event_id: "ev-1", topic: "events", partition: 0, offset: 7 }] }),
    dataLakehouseTierWrite: vi.fn().mockResolvedValue({ tier: "raw", records: 2, format: "json", dataset_id: "ds-1" }),
    dataLakehouseStats: vi.fn().mockResolvedValue({
      stats: { raw: { exists: true, row_count: 100 }, validated: { exists: false, row_count: 0 } },
      optimizations: [{ action: "none", reason: "no fragmentation" }],
    }),
  };
  Object.assign(api, defaults, overrides);
}

describe("DataPlatformWorkspace (C1)", () => {
  beforeEach(() => {
    installApiMock();
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders the honest realtime badge and read-only notice without data:write", async () => {
    installApiMock({}, []);
    render(<DataPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.getByText("Read-only view · no data:write")).toBeTruthy();
  });

  it("labels overview figures as listed counts, never totals", async () => {
    installApiMock({}, ["data:write"]);
    render(<DataPlatformWorkspace />);
    expect(await screen.findByText("Datasets listed")).toBeTruthy();
    expect(screen.getByText("Listed count only — the backend reports no totals.")).toBeTruthy();
    expect(screen.getByText("Mutation actions enabled")).toBeTruthy();
  });

  it("renders datasets and shows detail on selection", async () => {
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Datasets" }));
    expect(await screen.findByText("events")).toBeTruthy();
    fireEvent.click(screen.getByText("events"));
    await waitFor(() => {
      expect(apiModule.api.dataDataset).toHaveBeenCalledWith("test-token", "ds-1");
    });
    expect(await screen.findByText("s3://lake/raw")).toBeTruthy();
  });

  it("hides dataset mutations without data:write", async () => {
    installApiMock({}, []);
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Datasets" }));
    expect(await screen.findByText("events")).toBeTruthy();
    expect(screen.queryByText("New dataset")).toBeNull();
  });

  it("creates a dataset then refetches authoritatively", async () => {
    installApiMock({}, ["data:write"]);
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Datasets" }));
    fireEvent.click(await screen.findByText("New dataset"));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "metrics" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await waitFor(() => {
      expect(api.dataDatasetCreate).toHaveBeenCalledWith("test-token", expect.objectContaining({ name: "metrics" }));
    });
    await waitFor(() => {
      expect((api.dataDatasets as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(1);
    });
  });

  it("renders pipelines with verbatim run statuses and starts runs", async () => {
    installApiMock({}, ["data:write"]);
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Pipelines" }));
    expect(await screen.findByText("nightly-sync")).toBeTruthy();
    fireEvent.click(screen.getByText("nightly-sync"));
    await waitFor(() => {
      expect(apiModule.api.dataJobs).toHaveBeenCalled();
    });
    expect(await screen.findByText("SUCCESS")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Start run" }));
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    await waitFor(() => {
      expect(apiModule.api.dataPipelineRun).toHaveBeenCalledWith("test-token", "pipe-1", {});
    });
  });

  it("renders quality results with passed/failed counts and no scores", async () => {
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Quality" }));
    fireEvent.change(screen.getByLabelText("Dataset ID"), { target: { value: "ds-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Load results" }));
    await waitFor(() => {
      expect(apiModule.api.dataQualityResults).toHaveBeenCalledWith("test-token", "ds-1");
    });
    expect(await screen.findByText(/passed 95 · failed 5/)).toBeTruthy();
    // No fabricated score values anywhere — only backend passed/failed counts
    expect(screen.queryByText(/score[:=]\s*\d/i)).toBeNull();
    expect(screen.queryByText(/\d+%\s*(healthy|quality|health)/i)).toBeNull();
  });

  it("traverses lineage with the backend depth bound", async () => {
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Lineage" }));
    fireEvent.change(screen.getByLabelText("Node"), { target: { value: "dataset:ds-1" } });
    fireEvent.click(screen.getByRole("button", { name: "Traverse" }));
    await waitFor(() => {
      expect(apiModule.api.dataLineageGraph).toHaveBeenCalledWith("test-token", "dataset:ds-1", 3);
    });
    expect(await screen.findByText("source:src-1 → dataset:ds-1")).toBeTruthy();
  });

  it("searches the catalog with modes and labels stale snapshots read-only", async () => {
    installApiMock({
      dataCatalogSearchFull: vi.fn().mockResolvedValue({ ...catalogResponse, stale: true, warning: "READ-ONLY stale, no privileged actions" }),
    });
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Catalog" }));
    fireEvent.change(screen.getByLabelText("Query"), { target: { value: "events" } });
    fireEvent.click(screen.getByLabelText("Semantic (Qdrant)"));
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      expect(apiModule.api.dataCatalogSearchFull).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({ q: "events", semantic: true }),
      );
    });
    expect(await screen.findByText("READ-ONLY stale — no privileged actions")).toBeTruthy();
  });

  it("reports stream lag verbatim from the backend", async () => {
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Streams" }));
    fireEvent.change(screen.getByLabelText("Topic"), { target: { value: "events" } });
    fireEvent.change(screen.getByLabelText("Consumer"), { target: { value: "etl" } });
    fireEvent.click(screen.getByRole("button", { name: "Lag" }));
    await waitFor(() => {
      expect(apiModule.api.dataStreamLag).toHaveBeenCalledWith("test-token", "events", "etl");
    });
    expect(await screen.findByText("42")).toBeTruthy();
  });

  it("labels lakehouse row counts as backend-reported", async () => {
    installApiMock({}, ["data:write"]);
    const { getByRole } = render(<DataPlatformWorkspace />);
    fireEvent.click(getByRole("tab", { name: "Datasets" }));
    expect(await screen.findByText("events")).toBeTruthy();
    fireEvent.click(screen.getByText("events"));
    fireEvent.click(getByRole("tab", { name: "Lakehouse" }));
    fireEvent.click(screen.getByRole("button", { name: "Load stats" }));
    await waitFor(() => {
      expect(apiModule.api.dataLakehouseStats).toHaveBeenCalledWith("test-token", "ds-1");
    });
    expect(await screen.findByText("present · 100 rows (reported)")).toBeTruthy();
  });

  it("refetches under the new scope on tenant switch without leaking state", async () => {
    render(<DataPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const callsBefore = (api.dataDatasets as ReturnType<typeof vi.fn>).mock.calls.length;
    expect(callsBefore).toBeGreaterThan(0);
    window.dispatchEvent(new CustomEvent("tenant:switched"));
    await waitFor(() => {
      expect((api.dataDatasets as ReturnType<typeof vi.fn>).mock.calls.length).toBeGreaterThan(callsBefore);
    });
  });

  it("renders no credentials, tokens or secrets anywhere", async () => {
    installApiMock({}, ["data:write"]);
    render(<DataPlatformWorkspace />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeTruthy();
    expect(screen.queryByText(/credential value/i)).toBeNull();
    expect(screen.queryByText(/api[_-]?key/i)).toBeNull();
    expect(screen.queryByText(/access_token/i)).toBeNull();
    expect(screen.queryByText(/password/i)).toBeNull();
  });
});
