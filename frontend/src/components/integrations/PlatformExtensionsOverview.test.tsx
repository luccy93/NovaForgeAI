import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { PlatformExtensionsOverview } from "@/components/integrations/PlatformExtensionsOverview";

const { filteredMock, connectionsMock, webhooksMock, policiesMock } = vi.hoisted(() => ({
  filteredMock: vi.fn(),
  connectionsMock: vi.fn(),
  webhooksMock: vi.fn(),
  policiesMock: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    api: {
      ...actual.api,
      integrationsFiltered: filteredMock,
      integrationConnections: connectionsMock,
      integrationWebhooks: webhooksMock,
      integrationPolicies: policiesMock,
    },
  };
});

describe("PlatformExtensionsOverview", () => {
  beforeEach(() => {
    filteredMock.mockResolvedValue({ items: [{ id: "int-1" }], total: 1 });
    connectionsMock.mockResolvedValue({ items: [{ id: "conn-1" }], total: 1 });
    webhooksMock.mockResolvedValue({ items: [], total: 0 });
    policiesMock.mockResolvedValue({ items: [{ id: "pol-1" }], total: 1 });
  });

  it("renders extension overview headings from real backend data", async () => {
    render(<PlatformExtensionsOverview />);
    expect(await screen.findByText("Integration Registry")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Connections" })).toBeInTheDocument();
    expect(screen.getByText("Webhooks & Sync")).toBeInTheDocument();
    expect(screen.getByText("Integration Policies")).toBeInTheDocument();
  });

  it("shows counts verbatim and not as zero when exposed", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Integration Registry");
    expect(screen.getAllByText("1").length).toBeGreaterThanOrEqual(1);
  });

  it("shows NOT EXPOSED BY API when backend returns null", async () => {
    filteredMock.mockResolvedValueOnce(null as unknown as never);
    connectionsMock.mockResolvedValueOnce(null as unknown as never);
    webhooksMock.mockResolvedValueOnce(null as unknown as never);
    policiesMock.mockResolvedValueOnce(null as unknown as never);
    render(<PlatformExtensionsOverview />);
    expect(await screen.findByText("Integration Registry")).toBeInTheDocument();
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(1);
  });

  it("shows realtime unavailable and no fake health", async () => {
    render(<PlatformExtensionsOverview />);
    expect(await screen.findByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Tenant-scoped · server-authoritative")).toBeInTheDocument();
    expect(screen.queryByText(/99\.99%/)).toBeNull();
    expect(screen.queryByText(/Healthy.*Connected/i)).toBeNull();
  });

  it("provides SDK/CLI/MCP handoffs to /docs and no external URLs", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Integration Registry");
    const sdkLink = screen.getByRole("link", { name: "View SDK Documentation" });
    const cliLink = screen.getByRole("link", { name: "CLI Documentation" });
    const mcpLink = screen.getByRole("link", { name: "View MCP Documentation" });
    expect(sdkLink).toHaveAttribute("href", "/docs");
    expect(cliLink).toHaveAttribute("href", "/docs");
    expect(mcpLink).toHaveAttribute("href", "/docs");
    const allLinks = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of allLinks) {
      expect(href.startsWith("/")).toBe(true);
      expect(href.includes("://")).toBe(false);
    }
  });

  it("never exposes secrets or credential material", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Integration Registry");
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("client_secret");
    expect(html).not.toContain("full_key");
    expect(html).not.toContain("access_token");
    expect(html).not.toContain("signing_secret");
    expect(html).not.toContain("bearer");
  });

  it("provides cross-domain handoffs to canonical routes", async () => {
    render(<PlatformExtensionsOverview />);
    await screen.findByText("Integration Registry");
    expect(screen.getAllByRole("link", { name: "Workflows" })[0]).toHaveAttribute("href", "/workflows");
    expect(screen.getAllByRole("link", { name: "Knowledge" })[0]).toHaveAttribute("href", "/knowledge");
  });
});
