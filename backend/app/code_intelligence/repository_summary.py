"""Repository Summary Generator — structured metadata overview of a repository.

Generates a comprehensive profile including language distribution, frameworks,
services, APIs, databases, queues, deployment config, test infrastructure,
architecture overview, monorepo structure, entry points, and size/complexity
maturity indicators.  Every detection result carries a confidence score.
"""

from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeFile, CodeHistory, CodeIndex, CodeImport, CodeMetrics,
    CodeOwnership, CodeSmell, CodeSymbol, CodeTest, SymbolType,
)

logger = logging.getLogger(__name__)
GENERATION_VERSION = "1.0.0"

# ── Extension → language mapping ────────────────────────────────────────

EXT_TO_LANG: dict[str, str] = {}
for _l, _e in {
    "python": [".py", ".pyi"], "javascript": [".js", ".mjs", ".cjs"],
    "typescript": [".ts", ".tsx", ".jsx"], "java": [".java"], "go": [".go"],
    "rust": [".rs"], "ruby": [".rb", ".rake"], "php": [".php"],
    "c": [".c", ".h"], "cpp": [".cpp", ".cxx", ".cc", ".hpp"],
    "c_sharp": [".cs"], "kotlin": [".kt", ".kts"], "scala": [".scala"],
    "swift": [".swift"], "dart": [".dart"], "shell": [".sh", ".bash", ".zsh"],
    "sql": [".sql"],     "yaml": [".yaml", ".yml"], "json": [".json"], "toml": [".toml"],
    "markdown": [".md", ".rst", ".txt"], "html": [".html", ".htm"],
    "css": [".css", ".scss", ".less"], "proto": [".proto"],
}.items():
    for _x in _e:
        EXT_TO_LANG[_x] = _l

# ── Framework adapters ──────────────────────────────────────────────────

FRAMEWORK_ADAPTERS: list[dict] = [
    {"name": "FastAPI", "lang": "python", "cat": "backend",
     "imp": [r"\bfrom\s+fastapi\b", r"\bimport\s+fastapi\b"],
     "cfg": [r"\bFastAPI\s*\("], "files": ["main.py", "app.py"]},
    {"name": "Django", "lang": "python", "cat": "backend",
     "imp": [r"\bfrom\s+django\b"],
     "cfg": [r"\bINSTALLED_APPS\b", r"\bWSGI_APPLICATION\b"],
     "files": ["settings.py", "wsgi.py", "asgi.py", "manage.py"]},
    {"name": "Flask", "lang": "python", "cat": "backend",
     "imp": [r"\bfrom\s+flask\b"],
     "cfg": [r"\bFlask\s*\("], "files": ["app.py", "routes.py"]},
    {"name": "Celery", "lang": "python", "cat": "queue",
     "imp": [r"\bfrom\s+celery\b"],
     "cfg": [r"\b@shared_task\b"], "files": ["celery.py", "tasks.py"]},
    {"name": "SQLAlchemy", "lang": "python", "cat": "orm",
     "imp": [r"\bfrom\s+sqlalchemy\b"],
     "cfg": [r"\bColumn\s*\("], "files": ["models.py"]},
    {"name": "Pydantic", "lang": "python", "cat": "validation",
     "imp": [r"\bfrom\s+pydantic\b"],
     "cfg": [r"\bBaseModel\s*\("], "files": ["schemas.py"]},
    {"name": "Express", "lang": "javascript", "cat": "backend",
     "imp": [r"""require\s*\(\s*['"]express['"]\s*\)""", r"""from\s+['"]express['"]"""],
     "cfg": [r"\bexpress\s*\(\s*\)"], "files": ["server.js", "app.js"]},
    {"name": "NestJS", "lang": "javascript", "cat": "backend",
     "imp": [r"""from\s+['"]@nestjs/"""],
     "cfg": [r"\bNestFactory\.create\b"], "files": ["main.ts"]},
    {"name": "React", "lang": "javascript", "cat": "frontend",
     "imp": [r"""from\s+['"]react['"]"""],
     "cfg": [r"\bcreateRoot\b"], "files": ["App.jsx", "App.tsx"]},
    {"name": "Vue", "lang": "javascript", "cat": "frontend",
     "imp": [r"""from\s+['"]vue['"]"""],
     "cfg": [r"\bdefineComponent\b"], "files": ["App.vue"]},
    {"name": "Angular", "lang": "typescript", "cat": "frontend",
     "imp": [r"""from\s+['"]@angular/"""],
     "cfg": [r"\b@Component\s*\("], "files": ["angular.json"]},
    {"name": "Next.js", "lang": "javascript", "cat": "fullstack",
     "imp": [r"""from\s+['"]next/"""],
     "cfg": [r"\bnext\.config\."], "files": ["next.config.js"]},
    {"name": "Spring Boot", "lang": "java", "cat": "backend",
     "imp": [r"\bimport\s+org\.springframework\b"],
     "cfg": [r"\b@SpringBootApplication\b"], "files": ["Application.java"]},
    {"name": "Gin", "lang": "go", "cat": "backend",
     "imp": [r"\bgithub\.com/gin-gonic/gin\b"],
     "cfg": [r"\bgin\.Default\(\)"], "files": ["main.go"]},
]

# ── Entry-point / API / DB / Queue / Deployment regex constants ─────────

EP_PATTERNS: dict[str, dict[str, re.Pattern]] = {
    "http_server": {
        "python": re.compile(r"(?:app\.run\(|uvicorn\.run|gunicorn|\.serve_forever\()"),
        "javascript": re.compile(r"(?:app\.listen\(|server\.listen\(|createServer\()"),
        "java": re.compile(r"(?:SpringApplication\.run|@SpringBootApplication)"),
        "go": re.compile(r"(?:http\.ListenAndServe|\.ListenAndServe\(|gin\.Default|echo\.New)"),
        "ruby": re.compile(r"(?:Rails\.application\.run|Sinatra::Application\.run)"),
        "php": re.compile(r"(?:artisan\s+serve)"),
    },
    "cli": {
        "python": re.compile(r"(?:@click\.command|argparse\.ArgumentParser|if\s+__name__\s*==\s*['\"]__main__['\"]|def\s+main\s*\(\))"),
        "javascript": re.compile(r"(?:#!/usr/bin/env\s+node|\.command\s*\(|yargs\.command)"),
        "go": re.compile(r"(?:flag\.Parse\(\)|cobra\.Command|os\.Args)"),
    },
    "worker": {
        "python": re.compile(r"(?:@celery\.task|@shared_task|def\s+worker|class\s+\w+Task)"),
        "javascript": re.compile(r"(?:Bull\(|new\s+Queue\(|process\s*\()"),
    },
    "scheduled_job": {
        "python": re.compile(r"(?:@schedule|schedule\.|cron|periodic_task|APScheduler|apscheduler)"),
        "javascript": re.compile(r"(?:cron\.\w+|node-cron|node-schedule|setInterval)"),
    },
}

API_PATTERNS: dict[str, re.Pattern] = {
    "rest_fastapi": re.compile(r"@(?:app|router)\.(?:get|post|put|delete|patch|head)\s*\(\s*['\"]([^'\"]+)['\"]"),
    "rest_flask": re.compile(r"@(?:app|bp)\.(?:route|get|post|put|delete)\s*\(\s*['\"]([^'\"]+)['\"]"),
    "rest_django": re.compile(r"path\s*\(\s*['\"]([^'\"]+)['\"]"),
    "rest_express": re.compile(r"(?:app|router)\.(?:get|post|put|delete|patch|use)\s*\(\s*['\"]([^'\"]+)['\"]"),
    "rest_nestjs": re.compile(r"@(?:Get|Post|Put|Delete|Patch)\s*\(\s*['\"]([^'\"]*)['\"]\s*\)"),
    "rest_spring": re.compile(r"@(?:GetMapping|PostMapping|PutMapping|DeleteMapping)\s*\(\s*(?:value\s*=\s*)?['\"]([^'\"]+)['\"]"),
    "rest_gin": re.compile(r"\.(?:GET|POST|PUT|DELETE|PATCH|Group)\s*\(\s*['\"]([^'\"]+)['\"]"),
    "graphql": re.compile(r"@(?:Query|Mutation|Subscription|Resolver)\s*\("),
    "grpc": re.compile(r"(?:service\s+\w+\s*\{|rpc\s+\w+\s*\(|grpc\.service)"),
    "event": re.compile(r"(?:@event_handler|@on_event|@subscribe|addEventListener|\.on\s*\(\s*['\"](\w+)['\"]\s*\))"),
    "webhook": re.compile(r"(?:webhook|@webhook|handle_webhook|verify_webhook)"),
}

DB_PATTERNS: dict[str, re.Pattern] = {
    "orm_model": re.compile(r"(?:class\s+\w+\s*\(\s*(?:Base|db\.Model|Model)\s*\)|@Entity|@Table\s*\()"),
    "migration": re.compile(r"(?:alembic|migration|migrate|schema\.py|versions?/\d)"),
    "sqlalchemy_model": re.compile(r"(?:__tablename__|Column\s*\(|mapped_column|relationship\s*\()"),
    "django_model": re.compile(r"(?:class\s+\w+\s*\(\s*models\.Model|models\.\w+Field)"),
    "prisma_schema": re.compile(r"(?:model\s+\w+\s*\{|datasource\s+\w+\s*\{)"),
    "database_url": re.compile(r"(?:DATABASE_URL|DB_URL|DB_HOST|MYSQL_URL|POSTGRES_URL|MONGO_URL|REDIS_URL|connection_string|jdbc:|mysql://|postgres(?:ql)?://|mongodb://|redis://)"),
}

QUEUE_PATTERNS: dict[str, re.Pattern] = {
    "celery_task": re.compile(r"(?:@shared_task|@celery\.task|\.delay\(|\.apply_async\()"),
    "bull_queue": re.compile(r"(?:new\s+Bull\s*\(|Queue\s*\(\s*['\"]|\.process\s*\()"),
    "kafka_producer": re.compile(r"(?:KafkaProducer|producer\.send|kafkaProducer)"),
    "kafka_consumer": re.compile(r"(?:KafkaConsumer|consumer\.poll|consumer\.subscribe)"),
    "rabbitmq": re.compile(r"(?:pika\.|amqp\.|channel\.basic_publish|channel\.basic_consume)"),
    "redis_queue": re.compile(r"(?:redis\.(?:lpush|rpop|blpop|publish)|\.lpush\(|\.rpop\()"),
}

DEPLOY_FILES: dict[str, str] = {
    "Dockerfile": "docker", "docker-compose.yml": "docker_compose",
    "docker-compose.yaml": "docker_compose", ".env": "env_template",
    ".env.example": "env_template", ".dockerignore": "docker", "Makefile": "build",
}
K8S_PATTERN = re.compile(r"(?:kind:\s+(?:Deployment|Service|ConfigMap|Secret|Ingress|StatefulSet|CronJob))")
CICD_PATHS: dict[str, str] = {
    ".github/workflows": "github_actions", ".gitlab-ci.yml": "gitlab_ci",
    "Jenkinsfile": "jenkins", ".circleci/config.yml": "circle_ci",
    ".travis.yml": "travis_ci", "azure-pipelines.yml": "azure_pipelines",
    "cloudbuild.yaml": "cloud_build",
}

WORKSPACE_CONFIGS: dict[str, re.Pattern] = {
    "package.json": re.compile(r""""workspaces"\s*:"""),
    "lerna.json": re.compile(r""""packages"\s*:"""),
    "pnpm-workspace.yaml": re.compile(r"""packages:"""),
    "turbo.json": re.compile(r""""pipeline"\s*:"""),
    "nx.json": re.compile(r"""(?i)"projects"\s*:"""),
    "rush.json": re.compile(r""""projects"\s*:"""),
    "Cargo.toml": re.compile(r"""\[workspace\]"""),
    "go.work": re.compile(r"""^use\s+"""),
}

LAYER_SIGNALS: dict[str, dict] = {
    "presentation": {
        "fp": [r"(?:components?|views?|pages?|screens?|templates?)", r"\.(?:jsx|tsx|vue|svelte|html)$"],
        "sp": [r"\b(?:Component|View|Page|Screen|Template)\b"],
    },
    "business_logic": {
        "fp": [r"(?:services?|handlers?|usecases?|managers?)"],
        "sp": [r"\b(?:Service|Handler|UseCase|Interactor|Manager)\b"],
    },
    "data_access": {
        "fp": [r"(?:repositories?|dao|dal|models?|entities?|migrations?)", r"(?:database|db|orm|store)"],
        "sp": [r"\b(?:Repository|DAO|Model|Entity|Schema|Migration)\b"],
    },
    "infrastructure": {
        "fp": [r"(?:config|middleware|logging|auth|cache|queue|worker)"],
        "sp": [r"\b(?:Middleware|Config|Cache|Logger|Auth|Queue|Worker)\b"],
    },
}

MATURITY_THRESHOLDS = {
    "immature": (20, 50, 10, 1), "early": (50, 200, 50, 3),
    "growing": (200, 1000, 200, 5), "mature": (500, 5000, 500, 10),
    "established": (2000, 20000, 2000, 20),
}
SIZE_BUCKETS = {"tiny": 500, "small": 5000, "medium": 20000, "large": 100000, "very_large": 500000}


# ═══════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LanguageInfo:
    language: str; file_count: int; line_count: int; proportion: float
    extensions: list[str] = field(default_factory=list)

@dataclass
class FrameworkInfo:
    name: str; category: str; language: str; confidence: float
    evidence: list[str] = field(default_factory=list)

@dataclass
class EntryPointInfo:
    type: str; file_path: str; file_id: Optional[str] = None
    language: Optional[str] = None; line: Optional[int] = None
    evidence: str = ""; confidence: float = 0.0

@dataclass
class ServiceInfo:
    name: str; file_count: int; primary_language: str
    has_entry_point: bool; has_config: bool; has_tests: bool
    has_models: bool; confidence: float
    sample_files: list[str] = field(default_factory=list)

@dataclass
class APIInfo:
    type: str; route: str; method: str; file_path: str
    language: Optional[str] = None; line: Optional[int] = None
    evidence: str = ""; confidence: float = 0.0

@dataclass
class DatabaseInfo:
    type: str; db_engine: str; file_path: str
    language: Optional[str] = None; line: Optional[int] = None
    match_count: int = 0; evidence: str = ""; confidence: float = 0.0

@dataclass
class QueueInfo:
    type: str; role: str; file_path: str; language: Optional[str] = None
    line: Optional[int] = None; match_count: int = 0; confidence: float = 0.0

@dataclass
class DeploymentConfigInfo:
    type: str; file_path: str; file_name: str
    language: Optional[str] = None; size_bytes: Optional[int] = None

@dataclass
class TestInfrastructureInfo:
    test_file_count: int; total_test_count: int
    frameworks: dict[str, int] = field(default_factory=dict)
    test_type_distribution: dict[str, int] = field(default_factory=dict)
    async_test_count: int = 0; fixture_count: int = 0
    coverage_files: list[str] = field(default_factory=list)

@dataclass
class ArchitectureComponent:
    name: str; component_type: str; language: Optional[str] = None
    file_count: int = 0; confidence: float = 0.0

@dataclass
class ArchitectureOverview:
    pattern: str; components: list[ArchitectureComponent] = field(default_factory=list)
    layers: list[dict] = field(default_factory=list); description: str = ""

@dataclass
class MonorepoInfo:
    is_monorepo: bool; workspace_type: Optional[str] = None
    config_file: Optional[str] = None; packages: list[str] = field(default_factory=list)
    package_count: int = 0; cross_package_deps: list[dict] = field(default_factory=list)
    confidence: float = 0.0

@dataclass
class EntryPointSummary:
    http_servers: list[EntryPointInfo] = field(default_factory=list)
    cli_commands: list[EntryPointInfo] = field(default_factory=list)
    workers: list[EntryPointInfo] = field(default_factory=list)
    scheduled_jobs: list[EntryPointInfo] = field(default_factory=list)
    total: int = 0

@dataclass
class RepositoryProfile:
    total_files: int = 0; total_symbols: int = 0; total_lines: int = 0
    total_code_lines: int = 0; total_comment_lines: int = 0; total_blank_lines: int = 0
    test_file_count: int = 0; config_file_count: int = 0; documentation_file_count: int = 0
    avg_complexity: float = 0.0; avg_maintainability: float = 0.0; max_complexity: int = 0
    total_smells: int = 0; unresolved_smells: int = 0; unique_authors: int = 0
    first_commit_date: Optional[str] = None; last_commit_date: Optional[str] = None
    total_commits: int = 0; maturity_rating: str = "unknown"
    complexity_rating: str = "unknown"; size_category: str = "unknown"

@dataclass
class RepositorySummaryResult:
    repository_id: str; generation_version: str; generated_at: str
    languages: list[LanguageInfo] = field(default_factory=list)
    frameworks: list[FrameworkInfo] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    entry_points: EntryPointSummary = field(default_factory=EntryPointSummary)
    apis: list[APIInfo] = field(default_factory=list)
    databases: list[DatabaseInfo] = field(default_factory=list)
    queues: list[QueueInfo] = field(default_factory=list)
    deployment_config: list[DeploymentConfigInfo] = field(default_factory=list)
    test_infrastructure: TestInfrastructureInfo = field(default_factory=TestInfrastructureInfo)
    architecture: ArchitectureOverview = field(default_factory=ArchitectureOverview)
    monorepo: MonorepoInfo = field(default_factory=MonorepoInfo)
    profile: RepositoryProfile = field(default_factory=RepositoryProfile)
    primary_language: Optional[str] = None
    total_files: int = 0; total_symbols: int = 0; total_lines: int = 0


# ═══════════════════════════════════════════════════════════════════════════
# RepositorySummarizer
# ═══════════════════════════════════════════════════════════════════════════


class RepositorySummarizer:
    """Generate a structured, persisted repository summary."""

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ── orchestration ────────────────────────────────────────────────

    async def generate_summary(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> RepositorySummaryResult:
        """Run all detectors and assemble the full summary."""
        session = db or self.db
        logger.info("Generating repository summary for %s", repository_id)

        languages = await self.detect_languages(repository_id, session)
        frameworks = await self.detect_frameworks(repository_id, session)
        entry_points = await self.detect_entry_points(repository_id, session)
        services = await self.detect_services(repository_id, session)
        apis = await self.detect_apis(repository_id, session)
        databases = await self.detect_databases(repository_id, session)
        queues = await self.detect_queues(repository_id, session)
        deployment_config = await self.detect_deployment_config(repository_id, session)
        test_infra = await self.detect_test_infrastructure(repository_id, session)
        architecture = await self.detect_architecture(repository_id, session)
        monorepo = await self.detect_monorepo_structure(repository_id, session)
        profile = await self.get_repository_profile(repository_id, session)

        primary = languages[0].language if languages else None
        ep_summary = EntryPointSummary(
            http_servers=[e for e in entry_points if e.type in ("http_server", "http_server_candidate")],
            cli_commands=[e for e in entry_points if e.type == "cli"],
            workers=[e for e in entry_points if e.type == "worker"],
            scheduled_jobs=[e for e in entry_points if e.type == "scheduled_job"],
            total=len(entry_points),
        )

        result = RepositorySummaryResult(
            repository_id=str(repository_id),
            generation_version=GENERATION_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            languages=languages, frameworks=frameworks, services=services,
            entry_points=ep_summary, apis=apis, databases=databases,
            queues=queues, deployment_config=deployment_config,
            test_infrastructure=test_infra, architecture=architecture,
            monorepo=monorepo, profile=profile, primary_language=primary,
            total_files=profile.total_files, total_symbols=profile.total_symbols,
            total_lines=profile.total_lines,
        )
        logger.info("Summary for %s: %d langs, %d fw, %d svc, %d APIs",
                     repository_id, len(languages), len(frameworks), len(services), len(apis))
        return result

    # ── language detection ───────────────────────────────────────────

    async def detect_languages(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[LanguageInfo]:
        """Detect languages and their file/line proportions."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        if not files:
            return []
        lang_files: dict[str, list[CodeFile]] = defaultdict(list)
        for f in files:
            lang = f.language or _detect_lang_from_path(f.file_path) or "unknown"
            lang_files[lang].append(f)
        total = len(files)
        result: list[LanguageInfo] = []
        for lang, flist in sorted(lang_files.items(), key=lambda x: len(x[1]), reverse=True):
            lc = sum(f.line_count or 0 for f in flist)
            exts = sorted({f".{f.file_path.rsplit('.', 1)[-1].lower()}" for f in flist if "." in f.file_path})
            result.append(LanguageInfo(lang, len(flist), lc, round(len(flist) / total, 4), exts))
        return result

    # ── framework detection ──────────────────────────────────────────

    async def detect_frameworks(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[FrameworkInfo]:
        """Detect frameworks via import patterns, config patterns, and file naming."""
        session = db or self.db
        imp_stmt = select(CodeImport.imported_name).where(CodeImport.repository_id == repository_id)
        import_text = "\n".join(r[0] for r in (await session.execute(imp_stmt)).all())

        fp_stmt = select(CodeFile.file_path, CodeFile.file_name).where(CodeFile.repository_id == repository_id)
        file_rows = (await session.execute(fp_stmt)).all()
        file_names = [r[1] for r in file_rows if r[1]]
        file_paths = [r[0] for r in file_rows if r[0]]

        detected: dict[str, FrameworkInfo] = {}
        for a in FRAMEWORK_ADAPTERS:
            score = 0.0
            evidence: list[str] = []
            for pat in a.get("imp", []):
                if re.search(pat, import_text):
                    score += 0.5; evidence.append(f"import:{pat}"); break
            for pat in a.get("cfg", []):
                if any(re.search(pat, fp) for fp in file_paths):
                    score += 0.3; evidence.append(f"config:{pat}"); break
            for fp_ in a.get("files", []):
                if any(fp_ in fn for fn in file_names):
                    score += 0.2; evidence.append(f"file:{fp_}"); break
            if score >= 0.5:
                nm = a["name"]
                if nm not in detected or score > detected[nm].confidence:
                    detected[nm] = FrameworkInfo(nm, a["cat"], a["lang"],
                                                 round(min(score, 0.95), 2), evidence[:5])
        return sorted(detected.values(), key=lambda fw: fw.confidence, reverse=True)

    # ── entry point detection ────────────────────────────────────────

    async def detect_entry_points(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[EntryPointInfo]:
        """Detect HTTP servers, CLI commands, workers, and scheduled jobs."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        eps: list[EntryPointInfo] = []
        for f in files:
            lang_key = _norm_lang(f.language or "")
            if not lang_key:
                continue
            content = await _safe_read(f)
            if not content:
                continue
            for ep_type, lpats in EP_PATTERNS.items():
                pat = lpats.get(lang_key)
                if not pat or not pat.search(content):
                    continue
                m = pat.search(content)
                ln = content[:m.start()].count("\n") + 1 if m else 1
                snippet = _snippet(content.split("\n"), ln, 2)
                eps.append(EntryPointInfo(ep_type, f.file_path, str(f.id), f.language, ln, snippet, 0.8))

        if not any(e.type == "http_server" for e in eps):
            main_names = {"main.py", "app.py", "server.py", "index.py", "main.js",
                          "server.js", "app.js", "index.js", "main.ts", "server.ts", "main.go"}
            mf = (await session.execute(
                select(CodeFile).where(CodeFile.repository_id == repository_id, CodeFile.file_name.in_(list(main_names)))
            )).scalars().all()
            for f in mf:
                eps.append(EntryPointInfo("http_server_candidate", f.file_path, str(f.id),
                                          f.language, None, f"Convention: {f.file_name}", 0.4))
        eps.sort(key=lambda e: e.confidence, reverse=True)
        return eps

    # ── service detection ────────────────────────────────────────────

    async def detect_services(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[ServiceInfo]:
        """Detect microservices, modules, and logical service boundaries."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        dir_files: dict[str, list[CodeFile]] = defaultdict(list)
        for f in files:
            parts = f.file_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                dir_files[parts[0]].append(f)

        entry_exts = {"main.py", "app.py", "server.py", "index.py", "main.js", "server.js",
                      "app.js", "index.js", "main.ts", "server.ts", "app.ts", "index.ts", "main.go"}
        svc_kw = {"service", "services", "handler", "handlers", "controller", "controllers", "resolver", "resolvers"}
        model_kw = {"model", "models", "entity", "entities", "schema", "schemas", "migration", "migrations"}

        services: list[ServiceInfo] = []
        for dn, dfl in dir_files.items():
            lc: Counter[str] = Counter()
            has_entry = has_config = has_tests = has_models = False
            for f in dfl:
                if f.language:
                    lc[f.language] += 1
                if f.is_test_file: has_tests = True
                if f.is_config_file: has_config = True
                bn = f.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
                if bn in entry_exts or bn.startswith("main."):
                    has_entry = True
                if any(kw in bn for kw in model_kw): has_models = True
                if any(kw in bn for kw in svc_kw): has_entry = True

            pl = lc.most_common(1)[0][0] if lc else "unknown"
            score = (0.4 if has_entry else 0) + (0.15 if has_config else 0) + (0.1 if has_tests else 0) + \
                    (0.1 if has_models else 0) + (0.15 if len(dfl) >= 3 else 0) + (0.1 if len(lc) > 1 else 0)
            if score >= 0.4:
                services.append(ServiceInfo(dn, len(dfl), pl, has_entry, has_config, has_tests,
                                            has_models, round(min(score, 0.95), 2),
                                            [f.file_path for f in dfl[:10]]))
        services.sort(key=lambda s: s.confidence, reverse=True)
        return services

    # ── API detection ────────────────────────────────────────────────

    async def detect_apis(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[APIInfo]:
        """Detect REST endpoints, GraphQL resolvers, gRPC services, event handlers."""
        session = db or self.db
        stmt = select(CodeFile).where(
            CodeFile.repository_id == repository_id,
            CodeFile.language.in_(["python", "py", "javascript", "js", "typescript",
                                   "ts", "tsx", "jsx", "java", "go", "rb", "ruby", "php"]),
        )
        files = (await session.execute(stmt)).scalars().all()
        endpoints: list[APIInfo] = []
        for f in files:
            content = await _safe_read(f)
            if not content:
                continue
            for pn, pat in API_PATTERNS.items():
                for m in pat.finditer(content):
                    route = m.group(1) if m.lastindex and m.group(1) else ""
                    ln = content[:m.start()].count("\n") + 1
                    snip = _snippet(content.split("\n"), ln, 1)
                    method = _http_method(pn, snip)
                    endpoints.append(APIInfo(_ep_type(pn), route, method, f.file_path, f.language, ln, snip, 0.85))
        endpoints.sort(key=lambda e: (e.file_path, e.line or 0))
        return endpoints

    # ── database detection ───────────────────────────────────────────

    async def detect_databases(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[DatabaseInfo]:
        """Detect ORM models, migrations, connection strings, database config."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        dbs: list[DatabaseInfo] = []
        for f in files:
            content = await _safe_read(f)
            if not content:
                continue
            for pn, pat in DB_PATTERNS.items():
                matches = list(pat.finditer(content))
                if not matches:
                    continue
                ln = content[:matches[0].start()].count("\n") + 1
                snip = _snippet(content.split("\n"), ln, 2)
                dbs.append(DatabaseInfo(pn, _db_engine(content, f.file_path) or "unknown",
                                        f.file_path, f.language, ln, len(matches),
                                        snip, min(0.5 + 0.1 * len(matches), 0.95)))
        return dbs

    # ── queue detection ──────────────────────────────────────────────

    async def detect_queues(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[QueueInfo]:
        """Detect message queue consumers and producers."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        queues: list[QueueInfo] = []
        for f in files:
            content = await _safe_read(f)
            if not content:
                continue
            for pn, pat in QUEUE_PATTERNS.items():
                matches = list(pat.finditer(content))
                if not matches:
                    continue
                ln = content[:matches[0].start()].count("\n") + 1
                role = _queue_role(content)
                queues.append(QueueInfo(pn, role, f.file_path, f.language, ln, len(matches),
                                        min(0.5 + 0.1 * len(matches), 0.9)))
        return queues

    # ── deployment config ────────────────────────────────────────────

    async def detect_deployment_config(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> list[DeploymentConfigInfo]:
        """Detect Docker, K8s, CI/CD, and other deployment configuration."""
        session = db or self.db
        stmt = select(CodeFile).where(CodeFile.repository_id == repository_id)
        files = (await session.execute(stmt)).scalars().all()
        configs: list[DeploymentConfigInfo] = []
        for f in files:
            fn = f.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            ct: Optional[str] = None
            for name, dtype in DEPLOY_FILES.items():
                if fn == name or fn.endswith(name):
                    ct = dtype; break
            if not ct:
                for path, dtype in CICD_PATHS.items():
                    if path in f.file_path:
                        ct = f"ci_cd_{dtype}"; break
            if not ct and fn.endswith((".yaml", ".yml")):
                content = await _safe_read(f)
                if content and K8S_PATTERN.search(content):
                    ct = "kubernetes"
            if not ct:
                if fn.startswith(".env"): ct = "env_template"
                elif fn == "Dockerfile" or fn.startswith("Dockerfile."): ct = "docker"
                elif fn.endswith((".ini", ".cfg", ".conf", ".properties")): ct = "service_config"
            if ct:
                configs.append(DeploymentConfigInfo(ct, f.file_path, fn, f.language, f.size_bytes))
        configs.sort(key=lambda c: c.type)
        return configs

    # ── test infrastructure ──────────────────────────────────────────

    async def detect_test_infrastructure(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> TestInfrastructureInfo:
        """Gather test framework distribution, counts, and coverage files."""
        session = db or self.db
        tfc = (await session.execute(select(func.count()).where(
            CodeFile.repository_id == repository_id, CodeFile.is_test_file.is_(True)))).scalar() or 0
        ttc = (await session.execute(select(func.count()).where(
            CodeTest.repository_id == repository_id))).scalar() or 0
        fw_rows = (await session.execute(
            select(CodeTest.framework, func.count(CodeTest.id))
            .where(CodeTest.repository_id == repository_id).group_by(CodeTest.framework)
        )).all()
        frameworks = {r[0] or "unknown": r[1] for r in fw_rows}
        tt_rows = (await session.execute(
            select(CodeTest.test_type, func.count(CodeTest.id))
            .where(CodeTest.repository_id == repository_id).group_by(CodeTest.test_type)
        )).all()
        test_types = {r[0]: r[1] for r in tt_rows}
        atc = (await session.execute(select(func.count()).where(
            CodeTest.repository_id == repository_id, CodeTest.is_async.is_(True)))).scalar() or 0
        fc = (await session.execute(select(func.count()).where(
            CodeTest.repository_id == repository_id, CodeTest.test_type == "FIXTURE"))).scalar() or 0
        cov_files: list[str] = []
        for pat in ["%coverage.json%", "%lcov.info%", "%cobertura.xml%"]:
            for r in (await session.execute(
                select(CodeFile.file_path).where(
                    CodeFile.repository_id == repository_id, CodeFile.file_path.ilike(pat)
                ).limit(10)
            )).scalars().all():
                cov_files.append(r)
        return TestInfrastructureInfo(tfc, ttc, frameworks, test_types, atc, fc, cov_files)

    # ── architecture overview ────────────────────────────────────────

    async def detect_architecture(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> ArchitectureOverview:
        """Produce architecture overview: detected layers, components, relationships."""
        session = db or self.db
        files = (await session.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id)
        )).scalars().all()
        symbols = (await session.execute(
            select(CodeSymbol).where(
                CodeSymbol.repository_id == repository_id,
                CodeSymbol.symbol_type.in_([SymbolType.CLASS.value, SymbolType.FUNCTION.value, SymbolType.METHOD.value]),
            )
        )).scalars().all()
        sym_names = " ".join(s.name for s in symbols)

        layers: list[dict] = []
        components: list[ArchitectureComponent] = []
        for ln, sig in LAYER_SIGNALS.items():
            matched: list[str] = []
            confs: list[float] = []
            for f in files:
                score = 0.0
                for p in sig.get("fp", []):
                    if re.search(p, f.file_path, re.IGNORECASE):
                        score += 0.4; break
                for p in sig.get("sp", []):
                    if re.search(p, sym_names, re.IGNORECASE):
                        score += 0.3; break
                if score >= 0.3:
                    matched.append(f.file_path); confs.append(score)
            if matched:
                avg = sum(confs) / len(confs) if confs else 0.0
                layers.append({"layer": ln, "file_count": len(matched),
                               "confidence": round(min(avg, 0.95), 2)})
                components.append(ArchitectureComponent(ln, "layer", None, len(matched),
                                                        round(min(avg, 0.95), 2)))

        dir_map: Counter[str] = Counter()
        for f in files:
            parts = f.file_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                dir_map[parts[0]] += 1
        for dn, cnt in dir_map.most_common(10):
            if cnt >= 3:
                components.append(ArchitectureComponent(dn, "module", None, cnt, 0.6))

        pattern = _infer_pattern(layers, components)
        layer_names = [l["layer"] for l in layers]
        desc = f"Repository follows a {pattern} architecture"
        if layer_names:
            desc += f" with layers: {', '.join(layer_names)}"
        return ArchitectureOverview(pattern, components, layers, desc)

    # ── monorepo structure ───────────────────────────────────────────

    async def detect_monorepo_structure(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> MonorepoInfo:
        """Detect workspace roots, packages, apps, and cross-package deps."""
        session = db or self.db
        files = (await session.execute(
            select(CodeFile).where(CodeFile.repository_id == repository_id)
        )).scalars().all()

        for f in files:
            fn = f.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
            if fn not in WORKSPACE_CONFIGS:
                continue
            content = await _safe_read(f)
            if not content or not WORKSPACE_CONFIGS[fn].search(content):
                continue
            ws_type = _classify_ws(fn, content)
            packages = _extract_ws_pkgs(fn, content)
            cross = await self._cross_package_deps(repository_id, packages, session)
            return MonorepoInfo(True, ws_type, f.file_path, packages, len(packages), cross, 0.85)

        dir_map: Counter[str] = Counter()
        for f in files:
            parts = f.file_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                dir_map[parts[0]] += 1
        indicators = {"packages", "apps", "services", "libs", "shared", "modules", "microservices", "internal"}
        detected = [d for d in dir_map if d.lower() in indicators]
        if len(detected) >= 2:
            return MonorepoInfo(True, "monorepo_by_convention", None, detected, len(detected), [], 0.5)
        return MonorepoInfo(False, confidence=0.3)

    async def _cross_package_deps(
        self, repo_id: UUID, packages: list[str], session: AsyncSession
    ) -> list[dict]:
        """Detect imports referencing other packages in the workspace."""
        if len(packages) < 2:
            return []
        pkg_bases = {p.rstrip("/").rsplit("/", 1)[-1].lower() for p in packages}
        if len(pkg_bases) < 2:
            return []
        rows = (await session.execute(
            select(CodeImport.imported_name, CodeImport.source_file_id)
            .where(CodeImport.repository_id == repo_id)
        )).all()
        seen: set[str] = set()
        deps: list[dict] = []
        for imp_name, sfid in rows:
            lo = imp_name.lower()
            for pb in pkg_bases:
                if pb in lo and lo != pb:
                    key = f"{imp_name}:{pb}"
                    if key not in seen:
                        seen.add(key)
                        deps.append({"imported_name": imp_name, "references_package": pb,
                                      "source_file_id": str(sfid)})
                    break
        return deps[:100]

    # ── repository profile ───────────────────────────────────────────

    async def get_repository_profile(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> RepositoryProfile:
        """Compute size, complexity, and maturity indicators."""
        session = db or self.db

        async def _q(stmt: Any) -> int:
            return (await session.execute(stmt)).scalar() or 0

        total_files = await _q(select(func.count()).select_from(CodeFile).where(CodeFile.repository_id == repository_id))
        total_symbols = await _q(select(func.count()).select_from(CodeSymbol).where(CodeSymbol.repository_id == repository_id))
        total_lines = await _q(select(func.coalesce(func.sum(CodeFile.line_count), 0))
                         .where(CodeFile.repository_id == repository_id))

        m_row = (await session.execute(select(
            func.coalesce(func.sum(CodeMetrics.code_lines), 0),
            func.coalesce(func.sum(CodeMetrics.comment_lines), 0),
            func.coalesce(func.sum(CodeMetrics.blank_lines), 0),
        ).where(CodeMetrics.repository_id == repository_id, CodeMetrics.symbol_id.is_(None)))).one()
        total_code, total_comment, total_blank = int(m_row[0] or 0), int(m_row[1] or 0), int(m_row[2] or 0)

        test_fc = await _q(select(func.count()).where(CodeFile.repository_id == repository_id, CodeFile.is_test_file.is_(True)))
        config_fc = await _q(select(func.count()).where(CodeFile.repository_id == repository_id, CodeFile.is_config_file.is_(True)))
        doc_fc = await _q(select(func.count()).where(CodeFile.repository_id == repository_id, CodeFile.is_documentation.is_(True)))

        cc = (await session.execute(select(
            func.avg(CodeMetrics.cyclomatic_complexity), func.max(CodeMetrics.cyclomatic_complexity),
            func.avg(CodeMetrics.maintainability_index),
        ).where(CodeMetrics.repository_id == repository_id, CodeMetrics.symbol_id.isnot(None)))).one()
        avg_cc, max_cc, avg_mi = float(cc[0] or 0.0), int(cc[1] or 0), float(cc[2] or 0.0)

        smells = await _q(select(func.count()).where(CodeSmell.repository_id == repository_id))
        try:
            authors = await _q(select(func.count(func.distinct(CodeOwnership.owner_email)))
                         .where(CodeOwnership.repository_id == repository_id))
        except Exception:
            authors = 0

        try:
            h = (await session.execute(select(
                func.min(CodeHistory.commit_date), func.max(CodeHistory.commit_date),
                func.count(func.distinct(CodeHistory.commit_sha)),
            ).where(CodeHistory.repository_id == repository_id))).one()
            first_c, last_c, commits = h[0], h[1], int(h[2] or 0)
        except Exception:
            first_c, last_c, commits = None, None, 0

        return RepositoryProfile(
            total_files=total_files, total_symbols=total_symbols, total_lines=total_lines,
            total_code_lines=total_code, total_comment_lines=total_comment, total_blank_lines=total_blank,
            test_file_count=test_fc, config_file_count=config_fc, documentation_file_count=doc_fc,
            avg_complexity=round(avg_cc, 2), avg_maintainability=round(avg_mi, 2), max_complexity=max_cc,
            total_smells=smells, unresolved_smells=smells, unique_authors=authors,
            first_commit_date=first_c.isoformat() if first_c else None,
            last_commit_date=last_c.isoformat() if last_c else None, total_commits=commits,
            maturity_rating=_maturity(total_files, total_symbols, commits, authors),
            complexity_rating=_complexity_rating(avg_cc, max_cc),
            size_category=_size_cat(total_lines),
        )

    # ── generate and persist ─────────────────────────────────────────

    async def generate_and_store(
        self, repository_id: UUID, db: Optional[AsyncSession] = None
    ) -> RepositorySummaryResult:
        """Generate summary and persist it as metadata on active CodeIndex."""
        session = db or self.db
        summary = await self.generate_summary(repository_id, session)
        idx_stmt = (
            select(CodeIndex).where(
                CodeIndex.repository_id == repository_id,
                CodeIndex.status.in_(["READY", "PARTIAL"]),
            ).order_by(CodeIndex.created_at.desc()).limit(1)
        )
        code_index = (await session.execute(idx_stmt)).scalar_one_or_none()
        if code_index is not None:
            code_index.metadata_ = {
                "repository_summary": asdict(summary),
                "summary_generated_at": summary.generated_at,
                "summary_version": summary.generation_version,
            }
            await session.flush()
            logger.info("Stored summary on index %s for repo %s", code_index.id, repository_id)
        else:
            logger.warning("No active CodeIndex for repo %s; summary not persisted", repository_id)
        return summary


# ═══════════════════════════════════════════════════════════════════════════
# Module-level helpers
# ═══════════════════════════════════════════════════════════════════════════


def _detect_lang_from_path(file_path: str) -> Optional[str]:
    lo = file_path.lower()
    for ext, lang in EXT_TO_LANG.items():
        if lo.endswith(ext): return lang
    return None


def _norm_lang(lang: str) -> Optional[str]:
    m = {"python": "python", "py": "python", "javascript": "javascript", "js": "javascript",
         "typescript": "javascript", "ts": "javascript", "tsx": "javascript", "jsx": "javascript",
         "java": "java", "go": "go", "ruby": "ruby", "rb": "ruby", "php": "php"}
    return m.get(lang.lower())


async def _safe_read(f: CodeFile) -> Optional[str]:
    try:
        with open(f.file_path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, IOError, ValueError):
        return None


def _snippet(lines: list[str], ln: int, ctx: int = 2) -> str:
    start, end = max(0, ln - 1 - ctx), min(len(lines), ln + ctx)
    return "\n".join(f"{'>>> ' if i == ln - 1 else '    '}{i + 1}: {lines[i]}" for i in range(start, end))


def _http_method(pn: str, snip: str) -> str:
    lo = pn.lower()
    for name in ("get", "post", "put", "delete", "patch"):
        if name in lo: return name.upper()
    ls = snip.lower()
    for name in ("get", "post", "put", "delete", "patch"):
        if f".{name}(" in ls or f"@{name}" in ls: return name.upper()
    return "ANY"


def _ep_type(pn: str) -> str:
    tm = {"rest_fastapi": "REST", "rest_flask": "REST", "rest_django": "REST", "rest_express": "REST",
          "rest_nestjs": "REST", "rest_spring": "REST", "rest_gin": "REST", "rest_rails": "REST",
          "rest_laravel": "REST", "graphql": "GraphQL", "grpc": "gRPC", "event": "event", "webhook": "webhook"}
    return tm.get(pn, "unknown")


def _db_engine(content: str, fp: str) -> Optional[str]:
    lo = content.lower()
    for eng, kw in [("postgresql", "sqlalchemy"), ("postgresql", "postgresql"), ("mysql", "mysql"),
                    ("sqlite", "sqlite"), ("mongodb", "mongodb"), ("redis", "redis"),
                    ("elasticsearch", "elasticsearch"), ("dynamodb", "dynamodb"),
                    ("cassandra", "cassandra"), ("neo4j", "neo4j")]:
        if kw in lo: return eng
    if ".env" in fp or "config" in fp.lower():
        if "postgres" in lo: return "postgresql"
        if "mysql" in lo: return "mysql"
        if "mongo" in lo: return "mongodb"
    return None


def _queue_role(content: str) -> str:
    lo = content.lower()
    pub = any(k in lo for k in ("send", "publish", "produce", "push", "dispatch", "emit"))
    con = any(k in lo for k in ("receive", "consume", "subscribe", "listen", "poll", "handle", "process"))
    if pub and con: return "producer_consumer"
    if pub: return "producer"
    if con: return "consumer"
    return "unknown"


def _classify_ws(fn: str, content: str) -> str:
    tm = {"lerna.json": "lerna", "turbo.json": "turborepo", "nx.json": "nx",
          "rush.json": "rush", "pnpm-workspace.yaml": "pnpm_workspace",
          "Cargo.toml": "cargo_workspace", "go.work": "go_workspace"}
    if fn in tm: return tm[fn]
    if fn == "package.json" and '"workspaces"' in content: return "npm_workspace"
    return "unknown"


def _extract_ws_pkgs(fn: str, content: str) -> list[str]:
    import json as _json
    pkgs: list[str] = []
    if fn in ("package.json", "lerna.json"):
        try:
            data = _json.loads(content)
            ws = data.get("workspaces" if fn == "package.json" else "packages", [])
            pkgs = ws if isinstance(ws, list) else ws.get("packages", []) if isinstance(ws, dict) else []
        except (ValueError, KeyError):
            pass
    elif fn == "pnpm-workspace.yaml":
        for l in content.split("\n"):
            if l.strip().startswith("- ") and l.strip()[2:].strip():
                pkgs.append(l.strip()[2:].strip().strip("'\""))
    elif fn == "go.work":
        for l in content.split("\n"):
            if l.strip().startswith("use "):
                for p in l.strip()[4:].strip().strip("()").split("\n"):
                    p = p.strip()
                    if p: pkgs.append(p)
    elif fn == "Cargo.toml":
        for l in content.split("\n"):
            if l.strip().startswith("members") and "=" in l:
                for p in l.split("=", 1)[1].strip().strip("[]").split(","):
                    p = p.strip().strip("'\"")
                    if p: pkgs.append(p)
    return pkgs


def _infer_pattern(layers: list[dict], components: list[ArchitectureComponent]) -> str:
    names = {l["layer"] for l in layers}
    mods = {c.name.lower() for c in components if c.component_type == "module"}
    if any("service" in n for n in mods) and len(mods) > 3: return "microservices"
    if "presentation" in names and "business_logic" in names and "data_access" in names: return "layered"
    if "presentation" in names and "business_logic" in names: return "monolith_fullstack"
    if "business_logic" in names and "data_access" in names: return "monolith"
    if "presentation" in names: return "frontend_only"
    if any(n in ("worker", "celery", "task") for n in mods): return "event_driven"
    return "unknown"


def _maturity(files: int, symbols: int, commits: int, authors: int) -> str:
    score = 0
    for tf, ts, tc, ta in MATURITY_THRESHOLDS.values():
        if files >= tf: score += 1
        if symbols >= ts: score += 1
        if commits >= tc: score += 1
        if authors >= ta: score += 1
    if score >= 14: return "established"
    if score >= 10: return "mature"
    if score >= 6: return "growing"
    if score >= 3: return "early"
    return "immature"


def _complexity_rating(avg: float, mx: int) -> str:
    if avg <= 3 and mx <= 10: return "low"
    if avg <= 7 and mx <= 20: return "moderate"
    if avg <= 15 and mx <= 40: return "high"
    return "very_high"


def _size_cat(lines: int) -> str:
    for cat, thr in sorted(SIZE_BUCKETS.items(), key=lambda x: x[1]):
        if lines <= thr: return cat
    return "very_large"
