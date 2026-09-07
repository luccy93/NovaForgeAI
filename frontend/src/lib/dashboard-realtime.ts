"use client";

import { EventStream, type StreamMessage } from "@/lib/realtime";

export type RealtimeStatus = "unavailable" | "connecting" | "open" | "closed" | "error";

export type RealtimeEventKind =
  | "ai"
  | "workflow"
  | "agent"
  | "integration"
  | "security"
  | "governance"
  | "finops"
  | "knowledge";

/** Events that map to a targeted dashboard refresh instead of a full reload. */
const EVENT_KIND_BY_TYPE: Record<string, RealtimeEventKind> = {
  "agent.run.completed": "agent",
  "agent.run.failed": "agent",
  "delivery.pipeline.run_failed": "workflow",
  "delivery.pipeline.run_started": "workflow",
  "delivery.pipeline.run_completed": "workflow",
  "automation.task.failed": "workflow",
  "automation.task.completed": "workflow",
  "automation.approval.required": "workflow",
  "security.alert": "security",
  "marketplace.package_install_failed": "integration",
  "webhook.failed": "integration",
  "integration.failed": "integration",
  "governance.violation": "governance",
  "sre.slo.violation": "governance",
  "finops.budget.anomaly": "finops",
  "automation.budget.exceeded": "finops",
  "knowledge.indexed": "knowledge",
  "repository.imported": "knowledge",
};

/** Event types that should produce a user notification (real backend events only). */
const NOTIFY_KINDS: Record<RealtimeEventKind, string> = {
  workflow: "Workflow event",
  agent: "Agent event",
  integration: "Integration event",
  security: "Security alert",
  governance: "Governance violation",
  finops: "Budget anomaly",
  ai: "AI activity",
  knowledge: "Knowledge event",
};

interface RealtimeOptions {
  /** Backend SSE endpoint path. Empty/unset means the capability is unavailable. */
  endpoint?: string;
  token?: string | null;
  organizationId?: string | null;
  workspaceId?: string | null;
  onEvent?: (event: DashboardRealtimeEvent) => void;
  onNotify?: (message: string, tone: "warning" | "error" | "info") => void;
  onStatusChange?: (status: RealtimeStatus) => void;
  /** Only event types whose kind is in this set are forwarded. */
  kinds?: ReadonlySet<RealtimeEventKind>;
  maxPending?: number;
}

export interface DashboardRealtimeEvent {
  id?: string;
  type: string;
  kind: RealtimeEventKind;
  source?: string;
  status?: string;
  organizationId?: string;
  workspaceId?: string;
  timestamp?: string;
}

/**
 * Dashboard realtime adapter over the existing EventStream foundation.
 *
 * The adapter is backend-contract aware: it only connects when an SSE
 * subscription endpoint actually exists. With no endpoint configured the
 * status is explicitly `unavailable` — the dashboard must never imply a
 * live stream that does not exist.
 *
 * No fake events, no timers simulating realtime, no second realtime system.
 */
export class DashboardRealtime {
  private stream: EventStream | null = null;
  private seen = new Set<string>();
  private pending: Array<DashboardRealtimeEvent> = [];
  status: RealtimeStatus = "unavailable";

  constructor(private readonly options: RealtimeOptions) {
    if (!options.endpoint) {
      this.status = "unavailable";
      return;
    }
    this.status = "connecting";
    this.stream = new EventStream(
      options.endpoint,
      (message) => this.onStreamMessage(message),
      options.token,
    );
  }

  connect(): void {
    if (!this.stream) return;
    this.stream.connect();
  }

  close(): void {
    this.stream?.close();
    this.stream = null;
    this.seen.clear();
    this.pending = [];
    this.status = "closed";
    this.options.onStatusChange?.(this.status);
  }

  private onStreamMessage(message: StreamMessage): void {
    const data = message.data;
    if (!data || typeof data !== "object") return; // malformed event safe
    const record = data as Record<string, unknown>;
    const type = typeof record.type === "string" ? record.type : message.event;
    const kind = EVENT_KIND_BY_TYPE[type];
    if (!kind) return; // unknown/unauthorized event type ignored
    if (this.options.kinds && !this.options.kinds.has(kind)) return;

    // Tenant/workspace isolation: drop events not scoped to this context.
    const orgId = typeof record.organization_id === "string" ? record.organization_id : undefined;
    const wsId = typeof record.workspace_id === "string" ? record.workspace_id : undefined;
    if (this.options.organizationId && orgId && orgId !== this.options.organizationId) return;
    if (this.options.workspaceId && wsId && wsId !== this.options.workspaceId) return;

    const event: DashboardRealtimeEvent = {
      id: typeof record.id === "string" ? record.id : undefined,
      type,
      kind,
      source: typeof record.source === "string" ? record.source : undefined,
      status: typeof record.status === "string" ? record.status : undefined,
      organizationId: orgId,
      workspaceId: wsId,
      timestamp: typeof record.timestamp === "string" ? record.timestamp : undefined,
    };

    // Duplicate-event protection (bounded).
    const cursor = event.id ?? `${event.type}:${event.timestamp ?? ""}`;
    if (cursor && this.seen.has(cursor)) return;
    if (cursor) {
      if (this.seen.size >= 256) this.seen.clear();
      this.seen.add(cursor);
    }

    this.pending.push(event);
    const maxPending = this.options.maxPending ?? 32;
    if (this.pending.length > maxPending) this.pending.splice(0, this.pending.length - maxPending);

    this.options.onEvent?.(event);
    if (this.shouldNotify(event)) {
      this.options.onNotify?.(NOTIFY_KINDS[event.kind], this.toneFor(event));
    }
  }

  private shouldNotify(event: DashboardRealtimeEvent): boolean {
    // Only surface notable events — never spam on every streamed update.
    const notable =
      event.type.includes("failed") ||
      event.type.includes("violation") ||
      event.type.includes("exceeded") ||
      event.type.includes("alert") ||
      event.type.includes("approval.required") ||
      event.type.includes("aborted") ||
      event.type.includes("install_failed");
    return notable;
  }

  private toneFor(event: DashboardRealtimeEvent): "warning" | "error" | "info" {
    const failed = event.status?.toLowerCase().includes("fail") ||
      event.type.includes("failed") ||
      event.type.includes("violation") ||
      event.type.includes("exceeded");
    if (failed) return "error";
    if (event.kind === "security" || event.kind === "governance" || event.kind === "finops") return "warning";
    return "info";
  }

  get pendingEvents(): ReadonlyArray<DashboardRealtimeEvent> {
    return this.pending;
  }
}

export function isRealtimeAvailable(): boolean {
  return false;
}