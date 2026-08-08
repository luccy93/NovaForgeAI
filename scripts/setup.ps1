#!/usr/bin/env pwsh
param(
    [switch]$NoDocker
)

$ErrorActionPreference = "Stop"
$DIR = Split-Path -Parent $PSScriptRoot | Resolve-Path
Set-Location $DIR

Write-Host "=== NovaForge AI Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check prerequisites
Write-Host "Checking prerequisites..." -ForegroundColor Yellow

function Check-Command($cmd) {
    try {
        $null = Get-Command $cmd -ErrorAction Stop
        Write-Host "  ✓ $cmd found" -ForegroundColor Green
        return $true
    } catch {
        Write-Host "  ✗ $cmd not found" -ForegroundColor Red
        return $false
    }
}

$allOk = $true

if (-not (Check-Command "docker")) { $allOk = $false }
if (-not (Check-Command "node")) { $allOk = $false }
if (-not (Check-Command "python")) { $allOk = $false }

# Check Node version
$nodeVersion = node -v
$nodeMajor = [int]($nodeVersion -replace 'v', '' -split '\.')[0]
if ($nodeMajor -lt 18) {
    Write-Host "  ✗ Node.js >= 18 required (found $nodeVersion)" -ForegroundColor Red
    $allOk = $false
} else {
    Write-Host "  ✓ Node.js $nodeVersion" -ForegroundColor Green
}

# Check Python version
$pyVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
$pyMajor, $pyMinor = $pyVersion -split '\.' | ForEach-Object { [int]$_ }
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 11)) {
    Write-Host "  ✗ Python >= 3.11 required (found $pyVersion)" -ForegroundColor Red
    $allOk = $false
} else {
    Write-Host "  ✓ Python $pyVersion" -ForegroundColor Green
}

# Check Docker Compose
try {
    $null = Get-Command "docker" -ErrorAction Stop
    $composeCheck = docker compose version 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✓ docker compose found" -ForegroundColor Green
    } else {
        $composeCheck2 = docker-compose --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Write-Host "  ✓ docker-compose found" -ForegroundColor Green
            $script:DOCKER_COMPOSE_LEGACY = $true
        } else {
            Write-Host "  ✗ docker compose not found" -ForegroundColor Red
            $allOk = $false
        }
    }
} catch {
    # docker may not be installed, but we already checked
}

if (-not $allOk) {
    Write-Host ""
    Write-Host "Please install missing prerequisites and try again." -ForegroundColor Red
    exit 1
}

Write-Host ""

# Create .env from example if not exists
if (-not (Test-Path ".env")) {
    Write-Host "Creating .env from .env.example..." -ForegroundColor Yellow
    Copy-Item ".env.example" ".env"
    Write-Host "  ✓ .env created" -ForegroundColor Green
    Write-Host "  ⚠  Please edit .env and fill in your API keys and secrets" -ForegroundColor Yellow
} else {
    Write-Host "  ✓ .env already exists" -ForegroundColor Green
}

# Install frontend dependencies
Write-Host ""
Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location "$DIR\frontend"
npm install
Set-Location $DIR
Write-Host "  ✓ Frontend dependencies installed" -ForegroundColor Green

# Create backend virtual environment and install dependencies
Write-Host ""
Write-Host "Setting up backend Python environment..." -ForegroundColor Yellow
if (-not (Test-Path "backend\.venv")) {
    python -m venv "backend\.venv"
    Write-Host "  ✓ Virtual environment created" -ForegroundColor Green
}

$venvActivate = "backend\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    & $venvActivate
    python -m pip install --upgrade pip
    python -m pip install -e "backend/"
    deactivate
} else {
    Write-Host "  ✗ Could not find virtual environment activate script" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Backend dependencies installed" -ForegroundColor Green

# Start development stack
if (-not $NoDocker) {
    Write-Host ""
    Write-Host "Starting Docker Compose development stack..." -ForegroundColor Yellow
    if ($script:DOCKER_COMPOSE_LEGACY) {
        docker-compose -f docker/dev/docker-compose.yml up -d
    } else {
        docker compose -f docker/dev/docker-compose.yml up -d
    }
    Write-Host "  ✓ Development stack started" -ForegroundColor Green
}

Write-Host ""
Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Frontend:  http://localhost:3000"
Write-Host "  Backend:   http://localhost:8000"
Write-Host "  API Docs:  http://localhost:8000/docs"
Write-Host ""
Write-Host "  PostgreSQL: localhost:5432"
Write-Host "  Neo4j:      localhost:7687 (bolt) / localhost:7474 (browser)"
Write-Host "  Qdrant:     localhost:6333"
Write-Host "  Redis:      localhost:6379"
Write-Host ""
Write-Host "To stop: docker compose -f docker/dev/docker-compose.yml down"
Write-Host "To view logs: docker compose -f docker/dev/docker-compose.yml logs -f"
