import * as vscode from 'vscode';

export class NovaForgeError extends Error {
  readonly statusCode: number;
  readonly responseBody?: string;
  readonly endpoint: string;

  constructor(message: string, statusCode: number, endpoint: string, responseBody?: string) {
    super(message);
    this.name = 'NovaForgeError';
    this.statusCode = statusCode;
    this.endpoint = endpoint;
    this.responseBody = responseBody;
  }
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  refresh_token?: string;
  scope?: string;
}

export interface WhoamiResponse {
  id: string;
  email: string;
  name?: string;
  organizations?: Array<{ id: string; name: string; role: string }>;
}

export interface StatusResponse {
  status: string;
  version?: string;
  user?: WhoamiResponse;
}

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: number;
}

export interface ChatResponse {
  message: string;
  conversation_id?: string;
  model?: string;
  tokens_used?: number;
  citations?: Array<{ title: string; path: string; line?: number; snippet?: string }>;
}

export interface ChatStreamChunk {
  content: string;
  done: boolean;
  conversation_id?: string;
}

export type SearchType = 'all' | 'file' | 'symbol' | 'documentation' | 'code';

export interface SearchResult {
  results: SearchResultItem[];
  total: number;
  query: string;
}

export interface SearchResultItem {
  type: string;
  title?: string;
  path?: string;
  line?: number;
  column?: number;
  snippet?: string;
  description?: string;
  score?: number;
}

export interface CodeActionResult {
  result?: string;
  explanation?: string;
  suggestedCode?: string;
  diff?: string;
  diagnostics?: Array<{
    message: string;
    severity: string;
    line?: number;
    column?: number;
  }>;
}

export type ReviewSeverity = 'critical' | 'error' | 'warning' | 'info' | 'hint';

export interface ReviewFinding {
  message: string;
  severity: ReviewSeverity;
  rule?: string;
  code?: string;
  file?: string;
  line?: number;
  column?: number;
  endLine?: number;
  endColumn?: number;
  suggestedFix?: string;
}

export interface ReviewResult {
  summary: string;
  findings: ReviewFinding[];
  score?: number;
  reviewedAt?: string;
}

export interface AgentRunResponse {
  result: string;
  agentName: string;
  status: string;
  duration?: number;
}

export interface WorkflowRunResponse {
  result: unknown;
  workflowId: string;
  status: string;
  duration?: number;
  outputs?: Record<string, unknown>;
}

export interface SessionResponse {
  sessionId: string;
  clientType: string;
  createdAt: string;
}

export interface CapabilitiesResponse {
  features: string[];
  models: string[];
  actions: string[];
  agents?: string[];
  workflows?: string[];
}

export interface Organization {
  id: string;
  name: string;
  slug: string;
  role?: string;
}

export interface Repository {
  id: string;
  name: string;
  fullName: string;
  orgId?: string;
  defaultBranch?: string;
}

export class NovaForgeAPI {
  private apiUrl: string;
  private apiKey: string;

  constructor() {
    const config = vscode.workspace.getConfiguration('novaforge');
    this.apiUrl = config.get<string>('apiUrl', 'https://api.novaforge.dev');
    this.apiKey = config.get<string>('apiKey', '');
  }

  private getHeaders(token?: string): Record<string, string> {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Accept': 'application/json'
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    } else if (this.apiKey) {
      headers['X-API-Key'] = this.apiKey;
    }

    return headers;
  }

  private async get<T>(endpoint: string, token?: string): Promise<T> {
    const url = `${this.apiUrl}${endpoint}`;
    const headers = this.getHeaders(token);

    const response = await fetch(url, {
      method: 'GET',
      headers,
      signal: AbortSignal.timeout(30000)
    });

    return this.handleResponse<T>(response, endpoint);
  }

  private async post<T>(endpoint: string, body: unknown, token?: string): Promise<T> {
    const url = `${this.apiUrl}${endpoint}`;
    const headers = this.getHeaders(token);

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(60000)
    });

    return this.handleResponse<T>(response, endpoint);
  }

  private async put<T>(endpoint: string, body: unknown, token?: string): Promise<T> {
    const url = `${this.apiUrl}${endpoint}`;
    const headers = this.getHeaders(token);

    const response = await fetch(url, {
      method: 'PUT',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(30000)
    });

    return this.handleResponse<T>(response, endpoint);
  }

  private async delete<T>(endpoint: string, token?: string): Promise<T> {
    const url = `${this.apiUrl}${endpoint}`;
    const headers = this.getHeaders(token);

    const response = await fetch(url, {
      method: 'DELETE',
      headers,
      signal: AbortSignal.timeout(30000)
    });

    return this.handleResponse<T>(response, endpoint);
  }

  private async handleResponse<T>(response: Response, endpoint: string): Promise<T> {
    let bodyText: string | undefined;
    try {
      bodyText = await response.text();
    } catch {
      bodyText = undefined;
    }

    if (!response.ok) {
      let detail = '';
      if (bodyText) {
        try {
          const parsed = JSON.parse(bodyText);
          detail = parsed.detail || parsed.message || parsed.error || bodyText;
        } catch {
          detail = bodyText;
        }
      }

      throw new NovaForgeError(
        `HTTP ${response.status}: ${detail || response.statusText}`,
        response.status,
        endpoint,
        bodyText
      );
    }

    if (!bodyText || bodyText.length === 0) {
      return {} as T;
    }

    try {
      return JSON.parse(bodyText) as T;
    } catch {
      return bodyText as unknown as T;
    }
  }

  private async postStream(
    endpoint: string,
    body: unknown,
    token?: string
  ): Promise<ReadableStream<Uint8Array>> {
    const url = `${this.apiUrl}${endpoint}`;
    const headers = this.getHeaders(token);

    const response = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120000)
    });

    if (!response.ok) {
      let detail = '';
      try {
        detail = await response.text();
      } catch {
        // ignore
      }
      throw new NovaForgeError(
        `HTTP ${response.status}: ${detail || response.statusText}`,
        response.status,
        endpoint,
        detail
      );
    }

    if (!response.body) {
      throw new NovaForgeError('No response body for stream', 0, endpoint);
    }

    return response.body;
  }

  async login(email: string, password: string): Promise<TokenResponse> {
    return this.post<TokenResponse>('/auth/token-exchange', {
      grant_type: 'password',
      email,
      password
    });
  }

  async refreshToken(token: string): Promise<TokenResponse> {
    return this.post<TokenResponse>('/auth/token-exchange', {
      grant_type: 'refresh_token',
      refresh_token: token
    });
  }

  async whoami(token?: string): Promise<WhoamiResponse> {
    return this.get<WhoamiResponse>('/auth/whoami', token);
  }

  async status(token?: string): Promise<StatusResponse> {
    return this.get<StatusResponse>('/auth/status', token);
  }

  async chat(
    message: string,
    conversationId?: string,
    repoId?: string,
    token?: string
  ): Promise<ChatResponse> {
    const body: Record<string, unknown> = { message };
    if (conversationId) {
      body.conversation_id = conversationId;
    }
    if (repoId) {
      body.repo_id = repoId;
    }
    return this.post<ChatResponse>('/chat', body, token);
  }

  async chatStream(
    message: string,
    conversationId?: string,
    repoId?: string,
    token?: string
  ): Promise<ReadableStream<Uint8Array>> {
    const body: Record<string, unknown> = { message, stream: true };
    if (conversationId) {
      body.conversation_id = conversationId;
    }
    if (repoId) {
      body.repo_id = repoId;
    }
    return this.postStream('/chat/stream', body, token);
  }

  async search(
    query: string,
    type: SearchType = 'all',
    repoId?: string,
    token?: string
  ): Promise<SearchResult> {
    const body: Record<string, unknown> = { query, type };
    if (repoId) {
      body.repo_id = repoId;
    }
    return this.post<SearchResult>('/devtools/search', body, token);
  }

  async codeAction(
    action: string,
    filePath: string,
    language: string,
    code: string,
    startLine?: number,
    endLine?: number,
    token?: string
  ): Promise<CodeActionResult> {
    const body: Record<string, unknown> = {
      action,
      file_path: filePath,
      language,
      code
    };
    if (startLine !== undefined) {
      body.start_line = startLine;
    }
    if (endLine !== undefined) {
      body.end_line = endLine;
    }
    return this.post<CodeActionResult>('/devtools/code-actions', body, token);
  }

  async review(
    filePath?: string,
    code?: string,
    reviewType?: string,
    token?: string
  ): Promise<ReviewResult> {
    const body: Record<string, unknown> = {};
    if (filePath) {
      body.file_path = filePath;
    }
    if (code) {
      body.code = code;
    }
    if (reviewType) {
      body.review_type = reviewType;
    }
    return this.post<ReviewResult>('/devtools/review', body, token);
  }

  async runAgent(
    agentName: string,
    task: string,
    token?: string
  ): Promise<AgentRunResponse> {
    return this.post<AgentRunResponse>('/devtools/agents/run', {
      agent_name: agentName,
      task
    }, token);
  }

  async runWorkflow(
    workflowId: string,
    inputs?: Record<string, unknown>,
    token?: string
  ): Promise<WorkflowRunResponse> {
    const body: Record<string, unknown> = { workflow_id: workflowId };
    if (inputs) {
      body.inputs = inputs;
    }
    return this.post<WorkflowRunResponse>('/devtools/workflows/run', body, token);
  }

  async createSession(
    clientType: string,
    orgId?: string,
    repoId?: string,
    token?: string
  ): Promise<SessionResponse> {
    const body: Record<string, unknown> = { client_type: clientType };
    if (orgId) {
      body.org_id = orgId;
    }
    if (repoId) {
      body.repo_id = repoId;
    }
    return this.post<SessionResponse>('/devtools/sessions', body, token);
  }

  async getCapabilities(
    clientType: string,
    token?: string
  ): Promise<CapabilitiesResponse> {
    return this.get<CapabilitiesResponse>(
      `/devtools/capabilities?client_type=${encodeURIComponent(clientType)}`,
      token
    );
  }

  async listOrganizations(token?: string): Promise<Organization[]> {
    return this.get<Organization[]>('/organizations', token);
  }

  async listRepositories(token?: string): Promise<Repository[]> {
    return this.get<Repository[]>('/repositories', token);
  }
}
