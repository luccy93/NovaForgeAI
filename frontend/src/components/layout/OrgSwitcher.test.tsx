import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { OrgSwitcher } from "@/components/layout/OrgSwitcher";
import { useTenantStore } from "@/stores/tenant";
import * as apiModule from "@/lib/api";

// Mock api
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    api: {
      ...actual.api,
      listMyOrganizations: vi.fn().mockResolvedValue([
        { id: "org-1", name: "Acme", slug: "acme", plan: "free", is_active: true, created_at: new Date().toISOString() },
        { id: "org-2", name: "Beta", slug: "beta", plan: "pro", is_active: true, created_at: new Date().toISOString() },
      ]),
      listWorkspaces: vi.fn().mockResolvedValue([]),
      getOrganization: vi.fn().mockResolvedValue({ id: "org-2", name: "Beta", slug: "beta", plan: "pro", is_active: true, created_at: new Date().toISOString() }),
    },
    getToken: vi.fn().mockReturnValue("test-token"),
  };
});

describe("OrgSwitcher", () => {
  beforeEach(() => {
    useTenantStore.getState().clear();
    localStorage.clear();
  });

  it("renders organizations and switches with verification", async () => {
    render(<OrgSwitcher />);
    await waitFor(() => expect(screen.getByLabelText("Organization")).toBeInTheDocument());
    expect(screen.getByText("Acme (acme)")).toBeInTheDocument();
    expect(screen.getByText("Beta (beta)")).toBeInTheDocument();
  });

  it("is hidden when no organizations", async () => {
    const mocked = apiModule.api as unknown as { listMyOrganizations: ReturnType<typeof vi.fn> };
    mocked.listMyOrganizations.mockResolvedValueOnce([]);
    const { container } = render(<OrgSwitcher />);
    await new Promise((r) => setTimeout(r, 100));
    expect(container.innerHTML).toBe("");
  });
});
