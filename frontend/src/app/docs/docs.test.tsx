import { fireEvent, render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import DocsPage from "@/app/docs/page";

describe("DocsPage canonical documentation", () => {
  it("renders NovaForge Documentation home with search", () => {
    render(<DocsPage />);
    expect(screen.getAllByText("NovaForge Documentation").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText("Search documentation")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search docs, APIs, guides...")).toBeInTheDocument();
  });

  it("filters documentation search over verified content and shows no-results state", () => {
    render(<DocsPage />);
    const input = screen.getByLabelText("Search documentation") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "SDK" } });
    expect(screen.getByText(/result.*for "SDK"/i)).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "zzzznonexistent" } });
    expect(screen.getByText("No documentation matches")).toBeInTheDocument();
  });

  it("renders SDK, CLI, MCP handoffs to /docs and no external URLs", () => {
    render(<DocsPage />);
    expect(screen.getByRole("heading", { name: "SDK" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "CLI" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "MCP" })).toBeInTheDocument();
    const docsLinks = Array.from(document.querySelectorAll("a")).filter((a) => a.getAttribute("href") === "/docs");
    expect(docsLinks.length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(1);
  });

  it("does not create /sdk, /cli, /mcp routes and keeps links internal", () => {
    render(<DocsPage />);
    const links = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    expect(links).not.toContain("/sdk");
    expect(links).not.toContain("/cli");
    expect(links).not.toContain("/mcp");
    expect(links).not.toContain("/api-docs");
    for (const href of links) {
      if (href.startsWith("/") && href !== "#") {
        expect(href.includes("://")).toBe(false);
        expect(href.startsWith("//")).toBe(false);
      }
    }
  });

  it("documents verified platform routes and help surfaces", () => {
    render(<DocsPage />);
    expect(screen.getByRole("heading", { name: "Platform" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Operations" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "FAQ" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Troubleshooting" })).toBeInTheDocument();
    expect(screen.getByText("Where are API keys managed?")).toBeInTheDocument();
    expect(screen.getByText("SESSION EXPIRED (401)")).toBeInTheDocument();
  });

  it("exposes no secrets and no fake metrics", () => {
    render(<DocsPage />);
    const html = document.body.innerHTML.toLowerCase();
    expect(html).not.toContain("client_secret");
    expect(html).not.toContain("sk-");
    expect(html).not.toMatch(/nf_[a-z0-9]{20,}/);
    expect(screen.queryByText(/12,453 developers/i)).toBeNull();
    expect(screen.queryByText(/Trending/i)).toBeNull();
  });
});
