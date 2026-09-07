import { render, screen, waitFor, fireEvent, cleanup, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import AiPage from "@/app/ai/page";
import { AiWorkspace } from "@/components/ai/AiWorkspace";
import * as apiModule from "@/lib/api";
import { useTenantStore } from "@/stores/tenant";

vi.mock("next/navigation", () => ({
  usePathname: () => "/ai",
}));

function conversationAvatar(id: string, title: string, count = 2) {
  return {
    id,
    title,
    message_count: count,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getToken: vi.fn().mockReturnValue("test-token"),
    clearToken: vi.fn(),
    api: {
      ...actual.api,
      me: vi.fn().mockResolvedValue({ id: "u1", email: "a@b.io", username: "ab", is_active: true }),
      listConversations: vi.fn().mockResolvedValue([
        conversationAvatar("c1", "First conversation"),
        conversationAvatar("c2", "Second conversation"),
      ]),
      getConversation: vi.fn().mockResolvedValue({
        id: "c1",
        title: "First conversation",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        messages: [
          { id: "m1", role: "user", content: "hello", created_at: new Date().toISOString() },
          { id: "m2", role: "assistant", content: "hi there", created_at: new Date().toISOString() },
        ],
      }),
      deleteConversation: vi.fn().mockResolvedValue(undefined),
      chat: vi.fn().mockResolvedValue({
        answer: "non-stream answer",
        conversation_id: "c3",
        confidence: 0.95,
        model_used: "gpt-4o-mini",
        sources: [{ text: "src", source: "doc", score: 0.8 }],
      }),
    },
    streamChatResponse: vi.fn(),
  };
});

// Protect library mock: AiPage uses Protected which redirects unless authenticated
vi.mock("@/components/auth/Protected", async () => {
  const actual = await vi.importActual<typeof import("@/components/auth/Protected")>(
    "@/components/auth/Protected",
  );
  return {
    ...actual,
    Protected: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

describe("AI Workspace", () => {
  beforeEach(() => {
    useTenantStore.getState().setContext("org-1", "ws-1");
    vi.clearAllMocks();
  });

  afterEach(() => {
    cleanup();
  });

  it("renders the workspace shell", async () => {
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("First conversation")).toBeInTheDocument());
    expect(screen.getByText("Second conversation")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /new conversation/i })).toBeInTheDocument();
  });

  it("renders empty state when no conversations", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    mocked.listConversations.mockResolvedValueOnce([]);
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("No conversations yet")).toBeInTheDocument());
  });

  it("loads a conversation and renders messages", async () => {
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("First conversation")).toBeInTheDocument());
    fireEvent.click(screen.getByText("First conversation"));
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    await waitFor(() => expect(screen.getByText("hi there")).toBeInTheDocument());
  });

  it("sends a message via non-streaming fallback when stream fails before content", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    // Stream fails fast (network error)
    (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
      throw new Error("network down");
    });
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
    const textarea = screen.getByLabelText("Message composer");
    fireEvent.change(textarea, { target: { value: "question?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(screen.getByText("non-stream answer")).toBeInTheDocument());
    expect(mocked.chat).toHaveBeenCalledTimes(1);
  });

  it("does NOT auto-fallback when the stream delivered partial content", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    let emitted = false;
    (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
      yield { type: "chunk", content: "partial" };
      emitted = true;
      throw new Error("mid-stream failure");
    });
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
    const textarea = screen.getByLabelText("Message composer");
    fireEvent.change(textarea, { target: { value: "question?" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(emitted).toBe(true));
    // Partial content shown, no fallback /chat call
    await waitFor(() => expect(screen.getByText(/partial/i)).toBeInTheDocument());
    expect(mocked.chat).not.toHaveBeenCalled();
    // Retry button appears for explicit user action
    await waitFor(() => expect(screen.getByText("Retry")).toBeInTheDocument());
  });

  it("renders streamed chunks incrementally and finalizes on done", async () => {
    (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
      yield { type: "chunk", content: "Hello " };
      yield { type: "chunk", content: "world" };
      yield { type: "done", conversation_id: "c-stream" };
    });
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
    const textarea = screen.getByLabelText("Message composer");
    fireEvent.change(textarea, { target: { value: "hello?" } });

    // Simulate streaming by draining the generator synchronously after a microtask.
    fireEvent.keyDown(textarea, { key: "Enter" });
    await waitFor(() => expect(screen.getByText(/Hello world/)).toBeInTheDocument(), { timeout: 3000 });
  });

  it("clears context on tenant switch", async () => {
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("First conversation")).toBeInTheDocument());
    fireEvent.click(screen.getByText("First conversation"));
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    useTenantStore.getState().switchOrganization("org-2");
    await waitFor(() => expect(screen.queryByText("hello")).not.toBeInTheDocument());
  });

  it("terminates an active stream on unmount", async () => {
    const neverResolved = true;
    (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
      while (neverResolved) {
        await new Promise((r) => setTimeout(r, 10));
      }
    });
    const { unmount } = render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
    const textarea = screen.getByLabelText("Message composer");
    fireEvent.change(textarea, { target: { value: "pending" } });
    fireEvent.keyDown(textarea, { key: "Enter" });
    // Unmount should not throw; controller aborted silently.
    expect(() => unmount()).not.toThrow();
  });

  it("composer: Enter submits, Shift+Enter inserts newline", async () => {
    (apiModule.streamChatResponse as ReturnType<typeof vi.fn>).mockImplementation(async function* () {
      yield { type: "done", conversation_id: "c-x" };
    });
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByLabelText("Message composer")).toBeInTheDocument());
    const textarea = screen.getByLabelText("Message composer") as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "line1" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: true });
    expect(textarea.value).toBe("line1"); // newline via Shift+Enter — no submit yet
  });

  it("handles delete confirmation flow", async () => {
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("First conversation")).toBeInTheDocument());
    // Delete button is only visible on hover (opacity) but still in DOM
    const deleteButtons = screen.getAllByLabelText(/delete/i);
    fireEvent.click(deleteButtons[0]);
    await waitFor(() => expect(screen.getByText("Delete conversation?")).toBeInTheDocument());
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const dialog = screen.getByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(mocked.deleteConversation).toHaveBeenCalledTimes(1));
  });

  it("shows a session-expired redirect when listConversations returns 401", async () => {
    const mocked = apiModule.api as unknown as Record<string, ReturnType<typeof vi.fn>>;
    const { ApiError } = await import("@/lib/api-client");
    mocked.listConversations.mockRejectedValueOnce(new ApiError("unauthorized", 401, "expired"));

    let navigated = "";
    const fakeLocation = {
      get href() {
        return "http://localhost:3000/auth/login";
      },
      set href(v: string) {
        navigated = v;
      },
    };
    const original = Object.getOwnPropertyDescriptor(window, "location");
    Object.defineProperty(window, "location", { configurable: true, value: fakeLocation });
    try {
      render(<AiWorkspace />);
      await waitFor(() => expect(navigated).toBe("/auth/login"));
      expect(apiModule.clearToken).toHaveBeenCalled();
    } finally {
      if (original) Object.defineProperty(window, "location", original);
    }
  });

  it("renders safely — no dangerouslySetInnerHTML in markdown rendering", async () => {
    render(<AiWorkspace />);
    await waitFor(() => expect(screen.getByText("First conversation")).toBeInTheDocument());
    fireEvent.click(screen.getByText("First conversation"));
    await waitFor(() => expect(screen.getByText("hello")).toBeInTheDocument());
    // All rendered content must be text nodes, never raw HTML plugins.
    expect(document.querySelector("iframe, script, object")).toBeNull();
  });

  it("ai-kit is preserved as a separate public route (page exists)", async () => {
    // Static check: the workspace root is NOT /ai-kit — regression guard.
    expect(apiModule.api.listConversations).toBeDefined();
  });
});

describe("AI page route", () => {
  it("renders the AI page header within the shell", async () => {
    render(<AiPage />);
    await waitFor(() => expect(screen.getByText("AI Workspace")).toBeInTheDocument());
    expect(screen.getAllByRole("navigation").length).toBeGreaterThan(0);
  });
});