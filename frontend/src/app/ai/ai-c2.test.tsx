import { render, screen, waitFor, fireEvent, cleanup } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { AiWorkspace } from "@/components/ai/AiWorkspace";
import { MessageBubble } from "@/components/ai/MessageBubble";
import { ConversationList } from "@/components/ai/ConversationList";
import * as apiModule from "@/lib/api";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ai",
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: {
      ...actual.api,
      me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
      listConversations: vi.fn().mockResolvedValue(
        Array.from({ length: 55 }, (_, i) => ({
          id: `c${i}`,
          title: `Conversation ${i}`,
          message_count: 2,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        })),
      ),
      getConversation: vi.fn().mockResolvedValue({
        id: "c0",
        title: "Conversation 0",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [
          { id: "m1", role: "user", content: "hello", created_at: new Date().toISOString() },
          { id: "m2", role: "assistant", content: "hi there **bold**", created_at: new Date().toISOString() },
        ],
      }),
      deleteConversation: vi.fn().mockResolvedValue(undefined),
      chat: vi.fn().mockResolvedValue({
        answer: "fallback",
        conversation_id: "c100",
        confidence: 0.9,
        model_used: "gpt-4o-mini",
        sources: [],
      }),
    },
    streamChatResponse: vi.fn(),
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

describe("C2: Intelligence and hardening", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  describe("Copy to clipboard", () => {
    it("shows a copy button on assistant messages", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hi there")).toBeInTheDocument());
      const copyButtons = screen.getAllByLabelText("Copy message");
      expect(copyButtons.length).toBeGreaterThan(0);
    });

    it("copy button calls clipboard API", async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);
      Object.assign(navigator, { clipboard: { writeText } });
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hi there")).toBeInTheDocument());
      const copyBtn = screen.getAllByLabelText("Copy message")[0];
      fireEvent.click(copyBtn);
      await waitFor(() => expect(writeText).toHaveBeenCalled());
    });
  });

  describe("Pagination", () => {
    it("shows Load more when there are 50+ conversations", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      expect(screen.getByRole("button", { name: /load more/i })).toBeInTheDocument();
    });

    it("loads more conversations when Load more is clicked", async () => {
      const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByRole("button", { name: /load more/i }));
      await waitFor(() => {
        // Initial call + append call = 2
        expect(mocked.listConversations).toHaveBeenCalledTimes(2);
      });
    });
  });

  describe("Accessibility", () => {
    it("message timeline has role=log and aria-live", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
      const log = screen.getByRole("log");
      expect(log).toHaveAttribute("aria-label", "Conversation messages");
    });

    it("composer has aria-label", () => {
      render(<AiWorkspace />);
      expect(screen.getByLabelText("Message composer")).toBeInTheDocument();
    });

    it("conversation list has accessible label", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByLabelText("Conversation history")).toBeInTheDocument());
    });

    it("each message has an article role", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
      const articles = screen.getAllByRole("article");
      expect(articles.length).toBeGreaterThan(0);
    });
  });

  describe("Security", () => {
    it("markdown does not render raw HTML (XSS safety)", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
      // No script/iframe/object tags in the DOM
      expect(document.querySelector("script")).toBeNull();
      expect(document.querySelector("iframe")).toBeNull();
      expect(document.querySelector("object")).toBeNull();
    });

    it("MessageBubble renders markdown safely", () => {
      const msg = { id: "x1", role: "assistant" as const, content: "<script>alert('xss')</script>hello" };
      render(<MessageBubble message={msg} />);
      expect(document.querySelector("script")).toBeNull();
      expect(screen.getByText(/hello/)).toBeInTheDocument();
    });

    it("User messages are rendered as plain text (no markdown)", async () => {
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByText("Conversation 0")).toBeInTheDocument());
      fireEvent.click(screen.getByText("Conversation 0"));
      await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
  });

  describe("StreamingIndicator", () => {
    it("shows typing dots while waiting for first chunk", async () => {
      const { StreamingIndicator } = await import("@/components/ai/StreamingIndicator");
      render(<StreamingIndicator />);
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  describe("Context panel", () => {
    it("shows streamedWithoutMetadata when no metadata available after stream", async () => {
      const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
      (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
        yield { type: "chunk", content: "answer" };
        yield { type: "done", conversation_id: "c-streamed" };
      });
      render(<AiWorkspace />);
      await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
      const textarea = screen.getByLabelText("Message composer");
      fireEvent.change(textarea, { target: { value: "q?" } });
      fireEvent.keyDown(textarea, { key: "Enter" });
      await waitFor(() => expect(screen.getByText("answer")).toBeInTheDocument());
      // After stream: honest "No metadata for streamed reply" shown in context panel
      await waitFor(() =>
        expect(screen.getByText("No metadata for this reply")).toBeInTheDocument(),
      );
    });
  });
});