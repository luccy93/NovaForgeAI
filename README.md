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

