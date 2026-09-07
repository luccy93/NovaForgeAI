import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { QUICK_ACTIONS } from "@/components/dashboard/QuickActions";

describe("QuickActions route capability", () => {
  it("only exposes actions whose destination routes exist", () => {
    // Every rendered action must point to a real route. No placeholders,
    // no future-module routes, no 404 navigation.
    const realRoutes = new Set<string>([
      "/dashboard",
      "/ai-kit",
      // Future modules (/workflows, /integrations, /security, /governance)
      // intentionally omitted until they exist.
    ]);
    for (const action of QUICK_ACTIONS) {
      const base = action.href.split("#")[0];
      expect(realRoutes.has(base), `action ${action.id} must point to a real route`).toBe(true);
    }
  });

  it("does not link to non-existent module routes", () => {
    for (const action of QUICK_ACTIONS) {
      expect(action.href.startsWith("/workflows")).toBe(false);
      expect(action.href.startsWith("/integrations")).toBe(false);
      expect(action.href.startsWith("/security")).toBe(false);
      expect(action.href.startsWith("/governance")).toBe(false);
    }
  });

  it("renders the real quick actions with accessible labels", () => {
    render(
      <div>
        {QUICK_ACTIONS.map((action) => (
          <a key={action.id} href={action.href}>
            {action.label}
          </a>
        ))}
      </div>,
    );
    expect(screen.getByRole("link", { name: /search knowledge/i })).toHaveAttribute("href", "/dashboard#knowledge");
    expect(screen.getByRole("link", { name: /open ai/i })).toHaveAttribute("href", "/ai-kit");
  });
});