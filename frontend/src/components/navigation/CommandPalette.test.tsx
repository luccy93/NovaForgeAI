import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPalette } from "@/components/navigation/CommandPalette";
import { api, getToken } from "@/lib/api";
import { ApiError } from "@/lib/api-client";

vi.mock("@/lib/api", () => ({
  getToken: vi.fn(() => null),
  clearToken: vi.fn(),
  api: {
    knowledgeSearch: vi.fn(),
    dataCatalogSearch: vi.fn(),
    whoami: vi.fn(),
    zeroTrustAccessRequests: vi.fn(),
    zeroTrustReviews: vi.fn(),
    zeroTrustApproveAccessRequest: vi.fn(),
    zeroTrustCertifyReview: vi.fn(),
  },
}));

describe("CommandPalette", () => {
  beforeEach(() => {
    vi.mocked(getToken).mockReturnValue(null);
    vi.mocked(api.whoami).mockReset();
    vi.mocked(api.knowledgeSearch).mockReset();
    vi.mocked(api.dataCatalogSearch).mockReset();
    vi.mocked(api.zeroTrustAccessRequests).mockReset();
    vi.mocked(api.zeroTrustReviews).mockReset();
    vi.mocked(api.zeroTrustApproveAccessRequest).mockReset();
    vi.mocked(api.zeroTrustCertifyReview).mockReset();
  });

  function signInAs({ permissions }: { permissions?: string[] } = {}) {
    vi.mocked(getToken).mockReturnValue("token");
    vi.mocked(api.whoami).mockResolvedValue({ permissions: permissions ?? ["zero_trust:write"] } as never);
    vi.mocked(api.knowledgeSearch).mockResolvedValue({ items: [] } as never);
    vi.mocked(api.dataCatalogSearch).mockResolvedValue({ items: [] } as never);
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({ items: [] } as never);
    vi.mocked(api.zeroTrustReviews).mockResolvedValue({ items: [] } as never);
  }

  it("renders nothing when closed", () => {
    render(<CommandPalette open={false} onClose={() => {}} />);
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("filters navigation actions by query", () => {
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Command palette query"), { target: { value: "finops" } });
    expect(screen.getByText("Go to FinOps")).toBeInTheDocument();
    expect(screen.queryByText("Go to AI")).toBeNull();
  });

  it("closes on Escape", () => {
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("shows handoff shortcuts and honest empty recent state", () => {
    render(<CommandPalette open onClose={() => {}} />);
    expect(screen.getByText("Search everything")).toBeInTheDocument();
    expect(screen.getByText("Search Knowledge")).toBeInTheDocument();
    expect(screen.getByText("Search Code")).toBeInTheDocument();
    expect(screen.getByText("Ask AI")).toBeInTheDocument();
    expect(screen.getByText("No recent resources exposed by API.")).toBeInTheDocument();
  });

  it("hides recent when searching", () => {
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.change(screen.getByLabelText("Command palette query"), { target: { value: "finops" } });
    expect(screen.queryByText("No recent resources exposed by API.")).toBeNull();
  });

  it("moves selection with arrow keys", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const options = screen.getAllByRole("option");
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "ArrowDown" });
    expect(options[0]).toHaveAttribute("aria-selected", "false");
    expect(options[1]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "ArrowUp" });
    expect(options[0]).toHaveAttribute("aria-selected", "true");
  });

  it("runs the active action on Enter", () => {
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);
    fireEvent.keyDown(screen.getByLabelText("Command palette query"), { key: "Enter" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("lists the Analytics executive workspace without extra wiring", () => {
    render(<CommandPalette open onClose={() => {}} />);
    expect(screen.getByText("Go to Analytics")).toBeInTheDocument();
  });

  it("surfaces actionable Zero Trust actions for authorized users", async () => {
    signInAs();
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({
      items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "REQUESTED" }],
    } as never);
    vi.mocked(api.zeroTrustReviews).mockResolvedValue({
      items: [{ id: "rv-1", review_type: "privilege", scope: "platform", status: "pending" }],
    } as never);
    render(<CommandPalette open onClose={() => {}} />);
    expect(await screen.findByText("Approve access request: alice@corp.dev · prod-db")).toBeInTheDocument();
    expect(screen.getByText("Certify access review: privilege · platform")).toBeInTheDocument();
  });

  it("hides actions without zero_trust:write", async () => {
    signInAs({ permissions: [] });
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({
      items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "REQUESTED" }],
    } as never);
    render(<CommandPalette open onClose={() => {}} />);
    await waitFor(() => expect(api.zeroTrustAccessRequests).toHaveBeenCalled());
    expect(screen.queryByText(/Approve access request/)).toBeNull();
    expect(screen.queryByText(/Certify access review/)).toBeNull();
  });

  it("skips non-actionable targets", async () => {
    signInAs();
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({
      items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "APPROVED" }],
    } as never);
    vi.mocked(api.zeroTrustReviews).mockResolvedValue({
      items: [{ id: "rv-1", review_type: "privilege", scope: "platform", status: "certified" }],
    } as never);
    render(<CommandPalette open onClose={() => {}} />);
    await waitFor(() => expect(api.zeroTrustAccessRequests).toHaveBeenCalled());
    expect(screen.queryByText(/Approve access request/)).toBeNull();
    expect(screen.queryByText(/Certify access review/)).toBeNull();
  });

  it("opens the approve confirmation without closing the palette", async () => {
    signInAs();
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({
      items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "REQUESTED" }],
    } as never);
    vi.mocked(api.zeroTrustApproveAccessRequest).mockResolvedValue({ id: "req-1", status: "ACTIVE" } as never);
    const onClose = vi.fn();
    render(<CommandPalette open onClose={onClose} />);
    fireEvent.click(await screen.findByText("Approve access request: alice@corp.dev · prod-db"));
    expect(screen.getAllByRole("dialog")).toHaveLength(2);
    expect(screen.getByLabelText("Command palette query")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(api.zeroTrustApproveAccessRequest).toHaveBeenCalledWith("token", "req-1"));
    await waitFor(() => expect(screen.getAllByRole("dialog")).toHaveLength(1));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("requires the certify checkbox before confirming certification", async () => {
    signInAs();
    vi.mocked(api.zeroTrustReviews).mockResolvedValue({
      items: [{ id: "rv-1", review_type: "privilege", scope: "platform", status: "pending" }],
    } as never);
    vi.mocked(api.zeroTrustCertifyReview).mockResolvedValue({ id: "rv-1" } as never);
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.click(await screen.findByText("Certify access review: privilege · platform"));
    const confirmButton = screen.getByRole("button", { name: "Confirm certification" });
    expect(confirmButton).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(confirmButton).toBeEnabled();
    fireEvent.click(confirmButton);
    await waitFor(() => expect(api.zeroTrustCertifyReview).toHaveBeenCalledWith("token", "rv-1"));
  });

  it("keeps the confirmation open when the backend forbids", async () => {
    signInAs();
    vi.mocked(api.zeroTrustAccessRequests).mockResolvedValue({
      items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "REQUESTED" }],
    } as never);
    vi.mocked(api.zeroTrustApproveAccessRequest).mockRejectedValue(new ApiError("forbidden", 403, "Forbidden"));
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.click(await screen.findByText("Approve access request: alice@corp.dev · prod-db"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    expect(await screen.findByText(/zero_trust:write authorization is required/)).toBeInTheDocument();
    expect(screen.getAllByRole("dialog")).toHaveLength(2);
  });

  it("refreshes targets when the backend reports a stale target", async () => {
    signInAs();
    vi.mocked(api.zeroTrustAccessRequests)
      .mockResolvedValueOnce({
        items: [{ id: "req-1", identity: "alice@corp.dev", action: "prod-db", status: "REQUESTED" }],
      } as never)
      .mockResolvedValue({ items: [] } as never);
    vi.mocked(api.zeroTrustApproveAccessRequest).mockRejectedValue(new ApiError("server", 404, "Not found"));
    render(<CommandPalette open onClose={() => {}} />);
    fireEvent.click(await screen.findByText("Approve access request: alice@corp.dev · prod-db"));
    fireEvent.click(screen.getByRole("button", { name: "Confirm approval" }));
    await waitFor(() => expect(api.zeroTrustAccessRequests).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.queryByText(/Approve access request/)).toBeNull());
  });

  it("traps Tab focus within the palette dialog", () => {
    render(<CommandPalette open onClose={() => {}} />);
    const input = screen.getByLabelText("Command palette query");
    input.focus();
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    const focusables = Array.from(dialog.querySelectorAll<HTMLElement>("button:not([disabled]), input"));
    const last = focusables[focusables.length - 1];
    last.focus();
    fireEvent.keyDown(last, { key: "Tab" });
    expect(document.activeElement).toBe(input);
  });
});