import { render, screen, waitFor, fireEvent, cleanup, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { KnowledgeGraph } from "@/components/knowledge/KnowledgeGraph";
import * as apiModule from "@/lib/api";
import { ApiError } from "@/lib/api-client";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/knowledge/graph",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: { ...actual.api },
  };
});

vi.mock("@/components/auth/Protected", async () => {
  const actual = await vi.importActual<typeof import("@/components/auth/Protected")>(
    "@/components/auth/Protected",
  );
  return {
    ...actual,
    Protected: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

interface EntityFixture {
  entity_id: string;
  name: string;
  entity_type: string;
  description: string;
  classification: string;
  confidence: number;
}

function entity(id: string, name: string, entity_type: string): EntityFixture {
  return {
    entity_id: id,
    name,
    entity_type,
    description: "",
    classification: "INTERNAL",
    confidence: 0.87,
  };
}

const entities: EntityFixture[] = [
  entity("e1", "Payments Service", "service"),
  entity("e2", "Devendra Prasad", "person"),
  entity("e3", "acme/catalog", "repository"),
];

const detailBase = entities.find((e) => e.entity_id === "e2")!;

const details: Record<string, unknown> = {
  e1: { ...entities[0], links: [{ link_id: "l1", source_entity_id: "e1", target_entity_id: "e2", link_type: "owns" }] },
  e2: { ...detailBase, links: [{ link_id: "l1", source_entity_id: "e1", target_entity_id: "e2", link_type: "owns" }] },
  e3: { ...entities[2], links: [] },
};

function installApiMock() {
  const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
  const defaults: Record<string, ReturnType<typeof vi.fn>> = {
    knowledgeListEntities: vi.fn().mockResolvedValue({ items: entities, total: entities.length }),
    knowledgeGetEntity: vi.fn().mockImplementation((_token: string, id: string) =>
      Promise.resolve(details[id] ?? { ...entity(id, id, "concept"), links: [] }),
    ),
  };
  for (const [key, value] of Object.entries(defaults)) {
    api[key] = value;
  }
  return api;
}

describe("Knowledge Graph", () => {
  beforeEach(() => {
    installApiMock();
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("loads real entities from the Knowledge API on mount", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    expect(api.knowledgeListEntities).toHaveBeenCalledWith("test-token", { limit: 100 });
  });

  it("fetches entity details only for the bounded head, never the whole list", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const many = Array.from({ length: 30 }, (_, i) =>
      entity(`e${i}`, `Entity ${i}`, ["person", "service", "repository", "dataset"][i % 4]),
    );
    api.knowledgeListEntities.mockResolvedValue({ items: many, total: many.length });
    render(<KnowledgeGraph />);
    await waitFor(() => expect(api.knowledgeGetEntity).toHaveBeenCalledTimes(25));
    expect(api.knowledgeGetEntity).not.toHaveBeenCalledWith("test-token", "e25");
  });

  it("renders the graph from real edges returned by the detail API", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("img", { name: /Knowledge graph of real entities/ })).toBeInTheDocument();
  });

  it("shows list view with every entity", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("View"), { target: { value: "list" } });
    expect(screen.getByText("Payments Service")).toBeInTheDocument();
    expect(screen.getByText("Devendra Prasad")).toBeInTheDocument();
    expect(screen.getByText("acme/catalog")).toBeInTheDocument();
    expect(screen.getByText("service")).toBeInTheDocument();
  });

  it("shows real link metadata in the detail panel when an entity is selected", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
    fireEvent.change(screen.getByLabelText("View"), { target: { value: "list" } });
    fireEvent.click(screen.getByText("Payments Service"));
    await waitFor(() => expect(screen.getByText("Links (1)")).toBeInTheDocument());
    expect(screen.getByText("owns → e2")).toBeInTheDocument();
  });

  it("shows an honest state when the API returns no entities", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeListEntities.mockResolvedValue({ items: [], total: 0 });
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText("No entities in this workspace")).toBeInTheDocument(),
    );
  });

  it("surfaces lists errors with a working retry", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    api.knowledgeListEntities
      .mockRejectedValueOnce(new ApiError("server", 500, "graph service down"))
      .mockResolvedValue({ items: entities, total: entities.length });
    render(<KnowledgeGraph />);
    await waitFor(() => expect(screen.getByText("Knowledge graph unavailable")).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
  });

  it("states, honestly, that no graph can be drawn without real edges", async () => {
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const lonely = [entity("e1", "Payments Service", "service")];
    api.knowledgeListEntities.mockResolvedValue({ items: lonely, total: lonely.length });
    api.knowledgeGetEntity.mockResolvedValue({ ...lonely[0], links: [] });
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/backend returned no entity links/)).toBeInTheDocument(),
    );
    expect(screen.getByText(/1 entities · 0 real edges/)).toBeInTheDocument();
  });

  it("reloads from the API on tenant switch instead of reusing stale data", async () => {
    render(<KnowledgeGraph />);
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
    const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    await act(async () => {
      window.dispatchEvent(new Event("tenant:switched"));
    });
    await waitFor(() => expect(api.knowledgeListEntities).toHaveBeenCalledTimes(2));
    await waitFor(() =>
      expect(screen.getByText(/3 entities · 1 real edges/)).toBeInTheDocument(),
    );
  });

  it("escalates a 401 to a login redirect", async () => {
    const fakeLocation = { href: "", pathname: "/knowledge/graph", search: "" };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      const api = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      api.knowledgeListEntities.mockRejectedValue(new ApiError("unauthorized", 401, "expired"));
      render(<KnowledgeGraph />);
      await waitFor(() => expect(apiModule.clearToken).toHaveBeenCalled());
      expect(fakeLocation.href).toBe("/auth/login");
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });
});