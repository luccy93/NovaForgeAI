import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DeveloperPlatformOverview } from "@/components/developer/DeveloperPlatformOverview";

describe("DeveloperPage handoffs", () => {
  it("renders SDK, CLI, MCP handoffs to /docs and no external URLs", () => {
    render(<DeveloperPlatformOverview />);
    expect(screen.getByRole("heading", { name: "Developer Platform" })).toBeInTheDocument();
    const docsLinks = Array.from(document.querySelectorAll("a"))
      .map((a) => a.getAttribute("href"))
      .filter((h) => h === "/docs");
    expect(docsLinks.length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText("NOT EXPOSED BY API").length).toBeGreaterThanOrEqual(2);
  });

  it("does not create /sdk, /cli, /mcp routes and keeps all handoffs internal", () => {
    render(<DeveloperPlatformOverview />);
    const hrefs = Array.from(document.querySelectorAll("a")).map((a) => a.getAttribute("href") || "");
    for (const href of hrefs) {
      if (href.startsWith("/") && href !== "#") {
        expect(href.startsWith("//")).toBe(false);
        expect(href.includes("://")).toBe(false);
        expect(["/sdk", "/cli", "/mcp", "/developer/docs"].includes(href)).toBe(false);
      }
    }
    expect(hrefs).toContain("/settings/security");
    expect(hrefs).toContain("/integrations");
    expect(hrefs).toContain("/code");
  });
});
