import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DeveloperPlatformOverview } from "@/components/developer/DeveloperPlatformOverview";

describe("DeveloperPlatformOverview", () => {
  it("renders developer overview headings from verified handoffs", () => {
    render(<DeveloperPlatformOverview />);
    expect(screen.getByRole("heading", { name: "Developer Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API Access" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API Reference" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SDK" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "CLI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "MCP Servers" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API Playground" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Webhooks" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Code Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "AI Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Agents" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Unavailable Capabilities" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Documentation" })).toBeInTheDocument();
  });

  it("provides SDK/CLI/MCP handoffs to /docs and no external URLs", () => {
    render(<DeveloperPlatformOverview />);
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
      expect(href.startsWith("//")).toBe(false);
    }
  });

  it("does not create /sdk, /cli, /mcp routes", () => {
    render(<DeveloperPlatformOverview />);
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of hrefs) {
      if (href.startsWith("/") && href !== "#") {
        expect(href).not.toBe("/sdk");
        expect(href).not.toBe("/cli");
        expect(href).not.toBe("/mcp");
        expect(href).not.toBe("/developer/docs");
        expect(href.startsWith("/sdk")).toBe(false);
        expect(href.startsWith("/cli")).toBe(false);
        expect(href.startsWith("/mcp")).toBe(false);
      }
    }
  });

  it("provides canonical handoffs to verified routes", () => {
    render(<DeveloperPlatformOverview />);
    expect(screen.getByRole("link", { name: "Manage API Keys" })).toHaveAttribute("href", "/settings/security");
    expect(screen.getAllByRole("link", { name: "View Documentation" })[0]).toHaveAttribute("href", "/docs");
    expect(screen.getByRole("link", { name: "Manage Webhooks" })).toHaveAttribute("href", "/integrations");
    expect(screen.getByRole("link", { name: "Open Code Platform" })).toHaveAttribute("href", "/code");
    expect(screen.getByRole("link", { name: "Open AI Platform" })).toHaveAttribute("href", "/ai");
    const agentsLinks = screen.getAllByRole("link", { name: "Open Agents" });
    expect(agentsLinks[0]).toHaveAttribute("href", "/agents");
  });

  it("marks unavailable surfaces as NOT EXPOSED BY API and never fabricates metrics", () => {
    render(<DeveloperPlatformOverview />);
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(3);
    expect(screen.queryByText(/99\.9\s*%/)).toBeNull();
    expect(screen.queryByText(/uptime\s*[:=]/i)).toBeNull();
    expect(screen.getByText("Realtime: UNAVAILABLE")).toBeInTheDocument();
    expect(screen.getByText("Tenant-scoped · server-authoritative")).toBeInTheDocument();
  });

  it("never exposes secrets or credential material", () => {
    render(<DeveloperPlatformOverview />);
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("client_secret");
    expect(html).not.toContain("full_key");
    expect(html).not.toContain("access_token");
    expect(html).not.toContain("signing_secret");
    // header names and explanatory text are allowed; only actual secret material is forbidden
    expect(html).not.toMatch(/nf_[a-z0-9]{20,}/);
    expect(html).not.toContain("sk-");
  });

  it("keeps all platform navigation handoffs internal", () => {
    render(<DeveloperPlatformOverview />);
    const needed = ["/developer", "/docs", "/integrations", "/code", "/ai", "/agents", "/knowledge", "/command"];
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const path of needed) {
      expect(hrefs).toContain(path);
    }
    for (const href of hrefs) {
      expect(href).not.toMatch(/^https?:/);
    }
  });

  it("does not retain stale state after tenant or workspace switch", () => {
    render(<DeveloperPlatformOverview />);
    expect(screen.getByRole("heading", { name: "Developer Platform" })).toBeInTheDocument();
    window.dispatchEvent(new Event("tenant:switched"));
    expect(screen.getByRole("heading", { name: "Developer Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "SDK" })).toBeInTheDocument();
    window.dispatchEvent(new Event("workspace:switched"));
    expect(screen.getByRole("heading", { name: "Developer Platform" })).toBeInTheDocument();
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(3);
  });
});
