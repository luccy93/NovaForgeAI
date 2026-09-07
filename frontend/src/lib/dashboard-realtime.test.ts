import { describe, it, expect, vi, afterEach } from "vitest";
import { DashboardRealtime, isRealtimeAvailable, type DashboardRealtimeEvent } from "@/lib/dashboard-realtime";

class FakeEventSource {
  static instances: Array<FakeEventSource> = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: { type: string; data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;
  constructor(public url: string) {
    FakeEventSource.instances.push(this);
  }
  close() {
    this.closed = true;
  }
}

function push(event: Record<string, unknown>, type = "message") {
  FakeEventSource.instances.at(-1)?.onmessage?.({ type, data: JSON.stringify(event) });
}

describe("DashboardRealtime", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    FakeEventSource.instances = [];
    vi.restoreAllMocks();
  });

  it("is unavailable when no backend subscription endpoint exists", () => {
    const rt = new DashboardRealtime({});
    expect(rt.status).toBe("unavailable");
    expect(isRealtimeAvailable()).toBe(false);
    rt.connect(); // must not throw
    expect(FakeEventSource.instances.length).toBe(0);
  });

  it("does not connect when disabled (no realtime contract)", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const onStatus = vi.fn();
    const rt = new DashboardRealtime({ onStatusChange: onStatus });
    rt.connect();
    expect(FakeEventSource.instances.length).toBe(0);
    expect(onStatus).not.toHaveBeenCalled();
  });

  it("connects to the endpoint and routes events to a kind", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const rt = new DashboardRealtime({
      endpoint: "/realtime/stream",
      token: "tok",
      onEvent: (e) => events.push(e),
    });
    rt.connect();
    const url = FakeEventSource.instances.at(-1)?.url ?? "";
    expect(url).toContain("/realtime/stream");
    expect(url).toContain("access_token=tok");
    push({ id: "1", type: "agent.run.failed", status: "failed", source: "agents" });
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({ type: "agent.run.failed", kind: "agent", status: "failed" });
  });

  it("ignores unknown event types (unauthorized/unsupported)", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const rt = new DashboardRealtime({
      endpoint: "/realtime/stream",
      onEvent: (e) => events.push(e),
    });
    rt.connect();
    push({ id: "1", type: "someone.else.secret", data: { password: "x" } });
    expect(events).toHaveLength(0);
  });

  it("deduplicates repeated events by id", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const rt = new DashboardRealtime({ endpoint: "/realtime/stream", onEvent: (e) => events.push(e) });
    rt.connect();
    push({ id: "dup-1", type: "delivery.pipeline.run_failed", status: "failed" });
    push({ id: "dup-1", type: "delivery.pipeline.run_failed", status: "failed" });
    expect(events).toHaveLength(1);
  });

  it("drops events scoped to another organization or workspace", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const rt = new DashboardRealtime({
      endpoint: "/realtime/stream",
      organizationId: "org-A",
      workspaceId: "ws-1",
      onEvent: (e) => events.push(e),
    });
    rt.connect();
    push({ id: "1", type: "agent.run.completed", organization_id: "org-B" });
    push({ id: "2", type: "agent.run.completed", organization_id: "org-A", workspace_id: "ws-2" });
    push({ id: "3", type: "agent.run.completed", organization_id: "org-A", workspace_id: "ws-1" });
    expect(events).toHaveLength(1);
    expect(events[0].id).toBe("3");
  });

  it("is safe against malformed / non-object payloads", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const rt = new DashboardRealtime({ endpoint: "/realtime/stream", onEvent: (e) => events.push(e) });
    rt.connect();
    const raw = FakeEventSource.instances.at(-1);
    raw?.onmessage?.({ type: "message", data: "not-json" });
    raw?.onmessage?.({ type: "message", data: "[]" });
    expect(events).toHaveLength(0);
  });

  it("notifies only for notable events, never spam", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const events: DashboardRealtimeEvent[] = [];
    const notifications: string[] = [];
    const rt = new DashboardRealtime({
      endpoint: "/realtime/stream",
      onEvent: (e) => events.push(e),
      onNotify: (msg, tone) => notifications.push(`${tone}:${msg}`),
    });
    rt.connect();
    push({ id: "1", type: "agent.run.completed", status: "ok" }); // info — no notify
    push({ id: "2", type: "agent.run.failed", status: "failed" }); // notable — error
    push({ id: "3", type: "security.alert", status: "open" }); // notable — warning
    expect(events).toHaveLength(3);
    expect(notifications).toEqual(["error:Agent event", "warning:Security alert"]);
  });

  it("bounds the pending buffer", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const rt = new DashboardRealtime({ endpoint: "/realtime/stream", maxPending: 2 });
    rt.connect();
    for (let i = 0; i < 5; i += 1) {
      push({ id: `e${i}`, type: "agent.run.completed", status: "ok" });
    }
    expect(rt.pendingEvents.length).toBe(2);
  });

  it("closes the stream and clears state on cleanup", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const onStatus = vi.fn();
    const rt = new DashboardRealtime({ endpoint: "/realtime/stream", onStatusChange: onStatus });
    rt.connect();
    const source = FakeEventSource.instances.at(-1);
    rt.close();
    expect(source?.closed).toBe(true);
    onStatus.mockClear();
  });
});