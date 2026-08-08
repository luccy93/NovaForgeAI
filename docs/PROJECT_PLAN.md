# Project Plan: AI-Powered Code Intelligence Platform

## 🎯 Project Vision
Build an AI-powered code intelligence platform that combines GraphRAG (Graph-based Retrieval-Augmented Generation) with modern tooling for code analysis, documentation, and AI-assisted development.

---

## 🏗️ Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              FRONTEND (Next.js 15)                           │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  Dashboard  │ │ Code Editor │ │  Chat UI    │ │  Graph Visualizer   │   │
│  │  (Next.js)  │ │  (Monaco)   │ │  (Stream)   │ │  (React Flow/D3)    │   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘   │
│         │               │               │                   │              │
│         └───────────────┼───────────────┼───────────────────┘              │
│                         ▼                                               │
│              ┌─────────────────────┐                                   │
│              │   NextAuth/Clerk    │                                   │
│              │   Auth Middleware   │                                   │
│              └──────────┬──────────┘                                   │
└─────────────────────────┼───────────────────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BACKEND (FastAPI)                                 │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────────┐   │
│  │  API Routes │ │  WebSocket  │ │  Auth       │ │  Background Jobs    │   │
│  │  (REST/WS)  │ │  Manager    │ │  Middleware │ │  (Celery/Redis)     │   │
│  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────────┬──────────┘   │
│         │               │               │                   │              │
│         └───────────────┼───────────────┼───────────────────┘              │
│                         ▼               ▼                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                    LangGraph Orchestration Layer                    │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐   │  │
│  │  │ Code Parser │ │ Graph RAG   │ │ Vector RAG  │ │ Agent       │   │  │
│  │  │ (Tree-sitter)│ │ (LangGraph) │ │ (LlamaIndex)│ │ Orchestrator│   │  │
│  │  └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘   │  │
│  └─────────┼───────────────┼───────────────┼───────────────┼───────────┘  │
└────────────┼───────────────┼───────────────┼───────────────┼──────────────┘
             ▼               ▼               ▼               ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              DATA LAYER                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │
│  │  PostgreSQL  │  │   Neo4j      │  │   Qdrant/    │  │    Redis     │   │
│  │  (Metadata,  │  │  (Code Graph)│  │   ChromaDB   │  │  (Cache,     │   │
│  │   Users,     │  │              │  │  (Vectors)   │  │   Sessions,  │   │
│  │   Projects)  │  │              │  │              │  │   Queue)     │   │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Phase 1: Foundation & Infrastructure (Weeks 1-2)

### 1.1 Infrastructure Setup
- [ ] **Docker Compose** for local development
  - PostgreSQL 16 + pgvector extension
  - Neo4j 5.x
  - Qdrant or ChromaDB
  - Redis 7
  - FastAPI backend
  - Next.js 15 frontend
- [ ] **Kubernetes** manifests (Helm charts) for staging/prod
- [ ] **GitHub Actions** CI/CD pipeline
  - Lint, type-check, test
  - Build & push Docker images
  - Deploy to staging on merge to main
  - Deploy to prod on tag

### 1.2 Backend Foundation (FastAPI)
- [ ] Project structure with `pyproject.toml` (Poetry/UV)
- [ ] FastAPI app with:
  - Pydantic Settings for config
  - SQLAlchemy 2.0 + AsyncPG
  - Alembic migrations
  - Redis session/cache
  - Structured logging (structlog)
  - OpenTelemetry tracing
- [ ] Authentication integration (Clerk or NextAuth)
- [ ] API versioning (`/api/v1/`)
- [ ] Health checks & readiness probes

### 1.3 Frontend Foundation (Next.js 15)
- [ ] Next.js 15 App Router + TypeScript
- [ ] Tailwind CSS + Shadcn UI setup
- [ ] Clerk/NextAuth provider
- [ ] Monaco Editor integration
- [ ] React Query / TanStack Query for data fetching
- [ ] WebSocket hook for real-time updates
- [ ] ESLint, Prettier, Husky pre-commit

### 1.4 Database Schemas

**PostgreSQL (Users, Projects, Metadata):**
```sql
-- Users (synced from Clerk/NextAuth)
-- Projects (code repositories)
-- Files, Symbols, Embeddings metadata
-- Chat sessions, messages
-- Analysis jobs queue
```

**Neo4j (Code Knowledge Graph):**
```cypher
// Nodes: File, Class, Function, Variable, Import, Module
// Relationships: CONTAINS, CALLS, IMPORTS, INHERITS, DEFINES, REFERENCES
```

**Qdrant/ChromaDB (Vector Embeddings):**
```
Collections: code_embeddings, doc_embeddings, query_embeddings
```

---

## 📦 Phase 2: Core Code Intelligence (Weeks 3-5)

### 2.1 Code Parsing & Ingestion (Tree-sitter + LangGraph)
- [ ] **Tree-sitter parsers** for: Python, TypeScript, JavaScript, Go, Rust, Java
- [ ] **LangGraph workflow** for repository ingestion:
  ```
  Clone Repo → Parse Files → Extract AST → Build Graph → Generate Embeddings → Store
  ```
- [ ] **Neo4j schema** for code graph:
  - Nodes: Repository, File, Class, Function, Method, Variable, Import
  - Edges: CONTAINS, DEFINES, CALLS, IMPORTS, INHERITS, REFERENCES, DECORATES
- [ ] **Incremental indexing** (watch for file changes, update incrementally)
- [ ] **Symbol extraction** with location (file, line, column)

### 2.2 Vector Embeddings (LlamaIndex + Qdrant/ChromaDB)
- [ ] **Code embeddings**: CodeBERT, UniXcoder, or Voyage Code
- [ ] **Documentation embeddings**: text-embedding-3-large or BGE
- [ ] **Hybrid search**: Vector + Graph traversal + BM25
- [ ] **Chunking strategy**: AST-aware chunking (by function/class)

### 2.3 GraphRAG Pipeline (LangGraph)
```
Query → Intent Classification → 
  ├─> Graph Query (Cypher) → Neo4j
  ├─> Vector Search → Qdrant
  └─> Hybrid Retrieval → Re-rank → LLM Synthesis → Answer
```

**LangGraph Nodes:**
1. `classify_intent` - Route to graph/vector/hybrid
2. `generate_cypher` - LLM generates Cypher from NL
3. `execute_cypher` - Run against Neo4j
4. `vector_search` - Query Qdrant
5. `hybrid_merge` - Combine & rerank (cross-encoder)
6. `synthesize_answer` - LLM generates final answer
7. `generate_followups` - Suggest related questions

---

## 📦 Phase 3: AI Agent & Chat Interface (Weeks 6-8)

### 3.1 Multi-Model AI Router
```python
# Model Router
models = {
    "code_generation": ["claude-3.5-sonnet", "gpt-4o", "deepseek-coder"],
    "code_analysis": ["claude-3.5-sonnet", "gemini-1.5-pro"],
    "quick_chat": ["gemini-1.5-flash", "gpt-4o-mini", "ollama:codellama"],
    "embedding": ["voyage-code-2", "text-embedding-3-large", "bge-large"],
}
```

### 3.2 LangGraph Agent Tools
- [ ] `search_code_graph` - Natural language → Cypher → Results
- [ ] `search_code_vectors` - Semantic code search
- [ ] `get_file_content` - Read file with context
- [ ] `get_symbol_definition` - Go to definition
- [ ] `find_references` - Find all usages
- [ ] `analyze_complexity` - Cyclomatic complexity, etc.
- [ ] `suggest_refactor` - AI-powered refactoring suggestions
- [ ] `generate_tests` - Unit test generation
- [ ] `generate_docs` - Docstring/documentation generation
- [ ] `explain_code` - Step-by-step explanation

### 3.3 Streaming Chat UI (Next.js + Monaco)
- [ ] Chat interface with streaming responses
- [ ] Code blocks with syntax highlighting
- [ ] Inline code references (click to open in editor)
- [ ] File tree navigator
- [ ] Diff view for suggested changes
- [ ] Apply/Reject suggestions
- [ ] Conversation history & branching

---

## 📦 Phase 4: Advanced Features (Weeks 9-12)

### 4.1 Code Graph Visualization
- [ ] **React Flow / D3.js** interactive graph
- [ ] Filter by: file, symbol type, depth, connection type
- [ ] Search & highlight nodes
- [ ] Neighborhood exploration (click to expand)
- [ ] Export as PNG/SVG/GraphML

### 4.2 Repository Analysis Dashboard
- [ ] **Metrics**: Complexity, coupling, cohesion, test coverage
- [ ] **Hotspots**: Frequently changed files, bug-prone areas
- [ ] **Dependencies**: Circular deps, unused code, dead code
- [ ] **Architecture**: Layer violations, module boundaries
- [ ] **Trends**: Velocity, churn, ownership

### 4.3 AI-Powered Workflows
- [ ] **PR Review Agent**: Auto-review PRs with context
- [ ] **Issue-to-Code**: Generate implementation from issue
- [ ] **Refactoring Agent**: Safe automated refactoring
- [ ] **Test Generation**: Unit + integration tests
- [ ] **Documentation Generator**: API docs, README, ADRs

### 4.4 Collaboration Features
- [ ] Shared workspaces
- [ ] Code annotations & comments
- [ ] Team knowledge base (learned patterns)
- [ ] Onboarding assistant for new team members

---

## 📦 Phase 5: Production Hardening (Weeks 13-14)

### 5.1 Observability
- [ ] **Metrics**: Prometheus + Grafana dashboards
- [ ] **Logs**: Structured logging → Loki/Elasticsearch
- [ ] **Traces**: OpenTelemetry → Jaeger/Tempo
- [ ] **Alerts**: PagerDuty/Slack for errors, latency, queue depth

### 5.2 Security
- [ ] Secrets management (Vault/AWS Secrets Manager)
- [ ] Rate limiting & DDoS protection
- [ ] Input validation & sanitization
- [ ] RBAC for projects/teams
- [ ] Audit logging

### 5.3 Performance Optimization
- [ ] Query optimization (Neo4j indexes, Qdrant HNSW tuning)
- [ ] Caching strategy (Redis: queries, embeddings, sessions)
- [ ] Connection pooling
- [ ] Background job optimization (Celery + Redis/RQ)
- [ ] CDN for static assets

### 5.4 Testing Strategy
- [ ] Unit tests (pytest, vitest)
- [ ] Integration tests (Testcontainers)
- [ ] E2E tests (Playwright)
- [ ] Load testing (k6/Locust)
- [ ] Contract testing (Pact)

---

## 🛠️ Tech Stack Decisions

| Component | Choice | Rationale |
|-----------|--------|-----------|
| **Vector DB** | **Qdrant** | Better filtering, payload support, Rust performance |
| **Auth** | **Clerk** | Drop-in, great DX, org/team support, generous free tier |
| **Orchestration** | **LangGraph** | Stateful, cyclic graphs, human-in-the-loop, streaming |
| **Code Parsing** | **Tree-sitter** | Incremental, error-tolerant, 40+ languages |
| **Embeddings** | **Voyage Code 2** / **text-embedding-3-large** | Best code retrieval benchmarks |
| **LLM Router** | **LiteLLM** | Unified interface, fallbacks, cost tracking |
| **Queue** | **Celery + Redis** | Mature, scalable, priority queues |
| **Monitoring** | **Grafana Cloud** | Free tier, unified logs/metrics/traces |

---

## 📁 Project Structure

```
code-intelligence-platform/
├── .github/
│   └── workflows/           # CI/CD pipelines
├── docker/
│   ├── docker-compose.yml   # Local dev stack
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── Dockerfile.worker
├── helm/                    # Kubernetes Helm charts
├── docs/                    # Architecture, API docs, ADRs
├── backend/
│   ├── app/
│   │   ├── api/             # FastAPI routes
│   │   ├── core/            # Config, security, database
│   │   ├── models/          # SQLAlchemy models
│   │   ├── schemas/         # Pydantic schemas
│   │   ├── services/        # Business logic
│   │   ├── workers/         # Celery tasks
│   │   ├── graph/           # Neo4j models, queries
│   │   ├── rag/             # LangGraph pipelines
│   │   ├── parsers/         # Tree-sitter wrappers
│   │   └── ai/              # LLM clients, prompts
│   ├── tests/
│   ├── pyproject.toml
│   └── alembic/
├── frontend/
│   ├── src/
│   │   ├── app/             # Next.js App Router pages
│   │   ├── components/      # React components
│   │   ├── hooks/           # Custom hooks
│   │   ├── lib/             # Utilities, API client
│   │   ├── stores/          # Zustand/Redux stores
│   │   └── types/           # TypeScript types
│   ├── public/
│   ├── package.json
│   └── tailwind.config.ts
├── shared/                  # Shared types, constants
└── scripts/                 # Utility scripts
```

---

## 🚀 Quick Start (Local Development)

```bash
# 1. Clone & setup
git clone <repo>
cd code-intelligence-platform

# 2. Start infrastructure
docker-compose -f docker/docker-compose.yml up -d

# 3. Backend
cd backend
python -m venv venv && source venv/bin/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload

# 4. Frontend
cd frontend
npm install
npm run dev

# 5. Workers (separate terminal)
cd backend
celery -A app.workers.celery_app worker -l info
```

---

## 📊 Success Metrics

| Metric | Target |
|--------|--------|
| Code search latency (p95) | < 500ms |
| Chat response time (first token) | < 1s |
| Indexing speed | > 1000 files/min |
| Graph query latency (p95) | < 200ms |
| Uptime | 99.9% |
| Test coverage | > 80% |

---

## 🗓️ Timeline Summary

| Phase | Weeks | Deliverable |
|-------|-------|-------------|
| 1. Foundation | 1-2 | Infra, Auth, Basic API/UI |
| 2. Code Intelligence | 3-5 | Parsing, Graph, Vectors, GraphRAG |
| 3. AI Agent & Chat | 6-8 | Multi-tool agent, Streaming UI |
| 4. Advanced Features | 9-12 | Visualization, Analytics, Workflows |
| 5. Production | 13-14 | Observability, Security, Performance |

**Total: ~14 weeks (3.5 months) for MVP + advanced features**

---

## 🎯 Next Steps

1. **Finalize tech choices** - Confirm Qdrant vs ChromaDB, Clerk vs NextAuth
2. **Set up repos** - Create GitHub org/repos with branch protection
3. **Provision cloud** - AWS/GCP project, managed services (RDS, ElastiCache, etc.)
4. **Kick off Phase 1** - Start with docker-compose + FastAPI + Next.js scaffolding

---

*Document version: 1.0*  
*Last updated: 2025-07-16*