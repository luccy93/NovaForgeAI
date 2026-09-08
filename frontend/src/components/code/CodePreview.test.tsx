import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { CodePreview } from "@/components/code/CodePreview";
import { highlightCode, detectLanguage } from "@/lib/highlight";

vi.mock("@/lib/highlight", () => ({
  detectLanguage: vi.fn().mockReturnValue("python"),
  isLanguageSupported: vi.fn().mockReturnValue(true),
  highlightCode: vi.fn().mockImplementation(async (code: string) => ({
    lines: code.split("\n").map((line) => ({
      tokens: line
        .split(/([^A-Za-z0-9_]+)/)
        .filter(Boolean)
        .map((chunk) => ({
          content: chunk,
          color: chunk === "parse_amount" ? "rgb(121, 192, 255)" : null,
        })),
    })),
    highlighted: true,
    backgroundColor: null,
    foregroundColor: null,
  })),
  __resetHighlightMemo: vi.fn(),
}));

describe("CodePreview", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders highlighted tokens as text spans, never as HTML", async () => {
    const { container } = render(
      <CodePreview code={'def parse_amount(raw):\n    return int(raw)'} filePath="x/y.py" />,
    );
    await waitFor(() => expect(screen.getByText("parse_amount")).toBeInTheDocument());
    const colored = Array.from(container.querySelectorAll("span")).find(
      (el) => el.textContent === "parse_amount",
    );
    expect(colored).toBeTruthy();
    expect((colored as HTMLElement).style.color).toBe("rgb(121, 192, 255)");
    expect(detectLanguage).toHaveBeenCalledWith("x/y.py", null);
  });

  it("renders a plain fallback for unknown languages without color styling", async () => {
    (highlightCode as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      lines: [{ tokens: [{ content: "line one", color: null }] }],
      highlighted: false,
      backgroundColor: null,
      foregroundColor: null,
    });
    const { container } = render(<CodePreview code="line one" />);
    await waitFor(() => expect(screen.getByText("line one")).toBeInTheDocument());
    expect(container.querySelector("[style]")).toBeNull();
    expect(screen.getByText("line one").textContent).toBe("line one");
  });

  it("bounds the snippet to maxLines", async () => {
    render(<CodePreview code={"a\nb\nc\nd\ne"} maxLines={2} />);
    await waitFor(() => expect(screen.getByText("a")).toBeInTheDocument());
    expect(screen.queryByText("c")).not.toBeInTheDocument();
    // Gutter shows only the first two line numbers (startLine 1 + offset)
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("shifts the gutter by startLine", async () => {
    render(<CodePreview code={"x\ny"} startLine={40} />);
    await waitFor(() => expect(screen.getByText("x")).toBeInTheDocument());
    expect(screen.getByText("40")).toBeInTheDocument();
    expect(screen.getByText("41")).toBeInTheDocument();
  });

  it("escapes script-like snippet content instead of executing it", async () => {
    (highlightCode as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      lines: [{ tokens: [{ content: '<script>alert("x")</script>', color: null }] }],
      highlighted: false,
      backgroundColor: null,
      foregroundColor: null,
    });
    const { container } = render(<CodePreview code={'<script>alert("x")</script>'} />);
    await waitFor(() =>
      expect(screen.getByText('<script>alert("x")</script>')).toBeInTheDocument(),
    );
    expect(container.querySelector("script")).toBeNull();
  });
});