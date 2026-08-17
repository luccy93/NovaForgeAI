# Volume 41 — Developer Tools & IDE Integrations

## Overview

Full developer tooling integration connecting NovaForge AI's capabilities directly to developers' IDE workflows. Supports VS Code, JetBrains IDEs, CLI, and CI/CD pipelines.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    NovaForge Server                      │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│  │  DevTools   │  │   GitHub     │  │   Existing    │  │
│  │    API      │  │ Integration  │  │   Systems     │  │
│  │  (16 routes)│  │  (12 routes) │  │  (RAG/AI/etc) │  │
│  └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│         │                │                  │           │
│  ┌──────┴────────────────┴──────────────────┴───────┐  │
│  │              Session Management                   │  │
│  │         Context Collection Engine                 │  │
│  │          Code Action Pipeline                     │  │
│  │           Streaming (SSE)                         │  │
│  └──────────────────────────────────────────────────┘  │
└──────────────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────┴──────┐    ┌─────┴──────┐    ┌─────┴──────┐
  │  VS Code   │    │ JetBrains  │    │    CLI     │
  │ Extension  │    │  Plugin    │    │  Extension │
  │ (TypeScript│    │  (Kotlin)  │    │  (Python)  │
  └────────────┘    └────────────┘    └────────────┘
```

## Backend API (`/api/v1/devtools/`)

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/sessions` | Create a devtools session |
| GET | `/devtools/sessions/{id}` | Get session details |
| DELETE | `/devtools/sessions/{id}` | Close session |

### Context Collection

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/context` | Collect file, symbol, RAG, and graph context |

### Code Actions

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/code-actions` | Execute code action (explain, fix, refactor, optimize, generate_tests, generate_docs, security_review) |
| POST | `/devtools/code-actions/diff/{id}` | Get diff preview |
| POST | `/devtools/code-actions/apply/{id}` | Apply or reject action |

### Code Review

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/review` | AI code review (standard, security, architecture, performance) |

### Agent Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/agents/run` | Run agent from IDE/CLI |

### Search

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/search` | Search repository (semantic, symbol, file, repository) |

### Workflow Execution

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/devtools/workflows/run` | Execute workflow from IDE/CLI |

### Client Capabilities

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/devtools/capabilities` | Get supported features for client type |

### Git Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/devtools/git/status` | Get git branch, staged/unstaged changes |
| GET | `/devtools/git/diff` | Get git diff |
| GET | `/devtools/git/context` | Get full git context (branch, PR, commit) |

### Diagnostics

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/devtools/diagnostics` | Get lint/type/security diagnostics |

## GitHub/CI Integration (`/api/v1/github/`)

### Webhooks

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/github/webhook` | Receive GitHub webhooks |
| GET | `/github/repositories/{id}/webhooks` | List webhooks |
| POST | `/github/repositories/{id}/webhooks` | Create webhook |
| DELETE | `/github/repositories/{id}/webhooks/{id}` | Delete webhook |

### Pull Requests

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/github/pr/review` | Trigger AI PR review |
| POST | `/github/pr/comment` | Post PR comment |
| POST | `/github/pr/approve` | Approve PR |
| GET | `/github/pr/{number}/analysis` | Get PR analysis |

### CI/CD

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/github/ci/status` | Update CI check status |
| POST | `/github/ci/trigger` | Trigger CI workflow |
| POST | `/github/ci/validate` | Validate CI config |
| GET | `/github/ci/status/{run_id}` | Get CI run status |

## Client Capabilities

Each client type gets tailored capabilities:

| Feature | VS Code | JetBrains | CLI | CI |
|---------|---------|-----------|-----|-----|
| Streaming | ✅ | ✅ | ✅ | ✅ |
| Cancellation | ✅ | ✅ | ✅ | ✅ |
| Diff Preview | ✅ | ✅ | ❌ | ❌ |
| Code Actions | ✅ | ✅ | ✅ | ✅ |
| Review | ✅ | ✅ | ✅ | ✅ |
| Search | ✅ | ✅ | ✅ | ✅ |
| Agent Execution | ✅ | ✅ | ✅ | ✅ |
| Workflow Execution | ✅ | ✅ | ✅ | ✅ |
| Git Integration | ✅ | ✅ | ✅ | ✅ |
| Webview | ✅ | ❌ | ❌ | ❌ |
| Diagnostics | ✅ | ✅ | ❌ | ❌ |
| Code Lens | ✅ | ❌ | ❌ | ❌ |
| Inline Completion | ✅ | ❌ | ❌ | ❌ |
| Offline Mode | ❌ | ❌ | ✅ | ✅ |
| CI Mode | ❌ | ❌ | ✅ | ✅ |
| JSON Output | ❌ | ❌ | ✅ | ✅ |
| Machine Output | ❌ | ❌ | ❌ | ✅ |

## CLI Commands

```bash
# Chat with AI
python -m app.cli.developer_commands chat "explain this code" --stream

# Run an agent
python -m app.cli.developer_commands agent code_reviewer "review my changes"

# Code review
python -m app.cli.developer_commands review --file src/main.py --type security

# Search
python -m app.cli.developer_commands search "authentication" --type semantic

# Code actions
python -m app.cli.developer_commands explain src/main.py "def login(): ..."
python -m app.cli.developer_commands fix src/main.py "broken code"
python -m app.cli.developer_commands security src/main.py "user input"

# Workflow
python -m app.cli.developer_commands workflow wf_123 --inputs '{"key": "value"}'

# Auth
python -m app.cli.developer_commands login user@example.com password
python -m app.cli.developer_commands whoami
python -m app.cli.developer_commands status --json
```

## Python SDK

```python
from sdk.client import NovaForgeClient

client = NovaForgeClient(base_url="http://localhost:8000", api_key="your-api-key")

# Create session
session = client.create_devtools_session("vscode", org_id="org-1")

# Code action
result = client.code_action(
    action="explain",
    file_path="src/main.py",
    language="python",
    code="def login(): ...",
    session_id=session.session_id,
)

# Review
review = client.review_code(
    session_id=session.session_id,
    file_path="src/main.py",
    review_type="security",
)

# Search
results = client.search_code(
    session_id=session.session_id,
    query="authentication",
    search_type="semantic",
)

# Run agent
run = client.run_agent_from_ide(
    session_id=session.session_id,
    agent_name="code_reviewer",
    task="Review my changes",
)
```

## TypeScript SDK

```typescript
import { NovaForgeDevToolsClient } from './sdk';

const client = new NovaForgeDevToolsClient('http://localhost:8000', undefined, 'token');

// Create session
const session = await client.createSession({ client_type: 'vscode' });

// Code action
const result = await client.codeAction({
  session_id: session.session_id,
  action: 'explain',
  file_path: 'src/main.ts',
  language: 'typescript',
  code: 'function login() { ... }',
});

// Stream chat
for await (const event of client.streamChat('Hello AI')) {
  console.log(event);
}
```

## Streaming (SSE)

All streaming endpoints return `text/event-stream` with SSE events:

```
data: {"type": "started", "action_id": "uuid"}

data: {"type": "chunk", "content": "Here is the explanation..."}

data: {"type": "diff", "diff": "--- a/main.py\n+++ b/main.py\n..."}

data: {"type": "done", "action_id": "uuid"}
```

Event types: `started`, `chunk`, `diff`, `status`, `done`, `error`, `citation`, `context`

## Security

- All endpoints require authentication (JWT or API key)
- Session ownership validation (users can only access their own sessions)
- CSRF protection on state-changing operations
- HMAC-SHA256 webhook signature verification
- Rate limiting on all endpoints
- Never silently modify files — all code actions require user confirmation
- Tenant isolation enforced

## Tests

| Test File | Tests | Coverage |
|-----------|-------|----------|
| `test_devtools.py` | 47 | DevTools API (sessions, context, actions, review, search, git, diagnostics) |
| `test_github_integration.py` | 63 | GitHub/CI (webhooks, PR, CI, security, event handlers) |
| `test_developer_cli.py` | 15 | CLI commands (chat, agent, review, search, auth) |
| `test_sdk_devtools.py` | 33 | SDK (sync/async devtools methods, models) |
| **Total** | **158** | |
