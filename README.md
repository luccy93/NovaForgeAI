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
