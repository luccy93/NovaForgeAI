import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(join(__dirname, "..", "app", "globals.css"), "utf-8");

describe("design tokens", () => {
  it.each([
    "--color-surface: #0A0A0A",
    "--color-primary: #FFED00",
    "--color-error: #FF6B6B",
    "--color-outline: #333333",
    '"Space Grotesk"',
    '"JetBrains Mono"',
    "--z-dialog: 80",
    "--motion-base: 180ms",
  ])("defines %s", (token) => {
    expect(css).toContain(token);
  });

  it("keeps reduced-motion support", () => {
    expect(css).toContain("prefers-reduced-motion");
  });
});
