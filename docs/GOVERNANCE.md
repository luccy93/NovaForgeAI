# ======================================================================
# NOVAFORGE AI
# VOLUME 2 — PROJECT GOVERNANCE & STANDARDS
# ======================================================================

**Status:** Ratified
**Version:** 1.0.0
**Last Updated:** 2026-07-19
**Authority:** NovaForge AI Engineering Council

This document derives its authority from Volume 1 (Master Constitution).
All engineering decisions, code reviews, and architectural changes must conform to this document.

---

## 1. VISION & MISSION

### Vision
Forge Smarter. Code Faster. Build the Future.

An open-source enterprise AI platform where every developer has an intelligent teammate that understands their entire codebase — not just the file they're editing.

### Mission
Build the best open-source enterprise AI software engineering platform by combining knowledge graphs, vector search, and multi-agent AI into a unified, production-ready system that augments every stage of the software lifecycle.

### Strategic Pillars
1. **Repository Intelligence** — Deep understanding of code structure, dependencies, and semantics
2. **Hybrid RAG** — Combine vector search, knowledge graphs, and web context for accurate answers
3. **Multi-Agent Coordination** — Specialized agents that collaborate through an orchestrator
4. **Enterprise Ready** — Security, scalability, observability, and deployability out of the box

---

## 2. PRODUCT PRINCIPLES

| # | Principle | How We Apply It |
|---|-----------|-----------------|
| 1 | **AI Augments, Never Replaces** | Every AI output cites sources and provides confidence. Developers always make the final decision. |
| 2 | **Context Is King** | The AI must understand the full repository context — not just isolated files. Knowledge graphs and vector stores exist for this reason. |
| 3 | **Deterministic by Default** | Prefer deterministic, reproducible workflows over unpredictable black-box AI. LLMs are used for synthesis, not for logic. |
| 4 | **Local First** | Self-hostable with a single `docker compose up`. No mandatory cloud dependency. |
| 5 | **Privacy by Design** | Code never leaves the deployment. All processing happens inside the user's infrastructure. |
| 6 | **Progressive Disclosure** | Simple defaults for beginners. Deep configuration for experts. Don't overwhelm. |
| 7 | **API > UI** | Every feature must be accessible via API first. The UI is a consumer of the API, not the primary interface. |
| 8 | **Backward Compatibility** | Never break the API within a major version. Deprecate with clear migration paths. |

---

## 3. ENGINEERING PHILOSOPHY

### 3.1 Clean Architecture
```
┌─────────────────────────────────────────────────┐
│                  API Layer (routes)              │
├─────────────────────────────────────────────────┤
│              Service Layer (business logic)      │
├─────────────────────────────────────────────────┤
│              Repository Layer (data access)      │
├─────────────────────────────────────────────────┤
│              Domain Layer (models, entities)     │
└─────────────────────────────────────────────────┘
```

### 3.2 Rules
- **No business logic in routes** — Routes only: parse request, call service, return response
- **No SQL in routes** — All database access goes through repository classes
- **No AI calls in controllers** — AI orchestration belongs in service layer
- **Dependency injection** — Use FastAPI's `Depends` for all external dependencies
- **Feature-first organization** — Group by feature, not by layer type
- **Composition over inheritance** — Prefer small composable classes over deep hierarchies
- **STRICT typing** — Every function signature must have typed parameters and return types
- **Reusable modules** — Extract shared logic into modules, never copy-paste
- **Single responsibility** — One class, one reason to change
- **Loose coupling** — Services depend on abstractions, not concretions

---

## 4. ARCHITECTURE RULES

### 4.1 Module Structure
Every feature module must contain:
```
module/
├── api.py          # FastAPI routes (thin)
├── service.py      # Business logic
├── repository.py   # Data access (if needed)
├── models.py       # Domain models / SQLAlchemy models
├── schemas.py      # Pydantic request/response schemas
├── validators.py   # Input validation (if complex)
├── tests/          # Unit + integration tests
├── config.py       # Module-level configuration
└── logging.py      # Module-specific logging setup
```

### 4.2 Dependency Flow
```
Route → Service → Repository → Model
         ↓
    External APIs / AI / Queue
```

### 4.3 Data Flow Rules
- Routes receive Pydantic request models, return Pydantic response models
- Services operate on domain entities, not on request/response schemas
- Repositories return domain entities or raw results, never ORM objects outside service layer
- External service calls (AI, Neo4j, Qdrant) are wrapped in service classes
- Never expose internal IDs to clients — use UUIDs throughout

### 4.4 Database Architecture
- **PostgreSQL** — User data, organizations, repositories, conversations, messages
- **Neo4j** — Code relationship graph (files → functions → dependencies)
- **Qdrant** — Vector embeddings for semantic search
- **Redis** — Caching, session store, task queues
- Use Alembic for schema migrations
- Never write raw SQL unless the ORM cannot express the query performantly

---

## 5. CODING STANDARDS

### 5.1 Python (Backend)
- **Python 3.11+** — Use latest stable features
- **Formatter:** Ruff (line length 120)
- **Type checker:** MyPy (strict mode)
- **Linter:** Ruff (select E, F, I, W)
- **Naming:**
  - Classes: `PascalCase`
  - Functions/variables: `snake_case`
  - Constants: `UPPER_SNAKE_CASE`
  - Private methods: `_leading_underscore`
  - Modules: `snake_case`
- **Imports order:** stdlib → third-party → local
- **Docstrings:** Google style for public functions
- **No unnecessary comments** — Code should be self-documenting
- **Max function length:** 40 lines (refactor if longer)
- **Max file length:** 400 lines (split if longer)

### 5.2 TypeScript (Frontend)
(Referenced for frontend maintenance — frontend is a locked asset)
- **Strict mode** enabled in tsconfig
- **ESLint** with recommended rules
- **Naming:** Components PascalCase, hooks `use*`, utilities camelCase
- **No `any`** — Use `unknown` and type guards
- **No default exports** — Prefer named exports

---

## 6. REPOSITORY STANDARDS

### 6.1 Git Conventions
- **Branch naming:** `feature/short-description`, `fix/short-description`, `chore/short-description`
- **Commit messages:** Conventional Commits format
  ```
  feat(chat): add conversation history endpoint
  fix(code): handle empty file in complexity analysis
  chore(deps): update fastapi to 0.115.0
  ```
- **PR title:** Same format as commit
- **PR description:** Must include what, why, how, testing done
- **No direct pushes to `main` or `develop`**

### 6.2 Directory Layout
```
NovaForgeAI/
├── backend/          # Python FastAPI backend
├── frontend/         # Next.js frontend (locked)
├── agents/           # AI agent implementations
├── cli/              # Python CLI tool
├── docker/           # Dockerfiles + compose files
├── kubernetes/       # K8s manifests
├── github/           # GitHub App
├── vscode-extension/ # VS Code extension
├── scripts/          # Dev/CI utility scripts
├── tests/            # Integration/E2E tests
├── database/         # Migrations, seeds
├── docs/             # Documentation
├── .env.example
├── .gitignore
└── README.md
```

---

## 7. API STANDARDS

### 7.1 Design
- **RESTful** — Use HTTP methods semantically
- **Versioned** — Prefix all routes with `/api/v{number}`
- **OpenAPI** — Auto-generated via FastAPI, available at `/docs`
- **JSON only** — Request and response bodies
- **Pagination** — Every list endpoint supports `limit` and `offset`
- **Filtering** — Use query parameters for simple filters
- **Sorting** — Use `sort_by` and `sort_order` query parameters

### 7.2 Response Format
Success:
```json
{
  "data": { ... },
  "meta": { "page": 1, "total": 42 }
}
```

Error:
```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Human-readable description",
    "details": { "field": "email", "reason": "invalid format" }
  }
}
```

### 7.3 HTTP Status Codes
| Code | When |
|------|------|
| 200 | Successful GET, PUT, PATCH |
| 201 | Successful POST (resource created) |
| 204 | Successful DELETE |
| 400 | Validation error, bad request |
| 401 | Missing or invalid authentication |
| 403 | Authenticated but not authorized |
| 404 | Resource not found |
| 409 | Conflict (duplicate, state mismatch) |
| 422 | Request body validation failed |
| 429 | Rate limit exceeded |
| 500 | Unhandled server error |
| 503 | Service temporarily unavailable |

---

## 8. SECURITY STANDARDS

### 8.1 Authentication & Authorization
- **JWT** for stateless authentication
- **Access tokens:** Short-lived (30 min default)
- **Refresh tokens:** Long-lived (7 days), stored securely
- **Passwords** hashed with bcrypt (via passlib)
- **Organization isolation** — RBAC with scoped access
- **All secrets** loaded from environment variables, never hardcoded

### 8.2 Input & Output
- Validate all inputs with Pydantic schemas at the API boundary
- Sanitize outputs — never return raw database errors or stack traces
- Rate limiting on all endpoints (100 req/min standard, 10 req/min for auth)
- CORS restricted to configured origins

### 8.3 Audit Trail
- All mutations (POST/PUT/PATCH/DELETE) are logged with identity, action, timestamp
- Authentication failures are logged with source IP
- Admin actions require additional logging

---

## 9. PERFORMANCE BUDGETS

| Metric | Budget | Violation Action |
|--------|--------|------------------|
| API response time (p95) | < 500ms | Alert, review in next sprint |
| API response time (p99) | < 2s | Alert, escalate immediately |
| RAG query time | < 10s | Optimize retrieval or LLM call |
| Code analysis (1MB file) | < 5s | Optimize AST parsing or add streaming |
| Embedding generation | < 1s per 100 texts | Batch optimization |
| Concurrent users per instance | 100 | Scale horizontally |
| Memory per backend instance | < 512MB | Profile and optimize |
| DB query time (p95) | < 100ms | Add index or rewrite query |
| Startup time | < 10s | Lazy-load heavy modules |
| Docker image size | < 500MB | Multi-stage build, slim base images |

---

## 10. SCALABILITY RULES

- **Stateless services** — No in-memory session state. Use Redis.
- **Horizontal scaling** — Backend is stateless; scale via load balancer + multiple replicas
- **Database connection pooling** — Use SQLAlchemy's pool_pre_ping
- **Async everywhere** — All I/O operations are async (FastAPI, asyncpg, httpx)
- **Background tasks** — Offload heavy work to Celery or background workers
- **Caching** — Cache frequently accessed data in Redis
- **Rate limiting** — Per-user, per-IP, per-endpoint
- **Graceful degradation** — If Neo4j is down, fall back to vector-only search
- **Service readiness** — Health check must verify dependencies before accepting traffic

---

## 11. LOGGING & OBSERVABILITY

### 11.1 Structured Logging
Every log entry must contain:
```json
{
  "timestamp": "2026-07-19T10:30:00+00:00",
  "level": "INFO",
  "logger": "novaforge.services.rag_pipeline",
  "request_id": "abc-123-def",
  "message": "RAG query completed",
  "extra": {
    "query_time_ms": 1234,
    "sources_count": 5,
    "model_used": "gpt-4o-mini"
  }
}
```

### 11.2 Required Observability
1. **Structured logs** — JSON format, all fields indexed
2. **Request tracing** — Every request has a unique X-Request-ID
3. **Metrics** — Prometheus metrics endpoint (`/metrics`)
4. **Health checks** — `/health` (liveness) and `/health/ready` (readiness)
5. **Error reporting** — All unhandled exceptions logged with stack trace
6. **Performance timing** — Every request logged with response time
7. **Audit logs** — All mutations logged with user identity

---

## 12. ERROR HANDLING

### 12.1 Hierarchy
```
NovaForgeError (base)
├── NotFoundError         → 404
├── ValidationError       → 422
├── AuthenticationError   → 401
├── AuthorizationError    → 403
├── ConflictError         → 409
└── ServiceUnavailableError → 503
```

### 12.2 Rules
- All errors return consistent JSON format (see API Standards §7.2)
- Never expose stack traces to the client
- Log the full error server-side for debugging
- Every `except` block must either handle, wrap, or re-raise
- Use FastAPI exception handlers for global catching
- Business logic errors belong in service layer, not routes

---

## 13. DEFINITION OF DONE

A feature is **DONE** only when all of the following are true:

| # | Criterion | Verifiable By |
|---|-----------|---------------|
| 1 | Code compiles without errors | CI pipeline |
| 2 | All new and existing tests pass | `pytest` / `npm test` |
| 3 | Test coverage meets threshold (>80%) | Codecov / coverage report |
| 4 | API documentation is generated | Swagger UI renders correctly |
| 5 | Structured logging is added | Log output verified manually |
| 6 | Error handling is implemented | All error paths tested |
| 7 | Security review passed | No secrets, no injection vectors |
| 8 | Performance is acceptable | Within budgets (§9) |
| 9 | Observability hooks added | Request ID, timing, audit trail |
| 10 | Code review completed | PR approved by at least one peer |
| 11 | Documentation updated | README, API docs, guides |
| 12 | Integration tested | End-to-end flow works |
| 13 | Production ready | Docker image builds, health check passes |
| 14 | Merge to main | Via approved PR, no direct pushes |

---

## 14. RELEASE PROCESS

### 14.1 Versioning
Semantic Versioning: `MAJOR.MINOR.PATCH`
- **MAJOR** — Breaking API changes (rare)
- **MINOR** — New features, backward compatible
- **PATCH** — Bug fixes, performance improvements

### 14.2 Release Stages
```
develop (daily) → staging (weekly) → rc (pre-release) → main (release)
```

| Stage | Deployed To | Criteria |
|-------|-------------|----------|
| `develop` | Dev environment | All unit tests pass |
| `staging` | Staging environment | All integration tests pass, code review done |
| `rc` | Staging + QA | Full regression pass, performance validated |
| `main` | Production | All checks pass, release notes approved |

### 14.3 Release Checklist
- [ ] Version bumped in pyproject.toml / package.json
- [ ] CHANGELOG.md updated
- [ ] All tests green
- [ ] Performance budgets validated
- [ ] Security scan passed
- [ ] Migration scripts verified (if any)
- [ ] Release tagged with `vMAJOR.MINOR.PATCH`
- [ ] Docker images built and pushed
- [ ] Release notes published

---

## 15. QUALITY GATES

Every PR must pass these gates before merge:

| Gate | Tool/Process | Blocking? |
|------|-------------|-----------|
| 1. Code compiles | `ruff check`, `mypy` | Yes |
| 2. Lint passes | `ruff` | Yes |
| 3. Tests pass | `pytest` / `npm test` | Yes |
| 4. Coverage meets threshold | Coverage report | Yes (80%+) |
| 5. No secrets committed | Detect-secrets / git diff | Yes |
| 6. Code review approval | GitHub PR review | Yes |
| 7. No debug code | Manual + linter | Yes |
| 8. Documentation updated | Manual check | Yes |
| 9. Migration script (if DB change) | Alembic autogenerate | Yes |
| 10. Docker build passes | `docker compose build` | Yes |

---

## 16. DOCUMENTATION STANDARDS

### 16.1 Types
- **README.md** — Project overview, quick start, development setup
- **API docs** — Auto-generated via FastAPI's OpenAPI/Swagger
- **Architecture docs** — `/docs/ARCHITECTURE.md` — system design decisions
- **Setup guides** — `/docs/SETUP.md` — installation and configuration
- **Contributing guide** — `CONTRIBUTING.md` — how to contribute
- **CHANGELOG** — `CHANGELOG.md` — per-release changes
- **Code comments** — Google-style docstrings on public functions only

### 16.2 Rules
- Every public function must have a docstring (Python) / JSDoc (TypeScript)
- Every module must have a module-level docstring explaining its purpose
- Architectural decisions must be recorded in ADR format in `/docs/adr/`
- Documentation is reviewed as part of the PR, not an afterthought
- Diagrams use Mermaid syntax for version control compatibility

---

## 17. AI DEVELOPMENT PRINCIPLES

### 17.1 Core Tenets
- **AI augments, never replaces** the developer
- **Never hallucinate** repository data — always use real context
- **Always cite sources** for every AI-generated claim
- **Always provide confidence** scores
- **Prefer deterministic workflows** — AI for synthesis, not for logic
- **Support multiple LLM providers** — OpenAI, Google, Anthropic (pluggable)

### 17.2 Agent Design
Each agent must:
1. Accept typed input (Pydantic schema)
2. Return typed output (Pydantic schema)
3. Log its actions with request ID
4. Handle errors gracefully (fallback message, not crash)
5. Respect timeout budgets
6. Never access the file system directly (use API)

### 17.3 RAG Pipeline Rules
1. Retrieve from vector store (Qdrant) first
2. Enrich with knowledge graph (Neo4j) relationships
3. Optionally supplement with web search
4. Synthesize with LLM
5. Return answer + sources + confidence + model used
6. If no context found, say so clearly — never fabricate

---

## 18. BACKEND ARCHITECTURE

### 18.1 Component Map
```
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  FastAPI     │────▶│  Services     │────▶│  Repositories│
│  (routes)    │     │  (business)   │     │  (data)      │
└─────────────┘     └──────┬───────┘     └──────┬───────┘
                           │                    │
                    ┌──────▼───────┐     ┌──────▼───────┐
                    │  AI Agents    │     │  Databases    │
                    │  (orchestrator)│    │  PG/Neo4j/Qd  │
                    └──────────────┘     └──────────────┘
```

### 18.2 Key Services
| Service | Responsibility | Database |
|---------|---------------|----------|
| AuthService | JWT creation, password validation | PostgreSQL |
| ChatService | Conversation management, message persistence | PostgreSQL |
| RAGPipeline | Hybrid retrieval + LLM synthesis | Qdrant, Neo4j, Web |
| CodeAnalysisService | AST parsing, complexity, dependencies | In-memory |
| GraphStoreService | Neo4j CRUD, Cypher queries | Neo4j |
| VectorStoreService | Qdrant CRUD, semantic search | Qdrant |
| EmbeddingService | Text → vector embedding | OpenAI/Google/Local |
| AgentService | Agent orchestration, pipeline execution | (in-memory) |

### 18.3 Startup Sequence
1. Load configuration from `.env` / environment
2. Configure structured logging
3. Initialize database connection pool (asyncpg)
4. Initialize Neo4j driver (async)
5. Initialize Qdrant client
6. Initialize Redis connection
7. Initialize embedding service
8. Register middleware (CORS, RequestID, Audit, Exception handlers)
9. Register route handlers
10. Start listening

---

## 19. PROJECT GOVERNANCE

### 19.1 Roles
| Role | Responsibility |
|------|---------------|
| **Chief Software Architect** | Architecture decisions, technology selection, standards enforcement |
| **Engineering Manager** | Sprint planning, resource allocation, delivery |
| **Tech Lead** | Code review, quality enforcement, mentoring |
| **Security Lead** | Security reviews, vulnerability management |
| **DevOps Lead** | CI/CD, infrastructure, monitoring |
| **AI/ML Lead** | Agent design, prompt engineering, model selection |
| **Contributor** | Implementation, testing, documentation |

### 19.2 Decision Making
| Decision Type | Who Decides | Process |
|---------------|-------------|---------|
| Architecture change | Chief Architect + Engineering Council | RFC document, 2-day review period |
| New feature | Product Owner + Engineering Manager | Spec review, sprint planning |
| Technology choice | Chief Architect + Tech Lead | RFC with pros/cons, 1-week evaluation |
| Security change | Security Lead + Chief Architect | Immediate, documented after |
| Breaking change | Engineering Council | RFC, 1-week review, migration plan required |
| Library upgrade | Tech Lead | Review changelog, run full test suite |

### 19.3 RFC Process
For any significant change (architecture, breaking, new technology):
1. Write RFC in `docs/rfc/TITLE.md`
2. Submit as PR
3. 48-hour minimum review period
4. Engineering Council votes
5. If approved: merge, implement, document

### 19.4 Communication
- Daily standup: What I did, what I'll do, blockers
- Weekly engineering sync: Architecture decisions, design reviews
- Sprint review: Demo completed work
- Retrospective: What went well, what to improve
- All decisions recorded in writing (GitHub Issues, RFCs, commit messages)

### 19.5 Quality Ownership
- Every engineer owns quality for their code
- Code review is mandatory before merge
- Tests are not optional — untested code is incomplete code
- Technical debt is tracked in the backlog and allocated per sprint (20% capacity)

---

## APPENDIX A: FILE TEMPLATES

### A.1 Python Module Template
```python
"""
Module: app/services/example_service.py

Provides the ExampleService class for handling [domain logic].
"""

import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class ExampleService:
    """Handles [domain description]."""

    def __init__(self, dependency: Optional[Any] = None) -> None:
        self._dependency = dependency or DefaultImplementation()

    async def do_something(self, input_data: str) -> dict:
        """Process input and return result.

        Args:
            input_data: Description of input.

        Returns:
            dict with processed result.

        Raises:
            NotFoundError: If resource not found.
        """
        logger.info("Processing input: %s", input_data[:50])
        # ... implementation ...
        return {"result": "processed"}
```

### A.2 Test Template
```python
"""Tests for example_service.py."""

import pytest
from app.services.example_service import ExampleService


class TestExampleService:
    """Unit tests for ExampleService."""

    async def test_do_something_success(self) -> None:
        """Should return processed result for valid input."""
        service = ExampleService()
        result = await service.do_something("test")
        assert result["result"] == "processed"

    async def test_do_something_empty_input(self) -> None:
        """Should handle empty input gracefully."""
        service = ExampleService()
        result = await service.do_something("")
        assert "result" in result
```

---

*This governance document supplements Volume 1 (Master Constitution). Where conflicts exist, Volume 1 takes precedence.*
