import { describe, expect, it, vi } from "vitest";
import { EventStream } from "@/lib/realtime";

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

describe("EventStream", () => {
  it("connects, receives messages and cleans up", () => {
    vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
    const states: Array<string> = [];
    const messages: Array<unknown> = [];
    const stream = new EventStream("/events", (message) => messages.push(message), "tok");
    const off = stream.onStateChange((state) => states.push(state));
    stream.connect();
    const source = FakeEventSource.instances.at(-1);
    expect(source?.url).toContain("/events");
    expect(source?.url).toContain("access_token=tok");
    source?.onopen?.();
    source?.onmessage?.({ type: "message", data: '{"hello":1}' });
    expect(messages).toEqual([{ event: "message", data: { hello: 1 } }]);
    stream.close();
    off();
    expect(source?.closed).toBe(true);
    expect(states).toContain("open");
    expect(states).toContain("closed");
    vi.unstubAllGlobals();
    FakeEventSource.instances = [];
  });

  it("reconnects after errors", () => {
    vi.useFakeTimers();
    try {
      vi.stubGlobal("EventSource", FakeEventSource as unknown as typeof EventSource);
      const states: Array<string> = [];
      const stream = new EventStream("/events", () => {});
      stream.onStateChange((state) => states.push(state));
      stream.connect();
      const before = FakeEventSource.instances.length;
      FakeEventSource.instances.at(-1)?.onerror?.();
      expect(states).toContain("error");
      vi.advanceTimersByTime(1500);
      expect(FakeEventSource.instances.length).toBe(before + 1);
      stream.close();
    } finally {
      vi.useRealTimers();
      vi.unstubAllGlobals();
      FakeEventSource.instances = [];
    }
  });
});
