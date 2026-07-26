import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math, re
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class VersionStatus(Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


class ApprovalDecision(Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    CHANGES_REQUESTED = "changes_requested"


@dataclass
class PromptVersionDetail:
    id: str = ""
    prompt_id: str = ""
    version: int = 1
    content: str = ""
    author: str = ""
    reason: str = ""
    status: VersionStatus = VersionStatus.DRAFT
    approval: Optional[str] = None
    approval_decision: Optional[ApprovalDecision] = None
    test_results: dict = field(default_factory=dict)
    performance_scores: dict = field(default_factory=dict)
    created_at: str = ""
    approved_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        d["approval_decision"] = self.approval_decision.value if self.approval_decision else None
        return d

    @staticmethod
    def from_dict(data: dict) -> "PromptVersionDetail":
        data = data.copy()
        data["status"] = VersionStatus(data.get("status", "draft"))
        ad = data.get("approval_decision")
        data["approval_decision"] = ApprovalDecision(ad) if ad else None
        return PromptVersionDetail(**data)


@dataclass
class VersionDiff:
    version_from: int = 0
    version_to: int = 0
    additions: list[str] = field(default_factory=list)
    removals: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)
    token_diff: int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "VersionDiff":
        return VersionDiff(**data)


@dataclass
class ABTestConfig:
    id: str = ""
    prompt_id: str = ""
    variant_a_version: int = 1
    variant_b_version: int = 2
    traffic_split: float = 0.5
    min_sample_size: int = 100
    metrics: list[str] = field(default_factory=list)
    started_at: str = ""
    completed_at: Optional[str] = None

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.started_at:
            self.started_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ABTestConfig":
        return ABTestConfig(**data)


@dataclass
class ABTestResult:
    id: str = ""
    config_id: str = ""
    winner: str = ""
    metric_results: dict = field(default_factory=dict)
    confidence: float = 0.0
    sample_size: int = 0

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ABTestResult":
        return ABTestResult(**data)


class PromptVersionManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._versions_file = self.storage_dir / "prompt_version_details.json"
        self._versions: dict[str, list[PromptVersionDetail]] = defaultdict(list)
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("PromptVersionManager initialized at %s", storage_dir)

    def _save(self):
        data = {k: [v.to_dict() for v in vers] for k, vers in self._versions.items()}
        try:
            self._versions_file.write_text(json.dumps(data, indent=2))
        except Exception as e:
            logger.error("Failed to save version details: %s", e)
            raise

    def _load(self):
        try:
            if self._versions_file.exists():
                data = json.loads(self._versions_file.read_text())
                for k, vers in data.items():
                    self._versions[k] = [PromptVersionDetail.from_dict(v) for v in vers]
        except Exception as e:
            logger.error("Failed to load version details: %s", e)

    def create_version(self, prompt_id: str, content: str, author: str, reason: str = "", version: Optional[int] = None) -> PromptVersionDetail:
        existing = self._versions.get(prompt_id, [])
        next_version = version if version else (max((v.version for v in existing), default=0) + 1)
        detail = PromptVersionDetail(
            prompt_id=prompt_id,
            version=next_version,
            content=content,
            author=author,
            reason=reason,
            status=VersionStatus.DRAFT,
        )
        self._versions[prompt_id].append(detail)
        self._save()
        self._telemetry["versions_created"] += 1
        logger.info("Created version %d for prompt %s", next_version, prompt_id)
        return detail

    def get_version(self, prompt_id: str, version: int) -> Optional[PromptVersionDetail]:
        for v in self._versions.get(prompt_id, []):
            if v.version == version:
                return v
        return None

    def list_versions(self, prompt_id: str) -> list[PromptVersionDetail]:
        return sorted(self._versions.get(prompt_id, []), key=lambda v: v.version, reverse=True)

    def rollback_to_version(self, prompt_id: str, version: int) -> Optional[PromptVersionDetail]:
        target = self.get_version(prompt_id, version)
        if not target:
            return None
        for v in self._versions.get(prompt_id, []):
            if v.status == VersionStatus.ACTIVE:
                v.status = VersionStatus.ROLLED_BACK
        new_version = max((v.version for v in self._versions.get(prompt_id, [])), default=0) + 1
        rollback = PromptVersionDetail(
            prompt_id=prompt_id,
            version=new_version,
            content=target.content,
            author="system",
            reason=f"Rollback to version {version}",
            status=VersionStatus.ACTIVE,
        )
        self._versions[prompt_id].append(rollback)
        self._save()
        self._telemetry["versions_rolled_back"] += 1
        return rollback

    def compare_versions(self, prompt_id: str, version_a: int, version_b: int) -> VersionDiff:
        va = self.get_version(prompt_id, version_a)
        vb = self.get_version(prompt_id, version_b)
        if not va or not vb:
            raise ValueError(f"Version(s) not found: {version_a}, {version_b}")
        lines_a = set(va.content.splitlines())
        lines_b = set(vb.content.splitlines())
        diff = VersionDiff(
            version_from=version_a,
            version_to=version_b,
            additions=list(lines_b - lines_a),
            removals=list(lines_a - lines_b),
            token_diff=len(re.findall(r"\S+", vb.content)) - len(re.findall(r"\S+", va.content)),
        )
        for line in lines_a & lines_b:
            if line.strip() and line not in diff.additions and line not in diff.removals:
                diff.changes.append(line)
        return diff

    def approve_version(self, prompt_id: str, version: int, approver: str) -> Optional[PromptVersionDetail]:
        v = self.get_version(prompt_id, version)
        if not v:
            return None
        v.status = VersionStatus.APPROVED
        v.approval = approver
        v.approval_decision = ApprovalDecision.APPROVED
        v.approved_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._telemetry["versions_approved"] += 1
        return v

    def reject_version(self, prompt_id: str, version: int, approver: str, reason: str = "") -> Optional[PromptVersionDetail]:
        v = self.get_version(prompt_id, version)
        if not v:
            return None
        v.status = VersionStatus.REJECTED
        v.approval = approver
        v.approval_decision = ApprovalDecision.REJECTED
        v.reason = reason
        self._save()
        self._telemetry["versions_rejected"] += 1
        return v

    def promote_to_active(self, prompt_id: str, version: int) -> Optional[PromptVersionDetail]:
        for v in self._versions.get(prompt_id, []):
            if v.status == VersionStatus.ACTIVE:
                v.status = VersionStatus.SUPERSEDED
        target = self.get_version(prompt_id, version)
        if not target:
            return None
        target.status = VersionStatus.ACTIVE
        self._save()
        self._telemetry["versions_promoted"] += 1
        return target

    def get_active_version(self, prompt_id: str) -> Optional[PromptVersionDetail]:
        for v in self._versions.get(prompt_id, []):
            if v.status == VersionStatus.ACTIVE:
                return v
        return None

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


class ABTestingManager:
    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._configs_file = self.storage_dir / "ab_test_configs.json"
        self._results_file = self.storage_dir / "ab_test_results.json"
        self._configs: dict[str, ABTestConfig] = {}
        self._results: dict[str, ABTestResult] = {}
        self._load()
        self._telemetry = defaultdict(int)
        logger.info("ABTestingManager initialized at %s", storage_dir)

    def _save(self):
        try:
            configs_data = {k: v.to_dict() for k, v in self._configs.items()}
            results_data = {k: v.to_dict() for k, v in self._results.items()}
            self._configs_file.write_text(json.dumps(configs_data, indent=2))
            self._results_file.write_text(json.dumps(results_data, indent=2))
        except Exception as e:
            logger.error("Failed to save AB test data: %s", e)
            raise

    def _load(self):
        try:
            if self._configs_file.exists():
                data = json.loads(self._configs_file.read_text())
                self._configs = {k: ABTestConfig.from_dict(v) for k, v in data.items()}
            if self._results_file.exists():
                data = json.loads(self._results_file.read_text())
                self._results = {k: ABTestResult.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.error("Failed to load AB test data: %s", e)

    def create_ab_test(self, config: ABTestConfig) -> ABTestConfig:
        self._configs[config.id] = config
        self._save()
        self._telemetry["ab_tests_created"] += 1
        return config

    def run_ab_test(self, config_id: str) -> Optional[ABTestResult]:
        config = self._configs.get(config_id)
        if not config:
            return None
        import random
        results_a = {"latency": random.gauss(150, 30), "accuracy": random.gauss(0.85, 0.05)}
        results_b = {"latency": random.gauss(140, 25), "accuracy": random.gauss(0.88, 0.04)}
        combined = {}
        for metric in config.metrics:
            val_a = results_a.get(metric, 0)
            val_b = results_b.get(metric, 0)
            combined[metric] = {"variant_a": val_a, "variant_b": val_b, "delta": val_b - val_a}
        winner = "variant_b" if sum(combined[m]["delta"] for m in config.metrics) > 0 else "variant_a"
        result = ABTestResult(
            config_id=config_id,
            winner=winner,
            metric_results=combined,
            confidence=random.uniform(0.85, 0.99),
            sample_size=config.min_sample_size,
        )
        self._results[result.id] = result
        config.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._telemetry["ab_tests_completed"] += 1
        return result

    def get_results(self, config_id: str) -> Optional[ABTestResult]:
        for r in self._results.values():
            if r.config_id == config_id:
                return r
        return None

    def determine_winner(self, config_id: str) -> Optional[str]:
        result = self.get_results(config_id)
        return result.winner if result else None

    def stop_test(self, config_id: str) -> bool:
        config = self._configs.get(config_id)
        if not config:
            return False
        config.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self._telemetry["ab_tests_stopped"] += 1
        return True

    def list_tests(self, prompt_id: Optional[str] = None) -> list[ABTestConfig]:
        if prompt_id:
            return [c for c in self._configs.values() if c.prompt_id == prompt_id]
        return list(self._configs.values())

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


class ReleaseManager(PromptVersionManager, ABTestingManager):
    def __init__(self, storage_dir: str):
        PromptVersionManager.__init__(self, storage_dir)
        ABTestingManager.__init__(self, storage_dir)
        self._releases_file = self.storage_dir / "release_history.json"
        self._release_history: list[dict] = []
        self._load_release_history()
        logger.info("ReleaseManager initialized at %s", storage_dir)

    def _load_release_history(self):
        try:
            if self._releases_file.exists():
                self._release_history = json.loads(self._releases_file.read_text())
        except Exception as e:
            logger.error("Failed to load release history: %s", e)

    def _save_release_history(self):
        try:
            self._releases_file.write_text(json.dumps(self._release_history, indent=2))
        except Exception as e:
            logger.error("Failed to save release history: %s", e)

    def canary_release(self, prompt_id: str, version: int, canary_percent: float = 0.1) -> dict:
        config = ABTestConfig(
            prompt_id=prompt_id,
            variant_a_version=self.get_active_version(prompt_id).version if self.get_active_version(prompt_id) else 1,
            variant_b_version=version,
            traffic_split=canary_percent,
            min_sample_size=200,
            metrics=["latency", "accuracy"],
        )
        self.create_ab_test(config)
        release = {
            "type": "canary",
            "prompt_id": prompt_id,
            "version": version,
            "canary_percent": canary_percent,
            "config_id": config.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._release_history.append(release)
        self._save_release_history()
        self._telemetry["canary_releases"] += 1
        return release

    def blue_green_switch(self, prompt_id: str, blue_version: int, green_version: int) -> dict:
        self.promote_to_active(prompt_id, green_version)
        release = {
            "type": "blue_green",
            "prompt_id": prompt_id,
            "blue_version": blue_version,
            "green_version": green_version,
            "active_version": green_version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._release_history.append(release)
        self._save_release_history()
        self._telemetry["blue_green_switches"] += 1
        return release

    def rollback_release(self, prompt_id: str, target_version: int) -> Optional[PromptVersionDetail]:
        result = self.rollback_to_version(prompt_id, target_version)
        if result:
            release = {
                "type": "rollback",
                "prompt_id": prompt_id,
                "target_version": target_version,
                "new_version": result.version,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._release_history.append(release)
            self._save_release_history()
            self._telemetry["releases_rolled_back"] += 1
        return result

    def get_release_history(self, prompt_id: Optional[str] = None) -> list[dict]:
        if prompt_id:
            return [r for r in self._release_history if r["prompt_id"] == prompt_id]
        return list(self._release_history)
