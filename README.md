# NovaForge AI

**AI-powered code assistant with 3D code visualization**

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (React/Three.js)          │
│          3D Code Visualization + Web UI              │
├─────────────────────────────────────────────────────┤
│                    Backend (FastAPI)                  │
│   API Gateway → Agent Orchestrator → AI Services     │
├─────────────────────────────────────────────────────┤
│                   Agent Layer                         │
│  Code Review │ Doc Gen │ Test Gen │ Search │ Chat    │
├─────────────────────────────────────────────────────┤
│                  Databases                            │
│  PostgreSQL │ Redis │ Vector DB (Qdrant)             │
└─────────────────────────────────────────────────────┘
```

## Quick Start (Docker)

```bash
docker compose -f docker/dev/docker-compose.yml up -d
```

The API will be available at `http://localhost:8000` and the frontend at `http://localhost:3000`.

For production:
```bash
docker compose -f docker/prod/docker-compose.yml up -d
```

## Development Setup

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### CLI

```bash
cd cli
pip install -e .
novaforge --help
```

## Project Structure

```
NovaForgeAI/
├── backend/                 # FastAPI backend (Python 3.12)
│   ├── app/
│   │   ├── api/            # REST endpoints (chat, repos, agents, code, auth)
│   │   ├── core/           # Config, database engine
│   │   ├── models/         # SQLAlchemy models (User, Org, Repo, Conversation, Message)
│   │   ├── schemas/        # Pydantic schemas
│   │   └── services/       # Embeddings, VectorStore, GraphStore, RAG, CodeAnalysis
│   └── pyproject.toml
├── frontend/                # Next.js 16 + Three.js landing page
├── agents/                  # AI Multi-Agent System
│   ├── base.py, planner.py, reviewer.py, security.py
│   ├── testing.py, documentation.py, deployment.py
│   └── orchestrator.py
├── cli/                     # Terminal CLI tool (Click + Rich)
├── database/                # PostgreSQL 16 schema DDL
├── docker/                  # Dockerfiles + Compose (dev/prod)
├── github/                  # GitHub App manifest + webhook handler
├── kubernetes/              # K8s manifests (deployments, statefulsets, ingress)
├── scripts/                 # setup.sh / setup.ps1
├── vscode-extension/        # VS Code extension
├── tests/                   # Test directories
├── .env.example
├── .gitignore
└── README.md
```

## Available Commands

### CLI

| Command | Description |
|---------|-------------|
| `novaforge analyze <file>` | Analyze a code file |
| `novaforge ask <question>` | Ask AI a question |
| `novaforge agents` | List available agents |
| `novaforge run <agent> <input>` | Run a specific agent |
| `novaforge status` | Check API health |

### VS Code Extension

| Command | Keybinding |
|---------|-----------|
| NovaForge: Explain Code | `Ctrl+Shift+E` / `Cmd+Shift+E` |
| NovaForge: Review Code | — |
| NovaForge: Open 3D Code View | — |
| NovaForge: Ask AI | `Ctrl+Shift+A` / `Cmd+Shift+A` |
| NovaForge: Generate Tests | — |

## Documentation

- [API Reference](https://docs.novaforge.ai/api)
- [Architecture Guide](https://docs.novaforge.ai/architecture)
- [Deployment Guide](https://docs.novaforge.ai/deployment)

## Volume 32 - Multimodal AI & Computer Vision

A multimodal ingestion, analysis and retrieval platform for text, documents (PDF),
images, architecture diagrams, video and audio.

### Components (`backend/app/multimodal/`)

| Module | Purpose |
|--------|---------|
| `security.py` | Upload validation (magic bytes, size, zip-bomb), SSRF guard, processing sandbox, prompt-injection scanner |
| `ocr.py` | Pluggable OCR chain (Tesseract / PaddleOCR / Cloud Vision) with caching |
| `pdf_parser.py` | Stream-based PDF text extraction (no xref traversal) - Tj/TJ ops, Flate/ASCIIHex |
| `images.py` | Image stats, OCR, diagram parsing (box + directed-arrow detection), visual-regression compare |
| `docs.py` | Heading-anchored semantic chunking, table extraction (PDF grid / openpyxl / CSV) |
| `video.py` | ffmpeg frame sampling, HSV scene-change detection, OCR on scene frames |
| `audio.py` | Transcription (whisper / OpenAI / Google), topic + decision extraction |
| `index_store.py` | Embedding registry, Qdrant vector index with in-memory fallback + JSON persistence |
| `rag.py` | Cross-modal retrieval with citation-grounded answers; Neo4j knowledge-graph interlink |
| `screenshots.py` | URL screenshot capture (Playwright/Selenium, honest unavailability), SSRF-guarded; visual-comparison persistence (VRT verdicts) |
| `pipeline.py` | Asset lifecycle orchestrator (validate -> sandbox -> extract -> index -> KG) |
| `service.py` | `multimodal` service registered in the volume registry |

### CLI

```bash
python -m app.novaforge_cli health
python -m app.novaforge_cli multimodal ingest org-demo path/to/file.png
python -m app.novaforge_cli multimodal search org-demo "my query"
python -m app.novaforge_cli multimodal answer org-demo "my question"
python -m app.novaforge_cli multimodal assets org-demo
python -m app.novaforge_cli multimodal jobs org-demo
python -m app.novaforge_cli multimodal usage
python -m app.novaforge_cli multimodal vision path/to/image.png
python -m app.novaforge_cli multimodal screenshot org-demo https://example.com 1280x800
python -m app.novaforge_cli multimodal compare org-demo <baseline_id> <candidate_id>
python -m app.novaforge_cli multimodal ledger [org-demo]
```

### HTTP API (flat `app/api.py` router, same convention as Lakehouse)

```
POST   /multimodal/ingest                    raw bytes body
POST   /multimodal/upload                    multipart file
GET    /multimodal/ingest/{job_id}           job status
GET    /multimodal/assets                    list assets (?organization_id=&modality=)
DELETE /multimodal/assets/{asset_id}
GET    /multimodal/search                    ?organization_id=&q=
GET    /multimodal/answer                    ?organization_id=&q=
GET    /multimodal/usage
GET    /multimodal/ledger                cost ledger (?organization_id=&limit=)
POST   /multimodal/screenshot            ?organization_id=&url=&viewport=
GET    /multimodal/screenshots           screenshot records
GET    /multimodal/comparisons           recorded VRT verdicts
GET    /multimodal/compare/{baseline_id}/{candidate_id}
GET    /multimodal/health
```

### Behavior

- Every asset and search is tenant-scoped (`organization_id`).
- All capability degradations are honest: captions only from non-heuristic
  providers, video/audio report `available: false` with a reason when binaries
  or models are missing, and a down Qdrant/Neo4j never breaks ingestion
  (in-memory fallback + `written: false` KG reports).
- Executables, spoofed MIME types, oversized uploads, zip-bombs and prompt
  injection are rejected at the pipeline boundary.
- Screenshot URLs pass an SSRF guard before any capture; without a headless
  browser (Playwright/Selenium) capture reports `available: false` with an
  explicit reason. Compare verdicts persist to a comparison log.
- Cost tracking is honest end to end: every paid operation (vision/OCR/LLM)
  appends to the per-tenant cost ledger; free or local-heuristic paths record
  `cost_usd: 0.0`.
- Memory index persists to `data/multimodal/index.json` so one-shot CLI
  processes share state with the API server.

### Schema migration

```bash
cd backend
alembic upgrade head    # creates the 18 multimodal_* tables (see alembic/versions/0001_multimodal.py)
```

### Tests

```bash
cd backend
python -m pytest ../tests/backend/test_multimodal.py --confcutdir=../tests/backend
```

Note: `tests/backend/test_api.py`, `test_backend_features.py`,
`test_platform.py` and the PostgreSQL/Redis/Neo4j/Qdrant integration tests fail
when the external services or the `create_app` app factory are unavailable -
these predate Volume 32.

## Volume 33 - Automation, RPA & Intelligent Automation

A secure enterprise automation platform: declarative, versioned workflows
with a typed DSL, DAG validation, an execution engine with retries,
checkpoints, compensation and human approvals, plus policy-gated tools,
schedulers, webhooks, an event bus, artifacts, cost controls and an honest
AI-generation pipeline. Registered as the `automation` volume (10th service).

### Components (`backend/app/automation/`)

| Module | Purpose |
|--------|---------|
| `workflow.py` | `WorkflowSpec`/`WorkflowStep`/`RetryPolicy` models, lifecycle (draft -> published -> paused/deprecated/archived), tenant-scoped `WorkflowStore` with versioning + rollback |
| `dsl.py` | Strongly typed workflow DSL (dict/JSON -> `WorkflowSpec`) + `WorkflowValidator` (schema, trigger, policy surface) |
| `dag.py` | DAG build/validation: cycles, unknown deps, duplicates, execution order (Kahn) |
| `engine.py` | `WorkflowEngine`: gates -> approvals -> ordered step execution with retries/timeouts -> checkpoints -> compensation on failure |
| `retry.py` | Capped exponential backoff, transient-error classification |
| `checkpoint.py` | Persisted per-step checkpoints + resume plans |
| `compensation.py` | Rollback plans (reverse order) + execution, operator-review fallback |
| `approvals.py` | Pending/approved/rejected/expired/auto-approved records (HMAC-free, tenant-scoped JSON) |
| `executions.py` | Persisted execution records + lifecycle tracker |
| `automation_policy.py` | Risk classification (dangerous actions always escalate to high), action/domain allowlists, lockdown mode, trigger blocking |
| `dryrun.py` | Dry-run gate: DAG + policy + approval + cost estimates, `executed: false` |
| `simulator.py` | Step-by-step simulation report (no side effects) |
| `triggers.py` | Trigger parsing (manual/schedule/webhook/event/github/gitlab/metric) + `DispatchHub` |
| `scheduler.py` | 5-field cron parser + due-rule tick |
| `events.py` | Typed pub/sub event bus with persistent log |
| `webhooks.py` | HMAC-SHA256 signed webhook receiver (timestamp + signature verify) |
| `tools.py` | `ToolRegistry` + built-ins (read/search/http/parse/log/report/preview); SSRF-guarded HTTP |
| `terminal.py` | Sandboxed terminal: never runs on host without a remote runner; risk engine + approval |
| `browser.py` | Remote-browser agent (navigate/click/fill/screenshot); honest unavailability |
| `infra.py` | Plan/apply backends; apply requires approved human approval |
| `cicd.py` | Check/merge/release via platform client; mutations require approval |
| `artifacts.py` | Content-addressed (sha256) artifact store |
| `cost.py` | Per-org budgets, per-run/per-step cost attribution |
| `knowledge.py` | Runbook/troubleshooting knowledge store |
| `templates.py` | 6 curated templates (CI, deploy, incident, security, data, test) |
| `marketplace.py` | Publish/import validated workflows |
| `ai_steps.py` | AI workflow generation: dry-run gated, never exposes secrets, honest unavailable without an LLM |
| `gateway.py` | `AutomationGateway`: single facade wiring engine + policy + cost + triggers + bus |
| `workers.py` | Thread-pool worker queue for run requests |
| `service.py` | `automation` service registered in the volume registry |

### CLI

```bash
python -m app.novaforge_cli automation templates
python -m app.novaforge_cli automation define org-demo definition.json
python -m app.novaforge_cli automation list org-demo
python -m app.novaforge_cli automation dryrun org-demo wf_ci
python -m app.novaforge_cli automation publish org-demo wf_ci
python -m app.novaforge_cli automation run org-demo wf_ci '{"inputs":{}}'
python -m app.novaforge_cli automation execs org-demo
python -m app.novaforge_cli automation approve org-demo wf_ci step_id approve
python -m app.novaforge_cli automation tick
python -m app.novaforge_cli automation ai "deploy the release"
```

### HTTP API (flat `app/api.py` router, same convention)

```
POST   /automation/workflows                    define (JSON body, ?org_id=)
GET    /automation/workflows                    list (?org_id=)
GET    /automation/workflows/{id}/dry-run       dry-run gate (?org_id=)
POST   /automation/workflows/{id}/publish       (?org_id=)
POST   /automation/workflows/{id}/run           execute (?org_id=, inputs)
GET    /automation/executions                   (?org_id=&limit=)
GET    /automation/executions/{execution_id}    (?org_id=)
POST   /automation/approvals/{workflow}/{step}  ?decision=approved|rejected
POST   /automation/ai/generate                  ?prompt=&org_id=
POST   /automation/webhook/{path}               HMAC-signed (?timestamp=&signature=)
POST   /automation/tick
GET    /automation/health
```

### Behavior

- Every workflow, execution, approval, checkpoint, artifact and cost entry is
  tenant-scoped (`organization_id`); store reads refuse cross-tenant access.
- Nothing ever executes untrusted commands on the host: terminal/browser tools
  report `available: false` with a reason unless a remote sandbox backend is
  configured, and `http`/screenshot URLs pass an SSRF guard.
- High-risk actions (terminal, browser, infra, deploy, cicd and any action on
  the policy denylist) always require an approved human (or policy
  auto-approved) request before the engine runs them; runs blocked on
  approvals persist as `awaiting_approval` and create the pending requests.
- AI-generated workflows pass the same pipeline as hand-written ones: DSL
  parse -> DAG validation -> policy dry run -> approval -> execution, and are
  rejected by the dry-run gate when invalid; without an LLM callback, AI
  generation reports `available: false` honestly.
- Dry runs and simulations never execute; every execution gets an
  `execution_id` and a persisted record with per-step results, timing and
  audit trail; failures trigger compensation plans in reverse order.
- Schedules tick on cron expressions; webhooks require a valid HMAC-SHA256
  signature within the timestamp tolerance window.
- All JSON stores live under `data/automation/` so one-shot CLI processes
  share state with the API server.

### Schema migration

```bash
cd backend
alembic upgrade head    # adds the 13 automation_* tables (see alembic/versions/0002_automation.py)
```

### Tests

```bash
cd backend
python -m pytest ../tests/backend/test_automation.py --confcutdir=../tests/backend
```

66 tests cover the DSL, DAG, store versioning, retries, checkpoints,
compensation, approvals, engine gates, policy, dry run, scheduler, triggers,
webhooks (HMAC), cost budgets, tool honesty (terminal/HTTP/SSRF), gateway
end-to-end flow and the registered service. Combined with Volume 32:
`python -m pytest ../tests/backend/test_multimodal.py ../tests/backend/test_automation.py --confcutdir=../tests/backend` (137 passing).

