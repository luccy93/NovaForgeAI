import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import DocsPage from "@/app/docs/page";

describe("DocsPage developer resources", () => {
  it("renders SDK, CLI, MCP handoffs to /docs and no external URLs", () => {
    render(<DocsPage />);
    expect(screen.getByText("Developer SDK")).toBeInTheDocument();
    expect(screen.getByText("NovaForge CLI")).toBeInTheDocument();
    expect(screen.getByText("MCP Servers")).toBeInTheDocument();
    const docsLinks = Array.from(document.querySelectorAll("a")).filter((a) => a.getAttribute("href") === "/docs");
    expect(docsLinks.length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("NOT EXPOSED")).toBeInTheDocument();
    for (const a of docsLinks) {
      expect(a.getAttribute("href")).toBe("/docs");
    }
  });

  it("does not create /sdk, /cli, /mcp routes", () => {
    render(<DocsPage />);
    const links = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    expect(links).not.toContain("/sdk");
    expect(links).not.toContain("/cli");
    expect(links).not.toContain("/mcp");
    for (const href of links) {
      expect(href.includes("://")).toBe(false);
      if (href.startsWith("/") && href !== "#") {
        expect(href.startsWith("//")).toBe(false);
      }
    }
  });
});
