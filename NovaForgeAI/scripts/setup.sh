#!/usr/bin/env bash
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$DIR"

echo "=== NovaForge AI Setup ==="
echo ""

# Check prerequisites
echo "Checking prerequisites..."

check_cmd() {
    if ! command -v "$1" &> /dev/null; then
        echo "Error: $1 is not installed. Please install it first."
        exit 1
    fi
    echo "  ✓ $1 found"
}

check_cmd docker
check_cmd node
check_cmd python3

NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VERSION" -lt 18 ]; then
    echo "Error: Node.js >= 18 required (found v$(node -v))"
    exit 1
fi
echo "  ✓ Node.js version $(node -v)"

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(echo "$PYTHON_VERSION" | cut -d'.' -f1)" -lt 3 ] || { [ "$(echo "$PYTHON_VERSION" | cut -d'.' -f1)" -eq 3 ] && [ "$(echo "$PYTHON_VERSION" | cut -d'.' -f2)" -lt 11 ]; }; then
    echo "Error: Python >= 3.11 required (found $PYTHON_VERSION)"
    exit 1
fi
echo "  ✓ Python $PYTHON_VERSION"

# Check Docker Compose
if docker compose version &> /dev/null; then
    echo "  ✓ docker compose found"
elif docker-compose --version &> /dev/null; then
    echo "  ✓ docker-compose found"
    DOCKER_COMPOSE_LEGACY=true
else
    echo "Error: docker compose not found"
    exit 1
fi

echo ""

# Create .env from example if not exists
if [ ! -f .env ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "  ✓ .env created"
    echo "  ⚠  Please edit .env and fill in your API keys and secrets"
else
    echo "  ✓ .env already exists"
fi

# Install frontend dependencies
echo ""
echo "Installing frontend dependencies..."
cd frontend
npm install
cd "$DIR"
echo "  ✓ Frontend dependencies installed"

# Create backend virtual environment and install dependencies
echo ""
echo "Setting up backend Python environment..."
if [ ! -d backend/.venv ]; then
    python3 -m venv backend/.venv
    echo "  ✓ Virtual environment created"
fi

source backend/.venv/bin/activate
pip install --upgrade pip
pip install -e backend/
deactivate
echo "  ✓ Backend dependencies installed"

# Start development stack
echo ""
echo "Starting Docker Compose development stack..."
if [ "${DOCKER_COMPOSE_LEGACY:-false}" = true ]; then
    docker-compose -f docker/dev/docker-compose.yml up -d
else
    docker compose -f docker/dev/docker-compose.yml up -d
fi
echo "  ✓ Development stack started"

echo ""
echo "=== Setup Complete ==="
echo ""
echo "  Frontend:  http://localhost:3000"
echo "  Backend:   http://localhost:8000"
echo "  API Docs:  http://localhost:8000/docs"
echo ""
echo "  PostgreSQL: localhost:5432"
echo "  Neo4j:      localhost:7687 (bolt) / localhost:7474 (browser)"
echo "  Qdrant:     localhost:6333"
echo "  Redis:      localhost:6379"
echo ""
echo "To stop: docker compose -f docker/dev/docker-compose.yml down"
echo "To view logs: docker compose -f docker/dev/docker-compose.yml logs -f"
