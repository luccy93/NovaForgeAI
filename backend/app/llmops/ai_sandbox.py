import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class SandboxEnvironment(Enum):
    ISOLATED = "isolated"
    SHARED = "shared"
    TESTING = "testing"
    STAGING = "staging"
    PREVIEW = "preview"


class SandboxStatus(Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class TestType(Enum):
    PROMPT = "prompt"
    MODEL = "model"
    AGENT = "agent"
    EMBEDDING = "embedding"
    RETRIEVAL_PIPELINE = "retrieval_pipeline"
    CHAIN = "chain"
    TOOL = "tool"


@dataclass
class Sandbox:
    id: str = ""
    name: str = ""
    environment: SandboxEnvironment = SandboxEnvironment.ISOLATED
    status: SandboxStatus = SandboxStatus.CREATED
    test_type: TestType = TestType.PROMPT
    org_id: str = ""
    workspace_id: Optional[str] = None
    config: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)
    created_at: str = ""
    expires_at: str = ""
    completed_at: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        if not self.created_at:
            self.created_at = now.isoformat()
        if not self.expires_at:
            expiry = now.replace(hour=now.hour + 24)
            self.expires_at = expiry.isoformat()

    def is_expired(self) -> bool:
        if not self.expires_at:
            return False
        return datetime.fromisoformat(self.expires_at) < datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["environment"] = self.environment.value
        d["status"] = self.status.value
        d["test_type"] = self.test_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Sandbox":
        if "environment" in data:
            data["environment"] = SandboxEnvironment(data["environment"])
        if "status" in data:
            data["status"] = SandboxStatus(data["status"])
        if "test_type" in data:
            data["test_type"] = TestType(data["test_type"])
        return cls(**data)


@dataclass
class SandboxTest:
    id: str = ""
    sandbox_id: str = ""
    name: str = ""
    test_type: TestType = TestType.PROMPT
    input: dict = field(default_factory=dict)
    expected_output: str = ""
    actual_output: str = ""
    passed: bool = False
    score: float = 0.0
    latency_ms: float = 0.0
    cost: float = 0.0
    errors: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["test_type"] = self.test_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxTest":
        if "test_type" in data:
            data["test_type"] = TestType(data["test_type"])
        return cls(**data)


@dataclass
class SandboxTemplate:
    id: str = ""
    name: str = ""
    test_type: TestType = TestType.PROMPT
    template_config: dict = field(default_factory=dict)
    default_inputs: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["test_type"] = self.test_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxTemplate":
        if "test_type" in data:
            data["test_type"] = TestType(data["test_type"])
        return cls(**data)


@dataclass
class SandboxReport:
    id: str = ""
    sandbox_id: str = ""
    summary: str = ""
    test_count: int = 0
    passed: int = 0
    failed: int = 0
    avg_score: float = 0.0
    total_cost: float = 0.0
    recommendations: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SandboxReport":
        return cls(**data)


class SandboxManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/sandbox")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.sandboxes: dict[str, Sandbox] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_sandbox_path(self, sandbox_id: str) -> Path:
        return self.storage_dir / f"sandbox_{sandbox_id}.json"

    def _save_sandbox(self, sandbox: Sandbox):
        path = self._get_sandbox_path(sandbox.id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sandbox.to_dict(), f, indent=2)
            self.telemetry["sandboxes_saved"] += 1
        except Exception as e:
            logger.error("Failed to save sandbox %s: %s", sandbox.id, e)

    def _load(self):
        if not self.storage_dir.exists():
            return
        try:
            for path in self.storage_dir.glob("sandbox_*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    sandbox = Sandbox.from_dict(data)
                    self.sandboxes[sandbox.id] = sandbox
                except Exception as e:
                    logger.warning("Failed to load sandbox from %s: %s", path, e)
            self.telemetry["sandboxes_loaded"] = len(self.sandboxes)
        except Exception as e:
            logger.error("Failed to load sandboxes: %s", e)

    def create_sandbox(self, name: str, environment: SandboxEnvironment,
                       test_type: TestType, org_id: str,
                       config: Optional[dict] = None,
                       expires_in_hours: int = 24) -> Sandbox:
        now = datetime.now(timezone.utc)
        from datetime import timedelta
        expiry = now + timedelta(hours=expires_in_hours)
        sandbox = Sandbox(
            name=name,
            environment=environment,
            test_type=test_type,
            org_id=org_id,
            config=config or {},
            expires_at=expiry.isoformat(),
        )
        self.sandboxes[sandbox.id] = sandbox
        self._save_sandbox(sandbox)
        self.telemetry["sandboxes_created"] += 1
        logger.info("Created sandbox %s: %s [%s]", sandbox.id, name, environment.value)
        return sandbox

    def get_sandbox(self, sandbox_id: str) -> Optional[Sandbox]:
        return self.sandboxes.get(sandbox_id)

    def list_sandboxes(self, org_id: Optional[str] = None,
                       status: Optional[SandboxStatus] = None) -> list[Sandbox]:
        results = list(self.sandboxes.values())
        if org_id:
            results = [s for s in results if s.org_id == org_id]
        if status:
            results = [s for s in results if s.status == status]
        return sorted(results, key=lambda s: s.created_at, reverse=True)

    def terminate_sandbox(self, sandbox_id: str):
        sandbox = self.sandboxes.get(sandbox_id)
        if not sandbox:
            return
        sandbox.status = SandboxStatus.TERMINATED
        sandbox.completed_at = datetime.now(timezone.utc).isoformat()
        self._save_sandbox(sandbox)
        self.telemetry["sandboxes_terminated"] += 1
        logger.info("Terminated sandbox %s", sandbox_id)

    def expire_sandboxes(self):
        now = datetime.now(timezone.utc)
        expired_count = 0
        for sandbox in self.sandboxes.values():
            if sandbox.status in (SandboxStatus.TERMINATED, SandboxStatus.COMPLETED, SandboxStatus.EXPIRED):
                continue
            if sandbox.expires_at and datetime.fromisoformat(sandbox.expires_at) < now:
                sandbox.status = SandboxStatus.EXPIRED
                sandbox.completed_at = now.isoformat()
                self._save_sandbox(sandbox)
                expired_count += 1
        if expired_count:
            self.telemetry["sandboxes_expired"] += expired_count
            logger.info("Expired %d sandboxes", expired_count)

    def get_sandbox_stats(self) -> dict:
        total = len(self.sandboxes)
        by_status = defaultdict(int)
        by_env = defaultdict(int)
        by_type = defaultdict(int)
        for s in self.sandboxes.values():
            by_status[s.status.value] += 1
            by_env[s.environment.value] += 1
            by_type[s.test_type.value] += 1
        return {
            "total": total,
            "by_status": dict(by_status),
            "by_environment": dict(by_env),
            "by_test_type": dict(by_type),
            "telemetry": dict(self.telemetry),
        }


class SandboxExecutor:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/sandbox")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.tests: dict[str, SandboxTest] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_tests_path(self) -> Path:
        return self.storage_dir / "sandbox_tests.json"

    def _save(self):
        path = self._get_tests_path()
        try:
            data = {k: v.to_dict() for k, v in self.tests.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save sandbox tests: %s", e)

    def _load(self):
        try:
            path = self._get_tests_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.tests = {k: SandboxTest.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load sandbox tests: %s", e)

    def run_test(self, sandbox_id: str, name: str, test_type: TestType,
                 input_data: dict, expected_output: str = "",
                 test_fn: Optional[callable] = None) -> SandboxTest:
        test = SandboxTest(
            sandbox_id=sandbox_id,
            name=name,
            test_type=test_type,
            input=input_data,
            expected_output=expected_output,
        )
        if test_fn:
            try:
                start = time.time()
                result = test_fn(input_data)
                latency = (time.time() - start) * 1000
                test.actual_output = str(result)
                test.latency_ms = latency
                if expected_output:
                    test.passed = test.actual_output.strip() == expected_output.strip()
                else:
                    test.passed = True
                test.score = 1.0 if test.passed else 0.0
                test.logs.append(f"Test completed in {latency:.2f}ms")
                self.telemetry["tests_passed" if test.passed else "tests_failed"] += 1
            except Exception as e:
                test.passed = False
                test.score = 0.0
                test.errors.append(str(e))
                test.logs.append(f"Test failed: {e}")
                self.telemetry["tests_errored"] += 1
                logger.error("Test %s failed: %s", name, e)
        self.tests[test.id] = test
        self._save()
        self.telemetry["tests_run"] += 1
        return test

    def run_all_tests(self, sandbox_id: str, tests: list[dict],
                      test_fn: Optional[callable] = None) -> list[SandboxTest]:
        results = []
        for t in tests:
            test = self.run_test(
                sandbox_id=sandbox_id,
                name=t.get("name", "unnamed"),
                test_type=TestType(t.get("test_type", "prompt")),
                input_data=t.get("input", {}),
                expected_output=t.get("expected_output", ""),
                test_fn=test_fn,
            )
            results.append(test)
        return results

    def get_test(self, test_id: str) -> Optional[SandboxTest]:
        return self.tests.get(test_id)

    def get_test_results(self, sandbox_id: str) -> list[SandboxTest]:
        return [t for t in self.tests.values() if t.sandbox_id == sandbox_id]

    def compare_tests(self, test_ids: list[str]) -> list[dict]:
        comparisons = []
        for tid in test_ids:
            test = self.tests.get(tid)
            if test:
                comparisons.append({
                    "id": test.id,
                    "name": test.name,
                    "passed": test.passed,
                    "score": test.score,
                    "latency_ms": test.latency_ms,
                    "cost": test.cost,
                    "errors": test.errors,
                })
        return comparisons

    def run_parallel_tests(self, sandbox_id: str, tests: list[dict],
                           test_fn: Optional[callable] = None,
                           max_workers: int = 4) -> list[SandboxTest]:
        results = []
        batch = []
        for t in tests:
            batch.append(t)
            if len(batch) >= max_workers:
                for item in batch:
                    results.append(self.run_test(
                        sandbox_id=sandbox_id,
                        name=item.get("name", "unnamed"),
                        test_type=TestType(item.get("test_type", "prompt")),
                        input_data=item.get("input", {}),
                        expected_output=item.get("expected_output", ""),
                        test_fn=test_fn,
                    ))
                batch = []
        for item in batch:
            results.append(self.run_test(
                sandbox_id=sandbox_id,
                name=item.get("name", "unnamed"),
                test_type=TestType(item.get("test_type", "prompt")),
                input_data=item.get("input", {}),
                expected_output=item.get("expected_output", ""),
                test_fn=test_fn,
            ))
        return results


class SandboxTemplates:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/sandbox")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.templates: dict[str, SandboxTemplate] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_templates_path(self) -> Path:
        return self.storage_dir / "sandbox_templates.json"

    def _save(self):
        path = self._get_templates_path()
        try:
            data = {k: v.to_dict() for k, v in self.templates.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save templates: %s", e)

    def _load(self):
        try:
            path = self._get_templates_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.templates = {k: SandboxTemplate.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load templates: %s", e)

    def create_template(self, name: str, test_type: TestType,
                        template_config: Optional[dict] = None,
                        default_inputs: Optional[dict] = None) -> SandboxTemplate:
        template = SandboxTemplate(
            name=name,
            test_type=test_type,
            template_config=template_config or {},
            default_inputs=default_inputs or {},
        )
        self.templates[template.id] = template
        self._save()
        self.telemetry["templates_created"] += 1
        logger.info("Created template %s: %s", template.id, name)
        return template

    def get_template(self, template_id: str) -> Optional[SandboxTemplate]:
        return self.templates.get(template_id)

    def list_templates(self, test_type: Optional[TestType] = None) -> list[SandboxTemplate]:
        if test_type:
            return [t for t in self.templates.values() if t.test_type == test_type]
        return list(self.templates.values())

    def apply_template(self, template_id: str, overrides: Optional[dict] = None) -> dict:
        template = self.templates.get(template_id)
        if not template:
            return {}
        config = dict(template.template_config)
        inputs = dict(template.default_inputs)
        if overrides:
            config.update(overrides.get("config", {}))
            inputs.update(overrides.get("inputs", {}))
        self.telemetry["templates_applied"] += 1
        return {
            "template_id": template.id,
            "name": template.name,
            "test_type": template.test_type.value,
            "config": config,
            "default_inputs": inputs,
        }


class AISandbox(SandboxManager, SandboxExecutor, SandboxTemplates):
    def __init__(self, storage_dir: str = ""):
        SandboxManager.__init__(self, storage_dir)
        SandboxExecutor.__init__(self, storage_dir)
        SandboxTemplates.__init__(self, storage_dir)
        self.reports: dict[str, SandboxReport] = {}
        self.telemetry: dict = defaultdict(int)

    def _get_report_path(self) -> Path:
        return self.storage_dir / "sandbox_reports.json"

    def _save_reports(self):
        path = self._get_report_path()
        try:
            data = {k: v.to_dict() for k, v in self.reports.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save reports: %s", e)

    def _load_reports(self):
        try:
            path = self._get_report_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.reports = {k: SandboxReport.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load reports: %s", e)

    def test_prompt(self, sandbox_id: str, prompt: str,
                    test_fn: Optional[callable] = None) -> SandboxTest:
        return self.run_test(
            sandbox_id=sandbox_id,
            name="prompt_test",
            test_type=TestType.PROMPT,
            input_data={"prompt": prompt},
            test_fn=test_fn,
        )

    def test_model(self, sandbox_id: str, model_config: dict,
                   test_fn: Optional[callable] = None) -> SandboxTest:
        return self.run_test(
            sandbox_id=sandbox_id,
            name="model_test",
            test_type=TestType.MODEL,
            input_data=model_config,
            test_fn=test_fn,
        )

    def test_agent(self, sandbox_id: str, agent_config: dict,
                   test_fn: Optional[callable] = None) -> SandboxTest:
        return self.run_test(
            sandbox_id=sandbox_id,
            name="agent_test",
            test_type=TestType.AGENT,
            input_data=agent_config,
            test_fn=test_fn,
        )

    def test_embedding(self, sandbox_id: str, text: str,
                       test_fn: Optional[callable] = None) -> SandboxTest:
        return self.run_test(
            sandbox_id=sandbox_id,
            name="embedding_test",
            test_type=TestType.EMBEDDING,
            input_data={"text": text},
            test_fn=test_fn,
        )

    def test_retrieval(self, sandbox_id: str, query: str,
                       test_fn: Optional[callable] = None) -> SandboxTest:
        return self.run_test(
            sandbox_id=sandbox_id,
            name="retrieval_test",
            test_type=TestType.RETRIEVAL_PIPELINE,
            input_data={"query": query},
            test_fn=test_fn,
        )

    def generate_report(self, sandbox_id: str) -> SandboxReport:
        sandbox = self.get_sandbox(sandbox_id)
        if not sandbox:
            report = SandboxReport(sandbox_id=sandbox_id, summary="Sandbox not found")
            self.reports[report.id] = report
            self._save_reports()
            return report

        tests = self.get_test_results(sandbox_id)
        test_count = len(tests)
        passed = sum(1 for t in tests if t.passed)
        failed = test_count - passed
        avg_score = sum(t.score for t in tests) / test_count if test_count else 0.0
        total_cost = sum(t.cost for t in tests)

        recommendations = []
        if failed > 0:
            recommendations.append(f"Review {failed} failing test(s)")
        if avg_score < 0.7:
            recommendations.append("Improve overall test quality")
        if any(t.latency_ms > 5000 for t in tests):
            recommendations.append("Optimize high-latency tests")

        summary = f"{test_count} tests run, {passed} passed, {failed} failed, avg score {avg_score:.2f}"
        report = SandboxReport(
            sandbox_id=sandbox_id,
            summary=summary,
            test_count=test_count,
            passed=passed,
            failed=failed,
            avg_score=round(avg_score, 4),
            total_cost=total_cost,
            recommendations=recommendations,
        )
        self.reports[report.id] = report
        self._save_reports()
        self.telemetry["reports_generated"] += 1
        return report
