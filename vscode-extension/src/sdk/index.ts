// ---------------------------------------------------------------------------
// NovaForge Developer Tools SDK
// Production-quality TypeScript client for the NovaForge DevTools HTTP API.
// Used by the VS Code extension and JetBrains plugin.
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// Error hierarchy
// ---------------------------------------------------------------------------

export class NovaForgeError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(message: string, status: number, body?: unknown) {
    super(message);
    this.name = "NovaForgeError";
    this.status = status;
    this.body = body;
  }
}

export class AuthenticationError extends NovaForgeError {
  constructor(message = "Authentication failed", body?: unknown) {
    super(message, 401, body);
    this.name = "AuthenticationError";
  }
}

export class NotFoundError extends NovaForgeError {
  constructor(message = "Resource not found", body?: unknown) {
    super(message, 404, body);
    this.name = "NotFoundError";
  }
}

export class RateLimitError extends NovaForgeError {
  readonly retryAfter: number | undefined;

  constructor(retryAfter?: number, body?: unknown) {
    super(
      retryAfter
        ? `Rate limited – retry after ${retryAfter}s`
        : "Rate limited",
      429,
      body,
    );
    this.name = "RateLimitError";
    this.retryAfter = retryAfter;
  }
}

export class ValidationError extends NovaForgeError {
  constructor(message = "Validation error", body?: unknown) {
    super(message, 422, body);
    this.name = "ValidationError";
  }
}

export class ServerError extends NovaForgeError {
  constructor(status = 500, message = "Internal server error", body?: unknown) {
    super(message, status, body);
    this.name = "ServerError";
  }
}

// ---------------------------------------------------------------------------
// Domain types
// ---------------------------------------------------------------------------

export interface DevSession {
  session_id: string;
  client_type: string;
  client_version: string;
  organization_id: string;
  repository_id: string;
  created_at: string;
  expires_at: string;
  capabilities: ClientCapabilities;
}

export interface ContextRequest {
  session_id: string;
  file_path?: string;
  language?: string;
  selection?: string;
  imports?: string[];
  workspace_metadata?: Record<string, unknown>;
  max_context_tokens: number;
}

export interface ContextResult {
  context_id: string;
  file_context?: string;
  symbols: SymbolInfo[];
  rag_results: SearchResult[];
  graph_context?: GraphContextResult;
  total_tokens_estimate: number;
}

export interface SymbolInfo {
  name: string;
  kind: string;
  file_path: string;
  line: number;
  end_line?: number;
  signature?: string;
  documentation?: string;
}

export interface GraphContextResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  file_path?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relationship: string;
}

export interface CodeActionRequest {
  session_id: string;
  action: string;
  file_path: string;
  language: string;
  code: string;
  start_line?: number;
  end_line?: number;
  context?: string;
  stream: boolean;
}

export interface CodeActionResult {
  action_id: string;
  action: string;
  file_path: string;
  original_code: string;
  proposed_code: string;
  explanation: string;
  diff: string;
  confidence: number;
  citations: Citation[];
  warnings: string[];
}

export interface Citation {
  source: string;
  file_path?: string;
  line?: number;
  url?: string;
}

export interface ReviewRequest {
  session_id: string;
  file_path?: string;
  code?: string;
  pr_number?: number;
  review_type: string;
  stream: boolean;
}

export interface ReviewResult {
  review_id: string;
  summary: string;
  findings: ReviewFinding[];
  score: number;
  files_reviewed: number;
  lines_reviewed: number;
  duration_ms: number;
}

export interface ReviewFinding {
  id: string;
  severity: "critical" | "high" | "medium" | "low" | "info";
  category: string;
  file_path: string;
  line?: number;
  end_line?: number;
  message: string;
  evidence: string;
  suggested_fix?: string;
  confidence: number;
}

export interface AgentRunRequest {
  session_id: string;
  agent_name: string;
  task: string;
  context?: Record<string, unknown>;
  stream: boolean;
}

export interface AgentRunResult {
  run_id: string;
  agent_name: string;
  status: "running" | "completed" | "failed" | "cancelled";
  result?: string;
  artifacts: AgentArtifact[];
  duration_ms: number;
}

export interface AgentArtifact {
  name: string;
  type: string;
  content: string;
  file_path?: string;
}

export interface SearchRequest {
  session_id: string;
  query: string;
  search_type: "semantic" | "keyword" | "graph" | "hybrid";
  repository_id?: string;
  file_pattern?: string;
  limit: number;
}

export interface SearchResult {
  id: string;
  score: number;
  file_path: string;
  line?: number;
  content: string;
  symbol_type?: string;
  symbol_name?: string;
  repository?: string;
}

export interface SearchResultList {
  query: string;
  search_type: string;
  results: SearchResult[];
  total: number;
  duration_ms: number;
}

export interface WorkflowRunRequest {
  session_id: string;
  workflow_id: string;
  inputs?: Record<string, unknown>;
  stream: boolean;
}

export interface WorkflowRunResult {
  execution_id: string;
  workflow_id: string;
  status: "running" | "completed" | "failed";
  message: string;
}

export interface ClientCapabilities {
  streaming: boolean;
  cancellation: boolean;
  diff_preview: boolean;
  code_actions: boolean;
  review: boolean;
  search: boolean;
  agent_execution: boolean;
  workflow_execution: boolean;
  git_integration: boolean;
  offline_mode: boolean;
  [key: string]: any;
}

export interface GitStatus {
  branch: string;
  remote: string;
  staged_files: GitFileEntry[];
  unstaged_files: GitFileEntry[];
  untracked_files: GitFileEntry[];
  last_commit: string;
  is_clean: boolean;
}

export interface GitFileEntry {
  file_path: string;
  status: string;
}

export interface GitDiff {
  file_path: string;
  staged: boolean;
  diff: string;
  stats: { additions: number; deletions: number; files_changed: number };
}

export interface GitContext {
  branch: string;
  commit_sha: string;
  commit_message: string;
  pr_number?: number;
  pr_title?: string;
  pr_url?: string;
  remote_url?: string;
  is_dirty: boolean;
}

export interface Diagnostics {
  file_path: string;
  diagnostics: DiagnosticEntry[];
  summary: string;
}

export interface DiagnosticEntry {
  severity: "error" | "warning" | "info" | "hint";
  message: string;
  line: number;
  end_line?: number;
  column?: number;
  end_column?: number;
  code?: string;
  source?: string;
}

export interface TokenInfo {
  access_token: string;
  refresh_token?: string;
  expires_in: number;
  token_type: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

// ---------------------------------------------------------------------------
// Streaming event types
// ---------------------------------------------------------------------------

export interface StreamEvent {
  type: string;
  payload: unknown;
}

export interface StreamStartedEvent {
  type: "started";
  payload: { event_id: string; timestamp: string };
}

export interface StreamChunkEvent {
  type: "chunk";
  payload: { content: string; index: number };
}

export interface StreamDiffEvent {
  type: "diff";
  payload: { file_path: string; diff: string; line_start?: number; line_end?: number };
}

export interface StreamStatusEvent {
  type: "status";
  payload: { status: string; message?: string; progress?: number };
}

export interface StreamDoneEvent {
  type: "done";
  payload: { duration_ms: number; summary?: string };
}

export interface StreamErrorEvent {
  type: "error";
  payload: { message: string; code?: string };
}

export interface StreamCitationEvent {
  type: "citation";
  payload: Citation;
}

export interface StreamContextEvent {
  type: "context";
  payload: { context_id: string; tokens_added: number };
}

// ---------------------------------------------------------------------------
// Streaming parser
// ---------------------------------------------------------------------------

export class StreamingParser {
  /**
   * Parse a single SSE line of the form `data: {...}` or `event: ...\ndata: {...}`.
   * Returns `null` for blank/keep-alive lines or lines without parseable data.
   */
  parseSSELine(line: string): StreamEvent | null {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(":")) {
      return null;
    }

    if (trimmed.startsWith("data: ")) {
      const json = trimmed.slice(6).trim();
      if (json === "[DONE]") {
        return { type: "done", payload: { duration_ms: 0 } };
      }
      try {
        const parsed: Record<string, unknown> = JSON.parse(json);
        return {
          type: (parsed.type as string) ?? "chunk",
          payload: parsed.payload ?? parsed,
        } satisfies StreamEvent;
      } catch {
        return { type: "chunk", payload: { content: json } };
      }
    }

    return null;
  }

  /**
   * Async generator that reads an HTTP Response body as an SSE stream and
   * yields parsed `StreamEvent` objects.  Handles partial reads and
   * multi-line JSON payloads.
   */
  async *handleStream(response: Response): AsyncGenerator<StreamEvent, void, unknown> {
    if (!response.body) {
      throw new NovaForgeError("Response body is null – streaming not supported", 500);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const event = this.parseSSELine(line);
          if (event) {
            yield event;
            if (event.type === "done" || event.type === "error") {
              return;
            }
          }
        }
      }

      // Flush any remaining data in the buffer
      if (buffer.trim()) {
        const event = this.parseSSELine(buffer);
        if (event) {
          yield event;
        }
      }
    } finally {
      reader.releaseLock();
    }
  }
}

// ---------------------------------------------------------------------------
// Client configuration
// ---------------------------------------------------------------------------

export interface NovaForgeClientOptions {
  baseUrl: string;
  apiKey?: string;
  accessToken?: string;
  maxRetries?: number;
  retryDelayMs?: number;
  requestTimeoutMs?: number;
  streamingParser?: StreamingParser;
}

// ---------------------------------------------------------------------------
// NovaForgeDevToolsClient
// ---------------------------------------------------------------------------

export class NovaForgeDevToolsClient {
  private readonly baseUrl: string;
  private apiKey: string | undefined;
  private accessToken: string | undefined;
  private readonly maxRetries: number;
  private readonly retryDelayMs: number;
  private readonly requestTimeoutMs: number;
  public readonly streamingParser: StreamingParser;

  constructor(
    base_url: string,
    api_key?: string,
    access_token?: string,
    options?: Partial<Omit<NovaForgeClientOptions, "baseUrl" | "apiKey" | "accessToken">>,
  ) {
    this.baseUrl = base_url.replace(/\/+$/, "");
    this.apiKey = api_key;
    this.accessToken = access_token;
    this.maxRetries = options?.maxRetries ?? 3;
    this.retryDelayMs = options?.retryDelayMs ?? 1000;
    this.requestTimeoutMs = options?.requestTimeoutMs ?? 30_000;
    this.streamingParser = options?.streamingParser ?? new StreamingParser();
  }

  // -----------------------------------------------------------------------
  // Internal helpers
  // -----------------------------------------------------------------------

  private buildHeaders(isStreaming = false): Record<string, string> {
    const headers: Record<string, string> = {
      Accept: "application/json",
    };

    if (!isStreaming) {
      headers["Content-Type"] = "application/json";
    }

    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    } else if (this.apiKey) {
      headers["X-API-Key"] = this.apiKey;
    }

    return headers;
  }

  private createError(response: Response, body: unknown): NovaForgeError {
    const msg =
      typeof body === "object" && body !== null && "message" in body
        ? String((body as Record<string, unknown>).message)
        : `HTTP ${response.status}`;

    switch (response.status) {
      case 401:
        return new AuthenticationError(msg, body);
      case 404:
        return new NotFoundError(msg, body);
      case 422:
        return new ValidationError(msg, body);
      case 429: {
        const retryAfter = response.headers.get("Retry-After");
        return new RateLimitError(retryAfter ? Number(retryAfter) : undefined, body);
      }
      default:
        if (response.status >= 500) {
          return new ServerError(response.status, msg, body);
        }
        return new NovaForgeError(msg, response.status, body);
    }
  }

  private async request<T>(
    method: string,
    path: string,
    body?: unknown,
    retries = this.maxRetries,
  ): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const headers = this.buildHeaders(false);

    for (let attempt = 0; attempt <= retries; attempt++) {
      let response: Response;
      try {
        const controller = new AbortController();
        const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);

        response = await fetch(url, {
          method,
          headers,
          body: body != null ? JSON.stringify(body) : undefined,
          signal: controller.signal,
        });

        clearTimeout(timeout);
      } catch (err: unknown) {
        if (attempt === retries) {
          if (err instanceof Error && err.name === "AbortError") {
            throw new NovaForgeError(`Request timed out after ${this.requestTimeoutMs}ms`, 408);
          }
          throw new NovaForgeError(
            err instanceof Error ? err.message : "Network error",
            0,
          );
        }
        await this.delay(attempt);
        continue;
      }

      if (response.ok) {
        const text = await response.text();
        if (!text) return undefined as T;
        return JSON.parse(text) as T;
      }

      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text().catch(() => null);
      }

      if (response.status === 429 && attempt < retries) {
        const retryAfter = response.headers.get("Retry-After");
        const waitMs = retryAfter
          ? Number(retryAfter) * 1000
          : this.retryDelayMs * Math.pow(2, attempt);
        await this.delayMs(waitMs);
        continue;
      }

      if (response.status >= 500 && attempt < retries) {
        await this.delay(attempt);
        continue;
      }

      throw this.createError(response, errorBody);
    }

    throw new NovaForgeError("Exhausted retries", 0);
  }

  private delay(attempt: number): Promise<void> {
    return this.delayMs(this.retryDelayMs * Math.pow(2, attempt));
  }

  private delayMs(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private async requestStream(
    method: string,
    path: string,
    body?: unknown,
  ): Promise<Response> {
    const url = `${this.baseUrl}${path}`;
    const headers = this.buildHeaders(true);
    headers["Accept"] = "text/event-stream";

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.requestTimeoutMs);

    let response: Response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body != null ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err: unknown) {
      clearTimeout(timeout);
      if (err instanceof Error && err.name === "AbortError") {
        throw new NovaForgeError(`Stream request timed out after ${this.requestTimeoutMs}ms`, 408);
      }
      throw new NovaForgeError(
        err instanceof Error ? err.message : "Network error",
        0,
      );
    }

    clearTimeout(timeout);

    if (!response.ok) {
      let errorBody: unknown;
      try {
        errorBody = await response.json();
      } catch {
        errorBody = await response.text().catch(() => null);
      }
      throw this.createError(response, errorBody);
    }

    return response;
  }

  // -----------------------------------------------------------------------
  // Token / auth management
  // -----------------------------------------------------------------------

  async login(email: string, password: string): Promise<TokenInfo> {
    const token = await this.request<TokenInfo>("POST", "/api/v1/auth/login", {
      email,
      password,
    });
    this.accessToken = token.access_token;
    return token;
  }

  async refreshToken(refresh_token: string): Promise<TokenInfo> {
    const token = await this.request<TokenInfo>("POST", "/api/v1/auth/refresh", {
      refresh_token,
    });
    this.accessToken = token.access_token;
    return token;
  }

  async logout(): Promise<void> {
    await this.request<unknown>("POST", "/api/v1/auth/logout");
    this.accessToken = undefined;
  }

  setAccessToken(token: string | undefined): void {
    this.accessToken = token;
  }

  setApiKey(key: string | undefined): void {
    this.apiKey = key;
  }

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------

  async createSession(
    client_type: string,
    client_version: string,
    organization_id: string,
    repository_id: string,
  ): Promise<DevSession> {
    return this.request<DevSession>("POST", "/api/v1/sessions", {
      client_type,
      client_version,
      organization_id,
      repository_id,
    });
  }

  async getSession(session_id: string): Promise<DevSession> {
    return this.request<DevSession>("GET", `/api/v1/sessions/${encodeURIComponent(session_id)}`);
  }

  async deleteSession(session_id: string): Promise<void> {
    await this.request<unknown>("DELETE", `/api/v1/sessions/${encodeURIComponent(session_id)}`);
  }

  // -----------------------------------------------------------------------
  // Context
  // -----------------------------------------------------------------------

  async collectContext(request: ContextRequest): Promise<ContextResult> {
    return this.request<ContextResult>("POST", "/api/v1/context/collect", request);
  }

  // -----------------------------------------------------------------------
  // Code actions
  // -----------------------------------------------------------------------

  async codeAction(request: CodeActionRequest): Promise<CodeActionResult> {
    return this.request<CodeActionResult>("POST", "/api/v1/code-actions", {
      ...request,
      stream: false,
    });
  }

  // -----------------------------------------------------------------------
  // Review
  // -----------------------------------------------------------------------

  async reviewCode(request: ReviewRequest): Promise<ReviewResult> {
    return this.request<ReviewResult>("POST", "/api/v1/reviews", {
      ...request,
      stream: false,
    });
  }

  // -----------------------------------------------------------------------
  // Agent execution
  // -----------------------------------------------------------------------

  async runAgent(request: AgentRunRequest): Promise<AgentRunResult> {
    return this.request<AgentRunResult>("POST", "/api/v1/agents/run", {
      ...request,
      stream: false,
    });
  }

  // -----------------------------------------------------------------------
  // Search
  // -----------------------------------------------------------------------

  async searchCode(request: SearchRequest): Promise<SearchResultList> {
    return this.request<SearchResultList>("POST", "/api/v1/search", request);
  }

  // -----------------------------------------------------------------------
  // Workflows
  // -----------------------------------------------------------------------

  async runWorkflow(request: WorkflowRunRequest): Promise<WorkflowRunResult> {
    return this.request<WorkflowRunResult>("POST", "/api/v1/workflows/run", {
      ...request,
      stream: false,
    });
  }

  // -----------------------------------------------------------------------
  // Capabilities
  // -----------------------------------------------------------------------

  async getCapabilities(): Promise<ClientCapabilities> {
    return this.request<ClientCapabilities>("GET", "/api/v1/capabilities");
  }

  // -----------------------------------------------------------------------
  // Git
  // -----------------------------------------------------------------------

  async getGitStatus(session_id: string): Promise<GitStatus> {
    return this.request<GitStatus>(
      "GET",
      `/api/v1/git/status?session_id=${encodeURIComponent(session_id)}`,
    );
  }

  async getGitDiff(
    session_id: string,
    file_path: string,
    staged = false,
  ): Promise<GitDiff> {
    const params = new URLSearchParams({
      session_id,
      file_path,
      staged: String(staged),
    });
    return this.request<GitDiff>("GET", `/api/v1/git/diff?${params.toString()}`);
  }

  async getGitContext(session_id: string): Promise<GitContext> {
    return this.request<GitContext>(
      "GET",
      `/api/v1/git/context?session_id=${encodeURIComponent(session_id)}`,
    );
  }

  // -----------------------------------------------------------------------
  // Diagnostics
  // -----------------------------------------------------------------------

  async getDiagnostics(
    file_path: string,
    session_id?: string,
  ): Promise<Diagnostics> {
    const params = new URLSearchParams({ file_path });
    if (session_id) params.set("session_id", session_id);
    return this.request<Diagnostics>("GET", `/api/v1/diagnostics?${params.toString()}`);
  }

  // -----------------------------------------------------------------------
  // Streaming methods – return AsyncGenerator<StreamEvent>
  // -----------------------------------------------------------------------

  /**
   * Generic low-level SSE stream.  Yields `StreamEvent` objects until the
   * server closes the connection or sends a `done`/`error` event.
   */
  private async *sseStream(
    method: string,
    path: string,
    body?: unknown,
  ): AsyncGenerator<StreamEvent, void, unknown> {
    const response = await this.requestStream(method, path, body);
    yield* this.streamingParser.handleStream(response);
  }

  async *streamChat(
    session_id: string,
    messages: Array<{ role: string; content: string }>,
  ): AsyncGenerator<StreamEvent, void, unknown> {
    yield* this.sseStream("POST", "/api/v1/chat/stream", {
      session_id,
      messages,
      stream: true,
    });
  }

  async *streamCodeAction(
    request: Omit<CodeActionRequest, "stream"> & { stream?: boolean },
  ): AsyncGenerator<StreamEvent, void, unknown> {
    yield* this.sseStream("POST", "/api/v1/code-actions", {
      ...request,
      stream: true,
    });
  }

  async *streamReview(
    request: Omit<ReviewRequest, "stream"> & { stream?: boolean },
  ): AsyncGenerator<StreamEvent, void, unknown> {
    yield* this.sseStream("POST", "/api/v1/reviews", {
      ...request,
      stream: true,
    });
  }

  async *streamAgentRun(
    request: Omit<AgentRunRequest, "stream"> & { stream?: boolean },
  ): AsyncGenerator<StreamEvent, void, unknown> {
    yield* this.sseStream("POST", "/api/v1/agents/run", {
      ...request,
      stream: true,
    });
  }
}
