"""Architecture Discovery Engine — detect layers, services, entry points, APIs,
databases, queues, external dependencies, frameworks, configuration, and
monorepo structure from indexed code data.

Uses the adapter pattern for framework detection — never hard-coded assumptions.
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.code_intelligence.models import (
    CodeFile,
    CodeImport,
    CodeSymbol,
)

logger = logging.getLogger(__name__)


# ── Dataclasses ───────────────────────────────────────────────────────


@dataclass
class RepositorySummary:
    """Structured metadata about a repository."""
    languages: dict[str, int] = field(default_factory=dict)
    frameworks: list[dict] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)
    entry_points: list[dict] = field(default_factory=list)
    apis: list[dict] = field(default_factory=list)
    databases: list[dict] = field(default_factory=list)
    queues: list[dict] = field(default_factory=list)
    deployment_config: list[dict] = field(default_factory=list)
    test_files: list[str] = field(default_factory=list)
    architecture_pattern: str = "unknown"
    total_files: int = 0
    total_symbols: int = 0
    total_lines: int = 0


@dataclass
class ArchitectureResult:
    """Full architecture discovery output."""
    layers: list[dict] = field(default_factory=list)
    services: list[dict] = field(default_factory=list)
    entry_points: list[dict] = field(default_factory=list)
    api_endpoints: list[dict] = field(default_factory=list)
    databases: list[dict] = field(default_factory=list)
    queues: list[dict] = field(default_factory=list)
    external_deps: list[dict] = field(default_factory=list)
    frameworks: list[dict] = field(default_factory=list)
    configuration: list[dict] = field(default_factory=list)
    monorepo: list[dict] = field(default_factory=list)
    graph: dict = field(default_factory=dict)
    summary: RepositorySummary = field(default_factory=RepositorySummary)


# ── Framework Detection Adapters ──────────────────────────────────────


FRAMEWORK_ADAPTERS: list[dict] = [
    # ── Python Backend ──────────────────────────────────────────────
    {
        "name": "FastAPI",
        "language": "python",
        "import_patterns": [r"\bfrom\s+fastapi\b", r"\bimport\s+fastapi\b"],
        "config_patterns": [r"\bFastAPI\s*\("],
        "file_patterns": ["main.py", "app.py", "api.py"],
        "category": "backend",
    },
    {
        "name": "Django",
        "language": "python",
        "import_patterns": [r"\bfrom\s+django\b", r"\bimport\s+django\b"],
        "config_patterns": [r"\bINSTALLED_APPS\b", r"\bWSGI_APPLICATION\b", r"\bASGI_APPLICATION\b"],
        "file_patterns": ["settings.py", "wsgi.py", "asgi.py", "urls.py", "manage.py"],
        "category": "backend",
    },
    {
        "name": "Flask",
        "language": "python",
        "import_patterns": [r"\bfrom\s+flask\b", r"\bimport\s+flask\b"],
        "config_patterns": [r"\bFlask\s*\("],
        "file_patterns": ["app.py", "routes.py", "views.py"],
        "category": "backend",
    },
    {
        "name": "Celery",
        "language": "python",
        "import_patterns": [r"\bfrom\s+celery\b", r"\bimport\s+celery\b"],
        "config_patterns": [r"\bCELERY_\w+\b", r"\b@shared_task\b", r"\b@celery\.task\b"],
        "file_patterns": ["celery.py", "tasks.py"],
        "category": "queue",
    },
    {
        "name": "SQLAlchemy",
        "language": "python",
        "import_patterns": [r"\bfrom\s+sqlalchemy\b", r"\bimport\s+sqlalchemy\b"],
        "config_patterns": [r"\bSQLAlchemy\s*\(", r"\bColumn\s*\("],
        "file_patterns": ["models.py", "database.py", "db.py"],
        "category": "orm",
    },
    {
        "name": "Pydantic",
        "language": "python",
        "import_patterns": [r"\bfrom\s+pydantic\b", r"\bimport\s+pydantic\b"],
        "config_patterns": [r"\bBaseModel\s*\("],
        "file_patterns": ["schemas.py", "models.py"],
        "category": "validation",
    },
    {
        "name": "Alembic",
        "language": "python",
        "import_patterns": [r"\bfrom\s+alembic\b", r"\bimport\s+alembic\b"],
        "config_patterns": [r"\balembic\.ini\b"],
        "file_patterns": ["alembic.ini", "env.py"],
        "category": "migration",
    },
    {
        "name": "Celery-Redis",
        "language": "python",
        "import_patterns": [r"\bfrom\s+celery\b.*\bredis\b"],
        "config_patterns": [r"\bCELERY_BROKER_URL\s*=\s*.*redis"],
        "file_patterns": [],
        "category": "queue",
    },
    # ── JavaScript / TypeScript Backend ─────────────────────────────
    {
        "name": "Express",
        "language": "javascript",
        "import_patterns": [r"""\brequire\s*\(\s*['"]express['"]\s*\)""", r"""\bimport\s+.*from\s+['"]express['"]"""],
        "config_patterns": [r"\bexpress\s*\(\s*\)"],
        "file_patterns": ["server.js", "app.js", "index.js"],
        "category": "backend",
    },
    {
        "name": "NestJS",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]@nestjs/core['"]""", r"""\bfrom\s+['"]@nestjs/common['"]"""],
        "config_patterns": [r"\bNestFactory\.create\b", r"\b@Controller\s*\("],
        "file_patterns": ["main.ts", "app.module.ts"],
        "category": "backend",
    },
    {
        "name": "Koa",
        "language": "javascript",
        "import_patterns": [r"""\brequire\s*\(\s*['"]koa['"]\s*\)""", r"""\bimport\s+.*from\s+['"]koa['"]"""],
        "config_patterns": [r"\bnew\s+Koa\s*\("],
        "file_patterns": ["app.js", "server.js"],
        "category": "backend",
    },
    {
        "name": "Hapi",
        "language": "javascript",
        "import_patterns": [r"""\brequire\s*\(\s*['"]@hapi/hapi['"]\s*\)""", r"""\bimport\s+.*from\s+['"]@hapi/hapi['"]"""],
        "config_patterns": [r"\bHapi\.server\s*\("],
        "file_patterns": ["server.js"],
        "category": "backend",
    },
    {
        "name": "Sequelize",
        "language": "javascript",
        "import_patterns": [r"""\brequire\s*\(\s*['"]sequelize['"]\s*\)""", r"""\bimport\s+.*from\s+['"]sequelize['"]"""],
        "config_patterns": [r"\bnew\s+Sequelize\s*\("],
        "file_patterns": ["models/index.js", "sequelize.js"],
        "category": "orm",
    },
    {
        "name": "Prisma",
        "language": "javascript",
        "import_patterns": [r"\b@prisma/client\b"],
        "config_patterns": [r"\bPrismaClient\s*\("],
        "file_patterns": ["schema.prisma"],
        "category": "orm",
    },
    {
        "name": "TypeORM",
        "language": "javascript",
        "import_patterns": [r"\btypeorm\b"],
        "config_patterns": [r"\b@Entity\s*\(", r"\bDataSource\s*\("],
        "file_patterns": ["ormconfig.json", "ormconfig.ts"],
        "category": "orm",
    },
    {
        "name": "Bull",
        "language": "javascript",
        "import_patterns": [r"""\brequire\s*\(\s*['"]bull['"]\s*\)""", r"""\bimport\s+.*from\s+['"]bull['"]"""],
        "config_patterns": [r"\bnew\s+Bull\s*\("],
        "file_patterns": ["queue.js", "jobs.js"],
        "category": "queue",
    },
    # ── Java Backend ────────────────────────────────────────────────
    {
        "name": "Spring Boot",
        "language": "java",
        "import_patterns": [r"\bimport\s+org\.springframework\b"],
        "config_patterns": [r"\b@SpringBootApplication\b", r"\b@RestController\b", r"\b@Service\b"],
        "file_patterns": ["Application.java", "pom.xml", "build.gradle"],
        "category": "backend",
    },
    {
        "name": "Hibernate",
        "language": "java",
        "import_patterns": [r"\bimport\s+org\.hibernate\b", r"\bimport\s+javax\.persistence\b"],
        "config_patterns": [r"\b@Entity\b", r"\b@Table\s*\(", r"\b@Column\s*\("],
        "file_patterns": ["hibernate.cfg.xml"],
        "category": "orm",
    },
    {
        "name": "Spring Data JPA",
        "language": "java",
        "import_patterns": [r"\bimport\s+org\.springframework\.data\.jpa\b"],
        "config_patterns": [r"\bJpaRepository\b"],
        "file_patterns": [],
        "category": "orm",
    },
    # ── Go Backend ──────────────────────────────────────────────────
    {
        "name": "Gin",
        "language": "go",
        "import_patterns": [r"\bgithub\.com/gin-gonic/gin\b"],
        "config_patterns": [r"\bgin\.Default\(\)", r"\bgin\.New\(\)"],
        "file_patterns": ["main.go"],
        "category": "backend",
    },
    {
        "name": "Echo",
        "language": "go",
        "import_patterns": [r"\bgithub\.com/labstack/echo\b"],
        "config_patterns": [r"\becho\.New\(\)"],
        "file_patterns": ["main.go"],
        "category": "backend",
    },
    {
        "name": "Fiber",
        "language": "go",
        "import_patterns": [r"\bgithub\.com/gofiber/fiber\b"],
        "config_patterns": [r"\bfiber\.New\(\)"],
        "file_patterns": ["main.go"],
        "category": "backend",
    },
    {
        "name": "GORM",
        "language": "go",
        "import_patterns": [r"\bgithub\.com/gorm-io/gorm\b"],
        "config_patterns": [r"\bgorm\.Open\("],
        "file_patterns": ["models.go"],
        "category": "orm",
    },
    # ── Ruby Backend ────────────────────────────────────────────────
    {
        "name": "Ruby on Rails",
        "language": "ruby",
        "import_patterns": [r"""\brequire\s+['"]rails['"]"""],
        "config_patterns": [r"\bRails\.application\b", r"\bActiveRecord\b"],
        "file_patterns": ["Gemfile", "config/routes.rb", "config/database.yml"],
        "category": "backend",
    },
    {
        "name": "Sinatra",
        "language": "ruby",
        "import_patterns": [r"""\brequire\s+['"]sinatra['"]"""],
        "config_patterns": [r"\bget\s+['\"]\/", r"\bpost\s+['\"]\/"],
        "file_patterns": ["app.rb"],
        "category": "backend",
    },
    # ── PHP Backend ─────────────────────────────────────────────────
    {
        "name": "Laravel",
        "language": "php",
        "import_patterns": [r"\buse\s+Illuminate\\", r"\bApp\\Http\\Controllers\\"],
        "config_patterns": [r"\bRoute::", r"\bEloquent\\Model\b"],
        "file_patterns": ["artisan", "composer.json", "routes/web.php"],
        "category": "backend",
    },
    {
        "name": "Symfony",
        "language": "php",
        "import_patterns": [r"\buse\s+Symfony\\", r"\bApp\\Controller\\"],
        "config_patterns": [r"\b@Route\b", r"\b@Controller\b"],
        "file_patterns": ["composer.json", "symfony.lock"],
        "category": "backend",
    },
    # ── Frontend ────────────────────────────────────────────────────
    {
        "name": "React",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]react['"]""", r"""\bimport\s+React\b"""],
        "config_patterns": [r"\bReactDOM\.render\b", r"\bcreateRoot\b", r"\buseEffect\b"],
        "file_patterns": ["App.jsx", "App.tsx", "index.jsx", "index.tsx"],
        "category": "frontend",
    },
    {
        "name": "Vue",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]vue['"]""", r"""\bcreateApp\b"""],
        "config_patterns": [r"\bVue\.createApp\b", r"\bdefineComponent\b"],
        "file_patterns": ["App.vue", "main.js", "main.ts"],
        "category": "frontend",
    },
    {
        "name": "Angular",
        "language": "typescript",
        "import_patterns": [r"""\bfrom\s+['"]@angular/""", r"""\bimport\s+.*\bfrom\s+['"]@angular/"""],
        "config_patterns": [r"\b@Component\s*\(", r"\b@NgModule\s*\("],
        "file_patterns": ["angular.json", "app.module.ts", "main.ts"],
        "category": "frontend",
    },
    {
        "name": "Svelte",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]svelte/"""],
        "config_patterns": [r"\b\$:=", r"\bonMount\s*\("],
        "file_patterns": ["svelte.config.js"],
        "category": "frontend",
    },
    {
        "name": "Next.js",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]next/"""],
        "config_patterns": [r"\bnext\.config\.", r"\bgetServerSideProps\b", r"\bgetStaticProps\b"],
        "file_patterns": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "category": "fullstack",
    },
    {
        "name": "Nuxt.js",
        "language": "javascript",
        "import_patterns": [r"""\bfrom\s+['"]nuxt/"""],
        "config_patterns": [r"\bnuxt\.config\."],
        "file_patterns": ["nuxt.config.js", "nuxt.config.ts"],
        "category": "fullstack",
    },
]


# ── Layer Detection Signals ───────────────────────────────────────────

LAYER_SIGNALS: dict[str, dict] = {
    "presentation": {
        "file_patterns": [
            r"(?:components?|views?|pages?|screens?|templates?|layouts?)",
            r"\.(?:jsx|tsx|vue|svelte|html|ejs|hbs|pug|jinja|jinja2)$",
        ],
        "import_patterns": [
            r"\bfrom\s+['\"]react['\"]", r"\bfrom\s+['\"]vue['\"]",
            r"\bfrom\s+['\"]@angular/", r"\bfrom\s+['\"]svelte",
        ],
        "symbol_patterns": [
            r"\b(?:Component|View|Page|Screen|Template)\b",
        ],
        "framework_names": ["React", "Vue", "Angular", "Svelte", "Next.js", "Nuxt.js"],
    },
    "business_logic": {
        "file_patterns": [
            r"(?:services?|handlers?|usecases?|interactors?|managers?|facades?)",
            r"(?:domain|business|core|logic)",
        ],
        "symbol_patterns": [
            r"\b(?:Service|Handler|UseCase|Interactor|Manager|Facade|Orchestrator)\b",
        ],
        "framework_names": [],
    },
    "data_access": {
        "file_patterns": [
            r"(?:repositories?|dao|dal|models?|entities?|schemas?|migrations?)",
            r"(?:database|db|orm|store|gateway)",
        ],
        "symbol_patterns": [
            r"\b(?:Repository|DAO|Model|Entity|Schema|Migration|Gateway)\b",
        ],
        "framework_names": [
            "SQLAlchemy", "Sequelize", "Prisma", "TypeORM",
            "Hibernate", "Spring Data JPA", "GORM",
        ],
    },
    "infrastructure": {
        "file_patterns": [
            r"(?:config|middleware|logging|auth|cache|queue|celery|worker)",
            r"(?:infrastructure|infra|inf)",
        ],
        "symbol_patterns": [
            r"\b(?:Middleware|Config|Cache|Logger|Auth|Queue|Worker)\b",
        ],
        "framework_names": ["Celery", "Bull"],
    },
}


# ── Entry Point Patterns ─────────────────────────────────────────────

ENTRY_POINT_SIGNALS: dict[str, dict] = {
    "http_server": {
        "python": re.compile(
            r"""(?i)(?:app\.run\(|uvicorn\.run|uvicorn\.install|gunicorn|hypercorn\.run|\.listen\(|\.serve_forever\()"""
        ),
        "javascript": re.compile(
            r"""(?i)(?:app\.listen\(|server\.listen\(|createServer\(|\.listen\()"""
        ),
        "java": re.compile(
            r"""(?i)(?:SpringApplication\.run|@SpringBootApplication|main\s*\(\s*String\s*\[\])"""
        ),
        "go": re.compile(
            r"""(?i)(?:http\.ListenAndServe|\.ListenAndServe\(|gin\.Default|echo\.New|fiber\.New)"""
        ),
        "ruby": re.compile(
            r"""(?i)(?:Rails\.application\.run|Sinatra::Application\.run|run\s+app)"""
        ),
        "php": re.compile(
            r"""(?i)(?:artisan\s+serve|php\s+server\.php|symfony\s+server:serve)"""
        ),
    },
    "cli": {
        "python": re.compile(
            r"""(?i)(?:@click\.command|@click\.group|argparse\.ArgumentParser|if\s+__name__\s*==\s*['"]__main__['"]|def\s+main\s*\(\))"""
        ),
        "javascript": re.compile(
            r"""(?i)(?:#!/usr/bin/env\s+node|\.command\s*\(|\.action\s*\(|yargs\.command)"""
        ),
        "go": re.compile(
            r"""(?i)(?:flag\.Parse\(\)|cobra\.Command|kingpin|os\.Args)"""
        ),
    },
    "worker": {
        "python": re.compile(
            r"""(?i)(?:@celery\.task|@shared_task|def\s+worker|class\s+\w+Task|huey\.task)"""
        ),
        "javascript": re.compile(
            r"""(?i)(?:Bull\(|new\s+Queue\(|process\s*\(|worker\.listen)"""
        ),
    },
    "scheduled_job": {
        "python": re.compile(
            r"""(?i)(?:@schedule|schedule\.|cron|periodic_task|crontab|APScheduler|apscheduler)"""
        ),
        "javascript": re.compile(
            r"""(?i)(?:cron\.\w+|node-cron|node-schedule|setInterval|setTimeout.*\d{6,})"""
        ),
    },
}


# ── API Endpoint Patterns ────────────────────────────────────────────

API_ENDPOINT_PATTERNS: dict[str, dict] = {
    "rest_fastapi": re.compile(
        r"""@(?:app|router|api_router)\.(?:get|post|put|delete|patch|head|options)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    "rest_flask": re.compile(
        r"""@(?:app|bp|blueprint)\.(?:route|get|post|put|delete|patch)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    "rest_django": re.compile(
        r"""path\s*\(\s*['"]([^'"]+)['"]|url\s*\(\s*r?['"]([^'"]+)['"]""",
    ),
    "rest_express": re.compile(
        r"""(?:app|router|server)\.(?:get|post|put|delete|patch|use)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    "rest_nestjs": re.compile(
        r"""@(?:Get|Post|Put|Delete|Patch|Head|Options)\s*\(\s*['"]([^'"]*)['"]\s*\)""",
    ),
    "rest_spring": re.compile(
        r"""@(?:GetMapping|PostMapping|PutMapping|DeleteMapping|PatchMapping|RequestMapping)\s*\(\s*(?:value\s*=\s*)?['"]([^'"]+)['"]""",
    ),
    "rest_gin": re.compile(
        r"""\.(?:GET|POST|PUT|DELETE|PATCH|Group)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    "rest_rails": re.compile(
        r"""(?:get|post|put|patch|delete)\s+['"]([^'"]+)['"]""",
    ),
    "rest_laravel": re.compile(
        r"""Route::(?:get|post|put|patch|delete)\s*\(\s*['"]([^'"]+)['"]""",
    ),
    "graphql_resolver": re.compile(
        r"""@(?:Query|Mutation|Subscription|ResolveField|Resolver)\s*\(\s*(?:['"]([^'"]*)['"]|\)?)""",
    ),
    "grpc_service": re.compile(
        r"""(?i)(?:service\s+\w+\s*\{|rpc\s+\w+\s*\(|grpc\.service|ServerServiceDefinition)""",
    ),
    "event_handler": re.compile(
        r"""(?:@event_handler|@on_event|@subscribe|addEventListener|\.on\s*\(\s*['"](\w+)['"]|signal\s*\.\s*connect)""",
    ),
    "webhook_handler": re.compile(
        r"""(?:webhook|@webhook|handle_webhook|verify_webhook|@stripe_webhook|@slack_webhook)""",
    ),
}


# ── Database Detection Patterns ───────────────────────────────────────

DATABASE_PATTERNS: dict[str, re.Pattern] = {
    "orm_model": re.compile(
        r"""(?i)(?:class\s+\w+\s*\(\s*(?:Base\.?declarative_base|Model|db\.Model|Base|\w+Base)\s*\)|@Entity|@Table\s*\(|@dataclass\s*\n.*Table)""",
    ),
    "migration_file": re.compile(
        r"""(?i)(?:alembic|migration|migrate|schema\.py|versions?/\d|\.up\.(?:sql|py)|\.down\.(?:sql|py))""",
    ),
    "sqlalchemy_model": re.compile(
        r"""(?:__tablename__|Column\s*\(|mapped_column|relationship\s*\()""",
    ),
    "django_model": re.compile(
        r"""(?:class\s+\w+\s*\(\s*models\.Model|models\.\w+Field|class\s+Meta)""",
    ),
    "sequelize_model": re.compile(
        r"""(?:Model\.init|sequelize\.define|DataTypes\.\w+|@Column\s*\(|@Table\s*\()""",
    ),
    "prisma_schema": re.compile(
        r"""(?:model\s+\w+\s*\{|enum\s+\w+\s*\{|datasource\s+\w+\s*\{)""",
    ),
    "database_url": re.compile(
        r"""(?i)(?:DATABASE_URL|DB_URL|DB_HOST|MYSQL_URL|POSTGRES_URL|MONGO_URL|REDIS_URL|connection_string|jdbc:|mysql://|postgres(?:ql)?://|mongodb://|redis://)""",
    ),
}


# ── Queue Detection Patterns ──────────────────────────────────────────

QUEUE_PATTERNS: dict[str, re.Pattern] = {
    "celery_task": re.compile(
        r"""(?:@shared_task|@celery\.task|\.delay\(|\.apply_async\(|current_app\.send_task)""",
    ),
    "bull_queue": re.compile(
        r"""(?:new\s+Bull\s*\(|Queue\s*\(\s*['"]|\.add\s*\(\s*['"]|\.process\s*\()""",
    ),
    "kafka_producer": re.compile(
        r"""(?:KafkaProducer|kafka\.producer|producer\.send|kafkaProducer)""",
    ),
    "kafka_consumer": re.compile(
        r"""(?:KafkaConsumer|kafka\.consumer|consumer\.poll|consumer\.subscribe)""",
    ),
    "rabbitmq": re.compile(
        r"""(?:pika\.|amqp\.|channel\.basic_publish|channel\.basic_consume|rabbitmq)""",
    ),
    "redis_queue": re.compile(
        r"""(?:redis\.(?:lpush|rpop|blpop|brpop|publish)|\.lpush\(|\.rpop\()""",
    ),
    "sqs": re.compile(
        r"""(?:sqs\.(?:send_message|receive_message|delete_message)|QueueUrl|sqs_client)""",
    ),
}


# ── External Dependency Patterns ──────────────────────────────────────

EXTERNAL_API_PATTERNS: dict[str, re.Pattern] = {
    "http_client": re.compile(
        r"""(?:requests\.(?:get|post|put|delete|patch|head|options|session)|httpx\.|aiohttp\.(?:ClientSession|get|post)|axios\.|fetch\(|http\.Client|urllib\.request|net\.http\.Get|HttpClient)""",
    ),
    "grpc_client": re.compile(
        r"""(?:grpc\.insecure_channel|grpc\.secure_channel|grpc\.channel_ready|stub\s*=\s*\w+Stub)""",
    ),
    "websocket_client": re.compile(
        r"""(?:websocket\.connect|WebSocket\(|socket\.io|ws\.connect|wss?://|SignalR)""",
    ),
    "email_client": re.compile(
        r"""(?:smtplib\.|smtp\.|sendgrid\.|mailgun\.|ses\.(?:send_email|send_raw_email)|SendGrid)""",
    ),
    "cloud_sdk": re.compile(
        r"""(?:boto3\.|aws-sdk|google\.cloud\.|azure\.|gcloud|@aws-sdk/)""",
    ),
    "graphql_client": re.compile(
        r"""(?:gql\.|graphql-ws|ApolloClient|useQuery|useMutation|graphql-request)""",
    ),
}


# ── ArchitectureDiscovery ────────────────────────────────────────────


class ArchitectureDiscovery:
    """Discover architectural patterns, layers, services, entry points,
    APIs, databases, queues, external dependencies, frameworks,
    configuration, and monorepo structure from indexed code data.

    Uses the adapter pattern — framework detection is data-driven
    and never makes hard-coded assumptions about the codebase.
    """

    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    # ── orchestration ────────────────────────────────────────────────

    async def discover_architecture(
        self, repo_id: str, index_id: str
    ) -> ArchitectureResult:
        """Run full architecture discovery and return structured results."""
        logger.info(
            "Starting architecture discovery for repo %s, index %s",
            repo_id, index_id,
        )

        layers = await self.detect_layers(repo_id)
        services = await self.detect_services(repo_id)
        entry_points = await self.detect_entry_points(repo_id)
        api_endpoints = await self.detect_api_endpoints(repo_id)
        databases = await self.detect_databases(repo_id)
        queues = await self.detect_queues(repo_id)
        external_deps = await self.detect_external_dependencies(repo_id)
        frameworks = await self.detect_frameworks(repo_id)
        configuration = await self.detect_configuration(repo_id)
        monorepo = await self.detect_monorepo_structure(repo_id)
        graph = await self.build_architecture_graph(repo_id, index_id)
        summary = await self.generate_repository_summary(repo_id, index_id)

        return ArchitectureResult(
            layers=layers,
            services=services,
            entry_points=entry_points,
            api_endpoints=api_endpoints,
            databases=databases,
            queues=queues,
            external_deps=external_deps,
            frameworks=frameworks,
            configuration=configuration,
            monorepo=monorepo,
            graph=graph,
            summary=summary,
        )

    # ── layer detection ──────────────────────────────────────────────

    async def detect_layers(self, repo_id: str) -> list[dict]:
        """Detect presentation, business logic, data access, and
        infrastructure layers based on file structure, imports, symbols,
        and framework usage.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        import_stmt = (
            select(CodeImport)
            .where(CodeImport.repository_id == UUID(repo_id))
        )
        import_result = await self.db.execute(import_stmt)
        imports = import_result.scalars().all()

        symbol_stmt = (
            select(CodeSymbol)
            .where(
                CodeSymbol.repository_id == UUID(repo_id),
                CodeSymbol.symbol_type.in_(["CLASS", "FUNCTION", "METHOD"]),
            )
        )
        symbol_result = await self.db.execute(symbol_stmt)
        symbols = symbol_result.scalars().all()

        import_text = " ".join(i.imported_name for i in imports)
        symbol_names = " ".join(s.name for s in symbols)

        layers: list[dict] = []

        for layer_name, signals in LAYER_SIGNALS.items():
            matched_files: list[dict] = []
            confidence_factors: list[float] = []

            for file_row in files:
                path = file_row.file_path
                score = 0.0

                for pat in signals.get("file_patterns", []):
                    if re.search(pat, path, re.IGNORECASE):
                        score += 0.3
                        break

                for pat in signals.get("symbol_patterns", []):
                    if re.search(pat, symbol_names, re.IGNORECASE):
                        score += 0.2
                        break

                for fw_name in signals.get("framework_names", []):
                    if fw_name.lower() in import_text.lower():
                        score += 0.3
                        break

                if score >= 0.3:
                    matched_files.append({
                        "file_path": file_row.file_path,
                        "file_id": str(file_row.id),
                        "language": file_row.language,
                        "score": round(score, 2),
                    })
                    confidence_factors.append(score)

            if matched_files:
                avg_confidence = (
                    sum(confidence_factors) / len(confidence_factors)
                    if confidence_factors else 0.0
                )
                layers.append({
                    "layer": layer_name,
                    "file_count": len(matched_files),
                    "confidence": round(min(avg_confidence, 0.95), 2),
                    "files": sorted(
                        matched_files, key=lambda f: f["score"], reverse=True
                    )[:50],
                })

        layers.sort(key=lambda l: l["confidence"], reverse=True)
        return layers

    # ── service detection ────────────────────────────────────────────

    async def detect_services(self, repo_id: str) -> list[dict]:
        """Detect microservices, modules, packages, and logical service
        boundaries from directory structure, entry points, and imports.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        dir_files: dict[str, list[CodeFile]] = defaultdict(list)
        for f in files:
            parts = f.file_path.replace("\\", "/").split("/")
            if len(parts) >= 2:
                dir_files[parts[0]].append(f)

        services: list[dict] = []

        for dir_name, dir_file_list in dir_files.items():
            lang_counts: dict[str, int] = Counter()
            has_entry = False
            has_config = False
            has_tests = False
            has_models = False

            for f in dir_file_list:
                if f.language:
                    lang_counts[f.language] += 1
                if f.is_test_file:
                    has_tests = True
                if f.is_config_file:
                    has_config = True

            entry_extensions = {
                "main.py", "app.py", "server.py", "index.py",
                "main.js", "server.js", "app.js", "index.js",
                "main.ts", "server.ts", "app.ts", "index.ts",
                "main.go", "cmd", "main.rb", "app.php",
            }
            model_keywords = {
                "model", "models", "entity", "entities",
                "schema", "schemas", "migration", "migrations",
            }
            service_keywords = {
                "service", "services", "handler", "handlers",
                "controller", "controllers", "resolver", "resolvers",
                "usecase", "usecases", "interactor",
            }

            for f in dir_file_list:
                basename = f.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
                if basename in entry_extensions or basename.startswith("main."):
                    has_entry = True
                if any(kw in basename for kw in model_keywords):
                    has_models = True
                if any(kw in basename for kw in service_keywords):
                    has_entry = True

            primary_lang = lang_counts.most_common(1)[0][0] if lang_counts else "unknown"

            score = 0.0
            if has_entry:
                score += 0.4
            if has_config:
                score += 0.15
            if has_tests:
                score += 0.1
            if has_models:
                score += 0.1
            if len(dir_file_list) >= 3:
                score += 0.15
            if len(lang_counts) > 1:
                score += 0.1

            if score >= 0.4:
                services.append({
                    "name": dir_name,
                    "file_count": len(dir_file_list),
                    "primary_language": primary_lang,
                    "has_entry_point": has_entry,
                    "has_config": has_config,
                    "has_tests": has_tests,
                    "has_models": has_models,
                    "confidence": round(min(score, 0.95), 2),
                    "sample_files": [
                        f.file_path for f in dir_file_list[:10]
                    ],
                })

        services.sort(key=lambda s: s["confidence"], reverse=True)
        return services

    # ── entry point detection ────────────────────────────────────────

    async def detect_entry_points(self, repo_id: str) -> list[dict]:
        """Detect application entry points: HTTP servers, CLI entry points,
        workers, and scheduled jobs.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        entry_points: list[dict] = []

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            language = (file_row.language or "").lower()
            if language in ("python", "py"):
                lang_key = "python"
            elif language in ("javascript", "js", "typescript", "ts", "tsx", "jsx"):
                lang_key = "javascript"
            elif language in ("java",):
                lang_key = "java"
            elif language in ("go",):
                lang_key = "go"
            elif language in ("ruby", "rb"):
                lang_key = "ruby"
            elif language in ("php",):
                lang_key = "php"
            else:
                continue

            for ep_type, lang_patterns in ENTRY_POINT_SIGNALS.items():
                pattern = lang_patterns.get(lang_key)
                if pattern and pattern.search(content):
                    lines = content.split("\n")
                    match = pattern.search(content)
                    line_num = content[:match.start()].count("\n") + 1 if match else 1
                    snippet = self._extract_snippet(lines, line_num, context=2)

                    entry_points.append({
                        "type": ep_type,
                        "file_path": file_row.file_path,
                        "file_id": str(file_row.id),
                        "language": file_row.language,
                        "line": line_num,
                        "evidence": snippet,
                        "confidence": 0.8,
                    })

        if not any(
            ep["type"] == "http_server" for ep in entry_points
        ):
            main_files_stmt = (
                select(CodeFile)
                .where(
                    CodeFile.repository_id == UUID(repo_id),
                    CodeFile.file_name.in_([
                        "main.py", "app.py", "server.py",
                        "main.js", "server.js", "app.js", "index.js",
                        "main.ts", "server.ts",
                        "main.go",
                    ]),
                )
            )
            main_result = await self.db.execute(main_files_stmt)
            for f in main_result.scalars().all():
                entry_points.append({
                    "type": "http_server_candidate",
                    "file_path": f.file_path,
                    "file_id": str(f.id),
                    "language": f.language,
                    "line": None,
                    "evidence": f"Convention-based entry point: {f.file_name}",
                    "confidence": 0.4,
                })

        return entry_points

    # ── API endpoint detection ───────────────────────────────────────

    async def detect_api_endpoints(self, repo_id: str) -> list[dict]:
        """Detect REST endpoints, GraphQL resolvers, gRPC services,
        event handlers, and webhook handlers from source code.
        """
        stmt = (
            select(CodeFile)
            .where(
                CodeFile.repository_id == UUID(repo_id),
                CodeFile.language.in_([
                    "python", "py", "javascript", "js",
                    "typescript", "ts", "tsx", "jsx",
                    "java", "go", "rb", "ruby", "php",
                ]),
            )
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        endpoints: list[dict] = []

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            for pattern_name, pattern in API_ENDPOINT_PATTERNS.items():
                for match in pattern.finditer(content):
                    route = match.group(1) if match.lastindex and match.group(1) else ""
                    line_num = content[:match.start()].count("\n") + 1
                    lines = content.split("\n")
                    snippet = self._extract_snippet(lines, line_num, context=1)

                    method = self._infer_http_method(pattern_name, route, snippet)

                    endpoints.append({
                        "type": self._endpoint_type(pattern_name),
                        "route": route,
                        "method": method,
                        "file_path": file_row.file_path,
                        "file_id": str(file_row.id),
                        "language": file_row.language,
                        "line": line_num,
                        "evidence": snippet,
                        "pattern": pattern_name,
                        "confidence": 0.85,
                    })

        endpoints.sort(key=lambda e: (e["file_path"], e.get("line", 0)))
        return endpoints

    # ── database detection ───────────────────────────────────────────

    async def detect_databases(self, repo_id: str) -> list[dict]:
        """Detect database models, ORM usage, migration files, and
        database connection configuration.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        databases: list[dict] = []
        seen_db_types: set[str] = set()

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            for pattern_name, pattern in DATABASE_PATTERNS.items():
                matches = list(pattern.finditer(content))
                if not matches:
                    continue

                file_path = file_row.file_path
                line_num = content[:matches[0].start()].count("\n") + 1
                lines = content.split("\n")
                snippet = self._extract_snippet(lines, line_num, context=2)

                db_type = self._infer_db_type(content, file_path)
                if db_type and db_type not in seen_db_types:
                    seen_db_types.add(db_type)

                databases.append({
                    "type": pattern_name,
                    "db_engine": db_type or "unknown",
                    "file_path": file_path,
                    "file_id": str(file_row.id),
                    "language": file_row.language,
                    "line": line_num,
                    "match_count": len(matches),
                    "evidence": snippet,
                    "confidence": min(0.5 + 0.1 * len(matches), 0.95),
                })

        return databases

    # ── queue detection ──────────────────────────────────────────────

    async def detect_queues(self, repo_id: str) -> list[dict]:
        """Detect message queue consumers and producers."""
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        queues: list[dict] = []

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            for pattern_name, pattern in QUEUE_PATTERNS.items():
                matches = list(pattern.finditer(content))
                if not matches:
                    continue

                queue_type = self._classify_queue_role(content, pattern_name)
                line_num = content[:matches[0].start()].count("\n") + 1
                lines = content.split("\n")
                snippet = self._extract_snippet(lines, line_num, context=2)

                queues.append({
                    "type": pattern_name,
                    "role": queue_type,
                    "file_path": file_row.file_path,
                    "file_id": str(file_row.id),
                    "language": file_row.language,
                    "line": line_num,
                    "match_count": len(matches),
                    "evidence": snippet,
                    "confidence": min(0.5 + 0.1 * len(matches), 0.9),
                })

        return queues

    # ── external dependency detection ────────────────────────────────

    async def detect_external_dependencies(self, repo_id: str) -> list[dict]:
        """Detect external API calls, HTTP clients, cloud SDK usage,
        and other external dependencies.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        external_deps: list[dict] = []

        for file_row in files:
            content = await self._read_file_content(file_row)
            if not content:
                continue

            for pattern_name, pattern in EXTERNAL_API_PATTERNS.items():
                matches = list(pattern.finditer(content))
                if not matches:
                    continue

                line_num = content[:matches[0].start()].count("\n") + 1
                lines = content.split("\n")
                snippet = self._extract_snippet(lines, line_num, context=2)

                external_deps.append({
                    "type": pattern_name,
                    "file_path": file_row.file_path,
                    "file_id": str(file_row.id),
                    "language": file_row.language,
                    "line": line_num,
                    "match_count": len(matches),
                    "evidence": snippet,
                    "confidence": min(0.55 + 0.08 * len(matches), 0.9),
                })

        return external_deps

    # ── framework detection ──────────────────────────────────────────

    async def detect_frameworks(self, repo_id: str) -> list[dict]:
        """Detect frameworks using import patterns, config files, and
        project structure. Uses adapter pattern — never hard-coded
        assumptions.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        import_stmt = (
            select(CodeImport)
            .where(CodeImport.repository_id == UUID(repo_id))
        )
        import_result = await self.db.execute(import_stmt)
        imports = import_result.scalars().all()

        all_import_names = [i.imported_name for i in imports]
        import_text = "\n".join(all_import_names)

        detected_frameworks: dict[str, dict] = {}

        for adapter in FRAMEWORK_ADAPTERS:
            score = 0.0
            evidence_list: list[str] = []

            for pat in adapter.get("import_patterns", []):
                if re.search(pat, import_text):
                    score += 0.5
                    evidence_list.append(f"import pattern: {pat}")
                    break

            config_text = ""
            file_names: list[str] = []
            for f in files:
                file_names.append(f.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1])

            for pat in adapter.get("config_patterns", []):
                for f in files:
                    content = await self._read_file_content(f)
                    if content and re.search(pat, content):
                        score += 0.3
                        evidence_list.append(f"config pattern in {f.file_path}: {pat}")
                        break
                if score >= 0.3:
                    break

            for fpat in adapter.get("file_patterns", []):
                if any(fpat in fn for fn in file_names):
                    score += 0.2
                    evidence_list.append(f"file pattern: {fpat}")
                    break

            if score >= 0.5:
                fw_name = adapter["name"]
                if fw_name not in detected_frameworks or score > detected_frameworks[fw_name]["score"]:
                    detected_frameworks[fw_name] = {
                        "name": fw_name,
                        "language": adapter["language"],
                        "category": adapter["category"],
                        "score": round(min(score, 0.95), 2),
                        "confidence": round(min(score, 0.95), 2),
                        "evidence": evidence_list[:5],
                    }

        result_list = sorted(
            detected_frameworks.values(),
            key=lambda fw: fw["score"],
            reverse=True,
        )
        return result_list

    # ── configuration detection ──────────────────────────────────────

    async def detect_configuration(self, repo_id: str) -> list[dict]:
        """Parse package manifests, requirements, Dockerfiles, Kubernetes
        YAML, CI/CD config, and env templates.
        """
        config_files = {
            "python": [
                "requirements.txt", "setup.py", "setup.cfg", "pyproject.toml",
                "Pipfile", "poetry.lock",
            ],
            "javascript": [
                "package.json", "package-lock.json", "yarn.lock",
                "pnpm-lock.yaml", "tsconfig.json", "webpack.config.js",
                "vite.config.js", "vite.config.ts", "rollup.config.js",
            ],
            "java": [
                "pom.xml", "build.gradle", "build.gradle.kts",
                "settings.gradle", "gradle.properties",
            ],
            "go": ["go.mod", "go.sum"],
            "ruby": ["Gemfile", "Gemfile.lock", ".ruby-version"],
            "php": ["composer.json", "composer.lock"],
            "rust": ["Cargo.toml", "Cargo.lock"],
        }

        infrastructure_files = {
            "Dockerfile": "docker",
            "docker-compose.yml": "docker_compose",
            "docker-compose.yaml": "docker_compose",
            "docker-compose.dev.yml": "docker_compose",
            "docker-compose.prod.yml": "docker_compose",
            ".env": "env_template",
            ".env.example": "env_template",
            ".env.sample": "env_template",
            ".env.template": "env_template",
            ".gitignore": "git",
            ".dockerignore": "docker",
            "Makefile": "build",
            "Procfile": "deployment",
            "Vagrantfile": "infrastructure",
        }

        k8s_patterns = re.compile(
            r"""(?i)(?:apiVersion:\s+(?:apps/v1|v1)|kind:\s+(?:Deployment|Service|ConfigMap|Secret|Ingress|StatefulSet|DaemonSet|CronJob|Job|Pod))"""
        )

        cicd_patterns = {
            ".github/workflows": "github_actions",
            ".gitlab-ci.yml": "gitlab_ci",
            ".gitlab-ci.yaml": "gitlab_ci",
            "Jenkinsfile": "jenkins",
            ".circleci/config.yml": "circle_ci",
            ".travis.yml": "travis_ci",
            "azure-pipelines.yml": "azure_pipelines",
            "cloudbuild.yaml": "cloud_build",
            "bitbucket-pipelines.yml": "bitbucket_pipelines",
        }

        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        configurations: list[dict] = []

        for file_row in files:
            file_path = file_row.file_path
            file_name = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

            config_type = None

            for lang, manifests in config_files.items():
                if file_name in manifests:
                    config_type = f"package_manifest_{lang}"
                    break

            if not config_type:
                for infra_name, infra_type in infrastructure_files.items():
                    if file_name == infra_name or file_name.endswith(infra_name):
                        config_type = infra_type
                        break

            if not config_type:
                for cicd_path, cicd_type in cicd_patterns.items():
                    if cicd_path in file_path:
                        config_type = f"ci_cd_{cicd_type}"
                        break

            if not config_type:
                if file_name.endswith((".yaml", ".yml")):
                    content = await self._read_file_content(file_row)
                    if content and k8s_patterns.search(content):
                        config_type = "kubernetes"

            if not config_type:
                if file_name.startswith(".env"):
                    config_type = "env_template"
                elif file_name == "Dockerfile" or file_name.startswith("Dockerfile."):
                    config_type = "docker"
                elif file_name.endswith((".ini", ".cfg", ".conf", ".properties")):
                    config_type = "service_config"
                elif file_name.endswith((".toml",)):
                    config_type = "toml_config"

            if config_type:
                configurations.append({
                    "type": config_type,
                    "file_path": file_path,
                    "file_id": str(file_row.id),
                    "file_name": file_name,
                    "language": file_row.language,
                    "size_bytes": file_row.size_bytes,
                    "is_config_file": file_row.is_config_file,
                })

        configurations.sort(key=lambda c: c["type"])
        return configurations

    # ── monorepo structure detection ─────────────────────────────────

    async def detect_monorepo_structure(self, repo_id: str) -> list[dict]:
        """Detect workspace roots, packages, apps, shared libraries,
        and cross-package dependencies.
        """
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        workspaces: list[dict] = []

        workspace_config_files = {
            "package.json": re.compile(r""""workspaces"\s*:"""),
            "lerna.json": re.compile(r""""packages"\s*:"""),
            "pnpm-workspace.yaml": re.compile(r"""packages:"""),
            "turbo.json": re.compile(r""""pipeline"\s*:"""),
            "nx.json": re.compile(r"""(?i)"projects"\s*:"""),
            "rush.json": re.compile(r""""projects"\s*:"""),
            "Cargo.toml": re.compile(r"""\[workspace\]"""),
            "go.work": re.compile(r"""^use\s+"""),
            "pyproject.toml": re.compile(r"""\[tool\.hatch\.build\]"""),
        }

        for file_row in files:
            file_name = file_row.file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

            if file_name not in workspace_config_files:
                continue

            content = await self._read_file_content(file_row)
            if not content:
                continue

            pattern = workspace_config_files[file_name]
            if not pattern.search(content):
                continue

            ws_type = self._classify_workspace_type(file_name, content)
            packages = self._extract_workspace_packages(file_name, content)

            workspaces.append({
                "type": ws_type,
                "config_file": file_row.file_path,
                "config_file_id": str(file_row.id),
                "packages": packages,
                "package_count": len(packages),
                "confidence": 0.85,
            })

        if not workspaces:
            dir_map: dict[str, int] = Counter()
            for f in files:
                parts = f.file_path.replace("\\", "/").split("/")
                if len(parts) >= 2:
                    dir_map[parts[0]] += 1

            monorepo_indicators = {
                "packages", "apps", "services", "libs", "shared",
                "modules", "microservices", "internal",
            }
            detected = [
                d for d in dir_map
                if d.lower() in monorepo_indicators
            ]
            if len(detected) >= 2:
                workspaces.append({
                    "type": "monorepo_by_convention",
                    "config_file": "",
                    "config_file_id": None,
                    "packages": detected,
                    "package_count": len(detected),
                    "confidence": 0.5,
                })

        return workspaces

    # ── architecture graph ───────────────────────────────────────────

    async def build_architecture_graph(
        self, repo_id: str, index_id: str
    ) -> dict:
        """Build relationships between services, packages, modules,
        databases, APIs, queues, and external dependencies.
        """
        layers = await self.detect_layers(repo_id)
        services = await self.detect_services(repo_id)
        entry_points = await self.detect_entry_points(repo_id)
        api_endpoints = await self.detect_api_endpoints(repo_id)
        databases = await self.detect_databases(repo_id)
        queues = await self.detect_queues(repo_id)
        external_deps = await self.detect_external_dependencies(repo_id)
        frameworks = await self.detect_frameworks(repo_id)

        nodes: list[dict] = []
        edges: list[dict] = []

        for layer in layers:
            node_id = f"layer:{layer['layer']}"
            nodes.append({
                "id": node_id,
                "type": "layer",
                "label": layer["layer"],
                "confidence": layer["confidence"],
                "file_count": layer["file_count"],
            })

        for service in services:
            node_id = f"service:{service['name']}"
            nodes.append({
                "id": node_id,
                "type": "service",
                "label": service["name"],
                "language": service["primary_language"],
                "confidence": service["confidence"],
                "file_count": service["file_count"],
            })

        for ep in entry_points:
            node_id = f"entry_point:{ep['file_path']}:{ep['type']}"
            nodes.append({
                "id": node_id,
                "type": "entry_point",
                "label": ep["type"],
                "file_path": ep["file_path"],
                "language": ep["language"],
                "confidence": ep["confidence"],
            })

        for api in api_endpoints:
            route = api.get("route", "")
            node_id = f"api:{api['file_path']}:{route}"
            nodes.append({
                "id": node_id,
                "type": "api_endpoint",
                "label": route,
                "method": api.get("method", ""),
                "file_path": api["file_path"],
                "confidence": api["confidence"],
            })

        for db in databases:
            node_id = f"database:{db['db_engine']}:{db['type']}"
            if not any(n["id"] == node_id for n in nodes):
                nodes.append({
                    "id": node_id,
                    "type": "database",
                    "label": db["db_engine"],
                    "subtype": db["type"],
                    "confidence": db["confidence"],
                })

        for q in queues:
            node_id = f"queue:{q['type']}:{q['file_path']}"
            nodes.append({
                "id": node_id,
                "type": "queue",
                "label": q["type"],
                "role": q.get("role", ""),
                "file_path": q["file_path"],
                "confidence": q["confidence"],
            })

        for dep in external_deps:
            node_id = f"external:{dep['type']}:{dep['file_path']}"
            nodes.append({
                "id": node_id,
                "type": "external_dependency",
                "label": dep["type"],
                "file_path": dep["file_path"],
                "confidence": dep["confidence"],
            })

        for fw in frameworks:
            node_id = f"framework:{fw['name']}"
            nodes.append({
                "id": node_id,
                "type": "framework",
                "label": fw["name"],
                "category": fw["category"],
                "language": fw["language"],
                "confidence": fw["confidence"],
            })

        for service in services:
            svc_id = f"service:{service['name']}"
            svc_lang = service["primary_language"]

            for fw in frameworks:
                if fw["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"framework:{fw['name']}",
                        "type": "uses_framework",
                    })

            for ep in entry_points:
                if ep["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"entry_point:{ep['file_path']}:{ep['type']}",
                        "type": "has_entry_point",
                    })

            for api in api_endpoints:
                if api["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"api:{api['file_path']}:{api.get('route', '')}",
                        "type": "exposes_api",
                    })

            for db in databases:
                if db["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"database:{db['db_engine']}:{db['type']}",
                        "type": "accesses_database",
                    })

            for q in queues:
                if q["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"queue:{q['type']}:{q['file_path']}",
                        "type": "uses_queue",
                    })

            for dep in external_deps:
                if dep["language"] == svc_lang:
                    edges.append({
                        "source": svc_id,
                        "target": f"external:{dep['type']}:{dep['file_path']}",
                        "type": "calls_external",
                    })

        return {
            "nodes": nodes,
            "edges": edges,
            "metadata": {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    # ── repository summary ───────────────────────────────────────────

    async def generate_repository_summary(
        self, repo_id: str, index_id: str
    ) -> RepositorySummary:
        """Generate structured metadata about the repository."""
        stmt = (
            select(CodeFile)
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        result = await self.db.execute(stmt)
        files = result.scalars().all()

        symbol_stmt = (
            select(func.count()).where(CodeSymbol.repository_id == UUID(repo_id))
        )
        symbol_result = await self.db.execute(symbol_stmt)
        total_symbols = symbol_result.scalar() or 0

        loc_stmt = (
            select(func.coalesce(func.sum(CodeFile.line_count), 0))
            .where(CodeFile.repository_id == UUID(repo_id))
        )
        loc_result = await self.db.execute(loc_stmt)
        total_lines = loc_result.scalar() or 0

        languages: dict[str, int] = Counter()
        test_files: list[str] = []
        for f in files:
            if f.language:
                languages[f.language] += 1
            if f.is_test_file:
                test_files.append(f.file_path)

        frameworks = await self.detect_frameworks(repo_id)
        entry_points = await self.detect_entry_points(repo_id)
        api_endpoints = await self.detect_api_endpoints(repo_id)
        databases = await self.detect_databases(repo_id)
        queues = await self.detect_queues(repo_id)
        configuration = await self.detect_configuration(repo_id)

        packages: list[str] = []
        pkg_stmt = (
            select(CodeImport.imported_name)
            .where(
                CodeImport.repository_id == UUID(repo_id),
                CodeImport.is_external.is_(True),
                CodeImport.is_stdlib.is_(False),
            )
            .distinct()
        )
        pkg_result = await self.db.execute(pkg_stmt)
        packages = sorted([p[0].split(".")[0] for p in pkg_result.all()])

        deployment_files = [
            c["file_path"] for c in configuration
            if c["type"] in (
                "docker", "docker_compose", "kubernetes",
                "deployment", "github_actions", "gitlab_ci",
                "jenkins", "circle_ci", "travis_ci",
                "azure_pipelines", "cloud_build",
            )
        ]

        arch_pattern = self._infer_architecture_pattern(
            frameworks, services=[], entry_points=entry_points,
            databases=databases, queues=queues,
        )

        services = await self.detect_services(repo_id)

        return RepositorySummary(
            languages=dict(languages),
            frameworks=[
                {"name": fw["name"], "category": fw["category"]}
                for fw in frameworks
            ],
            packages=packages[:100],
            services=[
                {"name": s["name"], "language": s["primary_language"]}
                for s in services
            ],
            entry_points=[
                {"type": ep["type"], "file_path": ep["file_path"]}
                for ep in entry_points
            ],
            apis=[
                {"route": api.get("route", ""), "method": api.get("method", "")}
                for api in api_endpoints[:50]
            ],
            databases=[
                {"engine": db["db_engine"], "type": db["type"]}
                for db in databases
            ],
            queues=[
                {"type": q["type"], "role": q.get("role", "")}
                for q in queues
            ],
            deployment_config=deployment_files,
            test_files=test_files[:100],
            architecture_pattern=arch_pattern,
            total_files=len(files),
            total_symbols=total_symbols,
            total_lines=total_lines,
        )

    # ── private helpers ──────────────────────────────────────────────

    async def _read_file_content(self, file_row: CodeFile) -> str | None:
        try:
            with open(
                file_row.file_path, "r", encoding="utf-8", errors="replace"
            ) as f:
                return f.read()
        except (OSError, IOError, ValueError):
            return None

    @staticmethod
    def _extract_snippet(
        lines: list[str], line_num: int, context: int = 2
    ) -> str:
        start = max(0, line_num - 1 - context)
        end = min(len(lines), line_num + context)
        snippet_lines = []
        for i in range(start, end):
            prefix = ">>> " if i == line_num - 1 else "    "
            snippet_lines.append(f"{prefix}{i + 1}: {lines[i]}")
        return "\n".join(snippet_lines)

    @staticmethod
    def _infer_http_method(pattern_name: str, route: str, snippet: str) -> str:
        if "get" in pattern_name.lower() or "Get" in pattern_name:
            return "GET"
        if "post" in pattern_name.lower() or "Post" in pattern_name:
            return "POST"
        if "put" in pattern_name.lower() or "Put" in pattern_name:
            return "PUT"
        if "delete" in pattern_name.lower() or "Delete" in pattern_name:
            return "DELETE"
        if "patch" in pattern_name.lower() or "Patch" in pattern_name:
            return "PATCH"

        lower_snippet = snippet.lower()
        if ".get(" in lower_snippet or "@get" in lower_snippet:
            return "GET"
        if ".post(" in lower_snippet or "@post" in lower_snippet:
            return "POST"
        if ".put(" in lower_snippet or "@put" in lower_snippet:
            return "PUT"
        if ".delete(" in lower_snippet or "@delete" in lower_snippet:
            return "DELETE"
        if ".patch(" in lower_snippet or "@patch" in lower_snippet:
            return "PATCH"

        return "ANY"

    @staticmethod
    def _endpoint_type(pattern_name: str) -> str:
        type_map = {
            "rest_fastapi": "REST",
            "rest_flask": "REST",
            "rest_django": "REST",
            "rest_express": "REST",
            "rest_nestjs": "REST",
            "rest_spring": "REST",
            "rest_gin": "REST",
            "rest_rails": "REST",
            "rest_laravel": "REST",
            "graphql_resolver": "GraphQL",
            "grpc_service": "gRPC",
            "event_handler": "event",
            "webhook_handler": "webhook",
        }
        return type_map.get(pattern_name, "unknown")

    @staticmethod
    def _infer_db_type(content: str, file_path: str) -> str | None:
        if "sqlalchemy" in content.lower() or "postgresql" in content.lower():
            return "postgresql"
        if "mysql" in content.lower():
            return "mysql"
        if "sqlite" in content.lower() or "sqlite3" in content.lower():
            return "sqlite"
        if "mongodb" in content.lower() or "pymongo" in content.lower():
            return "mongodb"
        if "redis" in content.lower():
            return "redis"
        if "elasticsearch" in content.lower() or "elastic" in content.lower():
            return "elasticsearch"
        if "dynamodb" in content.lower():
            return "dynamodb"
        if "cassandra" in content.lower():
            return "cassandra"
        if "neo4j" in content.lower():
            return "neo4j"
        if ".env" in file_path or "config" in file_path.lower():
            if "postgres" in content.lower():
                return "postgresql"
            if "mysql" in content.lower():
                return "mysql"
            if "mongo" in content.lower():
                return "mongodb"
        return None

    @staticmethod
    def _classify_queue_role(content: str, pattern_name: str) -> str:
        lower = content.lower()
        has_publish = any(
            kw in lower
            for kw in ("send", "publish", "produce", "push", "dispatch", "emit")
        )
        has_consume = any(
            kw in lower
            for kw in ("receive", "consume", "subscribe", "listen", "poll", "handle", "process")
        )
        if has_publish and has_consume:
            return "producer_consumer"
        if has_publish:
            return "producer"
        if has_consume:
            return "consumer"
        return "unknown"

    @staticmethod
    def _classify_workspace_type(file_name: str, content: str) -> str:
        if file_name == "lerna.json":
            return "lerna"
        if file_name == "turbo.json":
            return "turborepo"
        if file_name == "nx.json":
            return "nx"
        if file_name == "rush.json":
            return "rush"
        if file_name == "pnpm-workspace.yaml":
            return "pnpm_workspace"
        if file_name == "Cargo.toml":
            return "cargo_workspace"
        if file_name == "go.work":
            return "go_workspace"
        if file_name == "package.json":
            if '"workspaces"' in content:
                return "npm_workspace"
        return "unknown"

    @staticmethod
    def _extract_workspace_packages(
        file_name: str, content: str
    ) -> list[str]:
        packages: list[str] = []

        import json as _json

        if file_name == "package.json":
            try:
                data = _json.loads(content)
                ws = data.get("workspaces", [])
                if isinstance(ws, list):
                    packages = ws
                elif isinstance(ws, dict):
                    packages = ws.get("packages", [])
            except (_json.JSONDecodeError, ValueError):
                pass
        elif file_name == "lerna.json":
            try:
                data = _json.loads(content)
                packages = data.get("packages", [])
            except (_json.JSONDecodeError, ValueError):
                pass
        elif file_name == "pnpm-workspace.yaml":
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("- "):
                    pkg = stripped[2:].strip().strip("'\"")
                    if pkg:
                        packages.append(pkg)
        elif file_name == "go.work":
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("use "):
                    paths = stripped[4:].strip().strip("()").strip()
                    for p in paths.split("\n"):
                        p = p.strip()
                        if p:
                            packages.append(p)
        elif file_name == "Cargo.toml":
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("members") and "=" in stripped:
                    val = stripped.split("=", 1)[1].strip().strip("[]")
                    for p in val.split(","):
                        p = p.strip().strip("'\"")
                        if p:
                            packages.append(p)

        return packages

    @staticmethod
    def _infer_architecture_pattern(
        frameworks: list[dict],
        services: list[dict],
        entry_points: list[dict],
        databases: list[dict],
        queues: list[dict],
    ) -> str:
        fw_categories = Counter(fw.get("category", "") for fw in frameworks)

        has_frontend = fw_categories.get("frontend", 0) > 0
        has_backend = fw_categories.get("backend", 0) > 0

        http_eps = sum(
            1 for ep in entry_points
            if ep.get("type") in ("http_server", "http_server_candidate")
        )

        if len(services) > 1:
            return "microservices"
        if has_frontend and has_backend:
            return "monolith_fullstack"
        if has_backend and len(databases) > 2:
            return "layered"
        if queues and has_backend:
            return "event_driven"
        if http_eps > 0 and fw_categories.get("backend", 0) > 0:
            return "monolith"
        if has_frontend:
            return "frontend_only"
        return "unknown"
