import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, math
from collections import defaultdict
from pathlib import Path

logger = logging.getLogger(__name__)


class ReleaseStrategy(Enum):
    CANARY = "canary"
    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    ALL_AT_ONCE = "all_at_once"
    STAGED_ROLLOUT = "staged_rollout"


class ReleaseStatus(Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReleaseGate(Enum):
    EVALUATION = "evaluation"
    BENCHMARK = "benchmark"
    SECURITY_REVIEW = "security_review"
    LATENCY_REPORT = "latency_report"
    COST_ANALYSIS = "cost_analysis"
    DOCUMENTATION = "documentation"
    ROLLBACK_PLAN = "rollback_plan"


@dataclass
class AIRelease:
    id: str = ""
    name: str = ""
    version: str = ""
    release_type: str = ""
    strategy: ReleaseStrategy = ReleaseStrategy.ALL_AT_ONCE
    status: ReleaseStatus = ReleaseStatus.DRAFT
    artifact_type: str = ""
    artifact_id: str = ""
    org_id: str = ""
    config: dict = field(default_factory=dict)
    gates: list[ReleaseGate] = field(default_factory=list)
    gate_results: dict = field(default_factory=dict)
    created_at: str = ""
    deployed_at: str = ""
    rolled_back_at: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        d["status"] = self.status.value
        d["gates"] = [g.value for g in self.gates]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AIRelease":
        if "strategy" in data:
            data["strategy"] = ReleaseStrategy(data["strategy"])
        if "status" in data:
            data["status"] = ReleaseStatus(data["status"])
        if "gates" in data:
            data["gates"] = [ReleaseGate(g) for g in data["gates"]]
        return cls(**data)


@dataclass
class CanaryConfig:
    id: str = ""
    release_id: str = ""
    initial_percentage: float = 5.0
    increment: float = 10.0
    interval_minutes: int = 10
    max_percentage: float = 100.0
    success_threshold: float = 0.95
    metrics: list[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CanaryConfig":
        return cls(**data)


@dataclass
class BlueGreenConfig:
    id: str = ""
    release_id: str = ""
    blue_version: str = ""
    green_version: str = ""
    active: str = "blue"
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "BlueGreenConfig":
        return cls(**data)


@dataclass
class FeatureFlag:
    id: str = ""
    name: str = ""
    org_id: str = ""
    enabled: bool = False
    rules: dict = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not self.created_at:
            self.created_at = now
        if not self.updated_at:
            self.updated_at = now

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "FeatureFlag":
        return cls(**data)


@dataclass
class ReleaseGateCheck:
    id: str = ""
    release_id: str = ""
    gate: ReleaseGate = ReleaseGate.EVALUATION
    passed: bool = False
    score: float = 0.0
    details: dict = field(default_factory=dict)
    checked_at: str = ""
    checked_by: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())
        if not self.checked_at:
            self.checked_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["gate"] = self.gate.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ReleaseGateCheck":
        if "gate" in data:
            data["gate"] = ReleaseGate(data["gate"])
        return cls(**data)


class ReleaseOrchestrator:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/releases")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.releases: dict[str, AIRelease] = {}
        self.gate_checks: dict[str, ReleaseGateCheck] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_release_path(self, release_id: str) -> Path:
        return self.storage_dir / f"release_{release_id}.json"

    def _get_gate_checks_path(self) -> Path:
        return self.storage_dir / "gate_checks.json"

    def _save_release(self, release: AIRelease):
        path = self._get_release_path(release.id)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(release.to_dict(), f, indent=2)
            self.telemetry["releases_saved"] += 1
        except Exception as e:
            logger.error("Failed to save release %s: %s", release.id, e)

    def _save_gate_checks(self):
        path = self._get_gate_checks_path()
        try:
            data = {k: v.to_dict() for k, v in self.gate_checks.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save gate checks: %s", e)

    def _load(self):
        if not self.storage_dir.exists():
            return
        try:
            for path in self.storage_dir.glob("release_*.json"):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    release = AIRelease.from_dict(data)
                    self.releases[release.id] = release
                except Exception as e:
                    logger.warning("Failed to load release from %s: %s", path, e)
        except Exception as e:
            logger.error("Failed to load releases: %s", e)
        try:
            path = self._get_gate_checks_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.gate_checks = {k: ReleaseGateCheck.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load gate checks: %s", e)

    def create_release(self, name: str, version: str, release_type: str,
                       strategy: ReleaseStrategy, artifact_type: str,
                       artifact_id: str, org_id: str,
                       config: Optional[dict] = None,
                       gates: Optional[list[ReleaseGate]] = None) -> AIRelease:
        release = AIRelease(
            name=name,
            version=version,
            release_type=release_type,
            strategy=strategy,
            artifact_type=artifact_type,
            artifact_id=artifact_id,
            org_id=org_id,
            config=config or {},
            gates=gates or [],
        )
        self.releases[release.id] = release
        self._save_release(release)
        self.telemetry["releases_created"] += 1
        logger.info("Created release %s: %s v%s", release.id, name, version)
        return release

    def get_release(self, release_id: str) -> Optional[AIRelease]:
        return self.releases.get(release_id)

    def list_releases(self, org_id: Optional[str] = None,
                      status: Optional[ReleaseStatus] = None) -> list[AIRelease]:
        results = list(self.releases.values())
        if org_id:
            results = [r for r in results if r.org_id == org_id]
        if status:
            results = [r for r in results if r.status == status]
        return sorted(results, key=lambda r: r.created_at, reverse=True)

    def deploy(self, release_id: str) -> bool:
        release = self.releases.get(release_id)
        if not release:
            logger.error("Release %s not found", release_id)
            return False
        if release.status in (ReleaseStatus.DEPLOYED, ReleaseStatus.DEPLOYING):
            logger.warning("Release %s already deployed or deploying", release_id)
            return False
        release.status = ReleaseStatus.DEPLOYING
        release.deployed_at = datetime.now(timezone.utc).isoformat()
        release.status = ReleaseStatus.DEPLOYED
        self._save_release(release)
        self.telemetry["releases_deployed"] += 1
        logger.info("Deployed release %s v%s", release.name, release.version)
        return True

    def rollback(self, release_id: str) -> bool:
        release = self.releases.get(release_id)
        if not release:
            logger.error("Release %s not found", release_id)
            return False
        if release.status != ReleaseStatus.DEPLOYED:
            logger.warning("Release %s is not deployed, cannot rollback", release_id)
            return False
        release.status = ReleaseStatus.ROLLING_BACK
        release.rolled_back_at = datetime.now(timezone.utc).isoformat()
        release.status = ReleaseStatus.ROLLED_BACK
        self._save_release(release)
        self.telemetry["releases_rolled_back"] += 1
        logger.info("Rolled back release %s v%s", release.name, release.version)
        return True

    def get_release_status(self, release_id: str) -> Optional[dict]:
        release = self.releases.get(release_id)
        if not release:
            return None
        return {
            "id": release.id,
            "name": release.name,
            "version": release.version,
            "status": release.status.value,
            "strategy": release.strategy.value,
            "deployed_at": release.deployed_at,
            "rolled_back_at": release.rolled_back_at,
        }

    def get_release_history(self, org_id: Optional[str] = None) -> list[dict]:
        releases = self.list_releases(org_id=org_id)
        return [
            {
                "id": r.id,
                "name": r.name,
                "version": r.version,
                "status": r.status.value,
                "strategy": r.strategy.value,
                "deployed_at": r.deployed_at,
                "rolled_back_at": r.rolled_back_at,
                "created_at": r.created_at,
            }
            for r in releases
        ]


class CanaryManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/releases")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.canaries: dict[str, CanaryConfig] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_canary_path(self) -> Path:
        return self.storage_dir / "canary_configs.json"

    def _save(self):
        path = self._get_canary_path()
        try:
            data = {k: v.to_dict() for k, v in self.canaries.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save canary configs: %s", e)

    def _load(self):
        try:
            path = self._get_canary_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.canaries = {k: CanaryConfig.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load canary configs: %s", e)

    def create_canary(self, release_id: str, initial_percentage: float = 5.0,
                      increment: float = 10.0, interval_minutes: int = 10,
                      max_percentage: float = 100.0,
                      success_threshold: float = 0.95) -> CanaryConfig:
        canary = CanaryConfig(
            release_id=release_id,
            initial_percentage=initial_percentage,
            increment=increment,
            interval_minutes=interval_minutes,
            max_percentage=max_percentage,
            success_threshold=success_threshold,
        )
        self.canaries[canary.id] = canary
        self._save()
        self.telemetry["canaries_created"] += 1
        logger.info("Created canary for release %s at %.1f%%", release_id, initial_percentage)
        return canary

    def promote(self, canary_id: str) -> Optional[float]:
        canary = self.canaries.get(canary_id)
        if not canary:
            return None
        current = self.calculate_progression(canary_id)
        new_percentage = min(current + canary.increment, canary.max_percentage)
        self.telemetry["canary_promotions"] += 1
        logger.info("Canary %s promoted to %.1f%%", canary_id, new_percentage)
        return new_percentage

    def rollback(self, canary_id: str):
        canary = self.canaries.get(canary_id)
        if not canary:
            return
        self.telemetry["canary_rollbacks"] += 1
        logger.info("Canary %s rolled back", canary_id)

    def get_canary_status(self, canary_id: str) -> Optional[dict]:
        canary = self.canaries.get(canary_id)
        if not canary:
            return None
        return {
            "id": canary.id,
            "release_id": canary.release_id,
            "current_percentage": self.calculate_progression(canary_id),
            "max_percentage": canary.max_percentage,
            "interval_minutes": canary.interval_minutes,
            "success_threshold": canary.success_threshold,
        }

    def calculate_progression(self, canary_id: str) -> float:
        canary = self.canaries.get(canary_id)
        if not canary:
            return 0.0
        return canary.initial_percentage

    def check_metrics(self, canary_id: str, metrics: dict) -> bool:
        canary = self.canaries.get(canary_id)
        if not canary:
            return False
        if not canary.metrics:
            return True
        for metric in canary.metrics:
            if metric in metrics:
                value = metrics[metric]
                if value < canary.success_threshold:
                    return False
        return True


class BlueGreenManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/releases")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.configs: dict[str, BlueGreenConfig] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_config_path(self) -> Path:
        return self.storage_dir / "blue_green_configs.json"

    def _save(self):
        path = self._get_config_path()
        try:
            data = {k: v.to_dict() for k, v in self.configs.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save blue/green configs: %s", e)

    def _load(self):
        try:
            path = self._get_config_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.configs = {k: BlueGreenConfig.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load blue/green configs: %s", e)

    def switch(self, config_id: str) -> Optional[str]:
        config = self.configs.get(config_id)
        if not config:
            return None
        new_active = "green" if config.active == "blue" else "blue"
        config.active = new_active
        self._save()
        self.telemetry["blue_green_switches"] += 1
        logger.info("Blue/Green switched to %s for release %s", new_active, config.release_id)
        return new_active

    def rollback(self, config_id: str) -> Optional[str]:
        config = self.configs.get(config_id)
        if not config:
            return None
        original = "blue" if config.active == "green" else "green"
        config.active = original
        self._save()
        self.telemetry["blue_green_rollbacks"] += 1
        logger.info("Blue/Green rolled back to %s for release %s", original, config.release_id)
        return original

    def get_active_version(self, config_id: str) -> Optional[str]:
        config = self.configs.get(config_id)
        if not config:
            return None
        return config.green_version if config.active == "green" else config.blue_version

    def get_standby_version(self, config_id: str) -> Optional[str]:
        config = self.configs.get(config_id)
        if not config:
            return None
        return config.blue_version if config.active == "green" else config.green_version

    def compare_versions(self, config_id: str) -> Optional[dict]:
        config = self.configs.get(config_id)
        if not config:
            return None
        return {
            "blue": config.blue_version,
            "green": config.green_version,
            "active": config.active,
            "standby": "green" if config.active == "blue" else "blue",
        }


class FeatureFlagManager:
    def __init__(self, storage_dir: str = ""):
        self.storage_dir = Path(storage_dir) if storage_dir else Path("data/releases")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.flags: dict[str, FeatureFlag] = {}
        self.telemetry: dict = defaultdict(int)
        self._load()

    def _get_flag_path(self) -> Path:
        return self.storage_dir / "feature_flags.json"

    def _save(self):
        path = self._get_flag_path()
        try:
            data = {k: v.to_dict() for k, v in self.flags.items()}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error("Failed to save feature flags: %s", e)

    def _load(self):
        try:
            path = self._get_flag_path()
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.flags = {k: FeatureFlag.from_dict(v) for k, v in data.items()}
        except Exception as e:
            logger.warning("Failed to load feature flags: %s", e)

    def create_flag(self, name: str, org_id: str, enabled: bool = False,
                    rules: Optional[dict] = None) -> FeatureFlag:
        flag = FeatureFlag(
            name=name,
            org_id=org_id,
            enabled=enabled,
            rules=rules or {},
        )
        self.flags[flag.id] = flag
        self._save()
        self.telemetry["flags_created"] += 1
        logger.info("Created feature flag %s: %s", flag.id, name)
        return flag

    def get_flag(self, flag_id: str) -> Optional[FeatureFlag]:
        return self.flags.get(flag_id)

    def update_flag(self, flag_id: str, name: Optional[str] = None,
                    rules: Optional[dict] = None) -> Optional[FeatureFlag]:
        flag = self.flags.get(flag_id)
        if not flag:
            return None
        if name is not None:
            flag.name = name
        if rules is not None:
            flag.rules = rules
        flag.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self.telemetry["flags_updated"] += 1
        return flag

    def enable(self, flag_id: str) -> Optional[FeatureFlag]:
        flag = self.flags.get(flag_id)
        if not flag:
            return None
        flag.enabled = True
        flag.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self.telemetry["flags_enabled"] += 1
        return flag

    def disable(self, flag_id: str) -> Optional[FeatureFlag]:
        flag = self.flags.get(flag_id)
        if not flag:
            return None
        flag.enabled = False
        flag.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        self.telemetry["flags_disabled"] += 1
        return flag

    def list_flags(self, org_id: Optional[str] = None) -> list[FeatureFlag]:
        if org_id:
            return [f for f in self.flags.values() if f.org_id == org_id]
        return list(self.flags.values())

    def evaluate_flag(self, flag_id: str, context: Optional[dict] = None) -> bool:
        flag = self.flags.get(flag_id)
        if not flag:
            return False
        if not flag.enabled:
            return False
        if not flag.rules or not context:
            return flag.enabled
        for key, condition in flag.rules.items():
            if key in context:
                value = context[key]
                if isinstance(condition, dict):
                    for op, target in condition.items():
                        if op == "eq" and value != target:
                            return False
                        elif op == "neq" and value == target:
                            return False
                        elif op == "in" and value not in target:
                            return False
                elif value != condition:
                    return False
        return True


class AIModelReleaseManager(ReleaseOrchestrator, CanaryManager, BlueGreenManager):
    def __init__(self, storage_dir: str = ""):
        ReleaseOrchestrator.__init__(self, storage_dir)
        CanaryManager.__init__(self, storage_dir)
        BlueGreenManager.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)

    def manage_rollout(self, release_id: str, strategy: ReleaseStrategy) -> bool:
        release = self.get_release(release_id)
        if not release:
            logger.error("Release %s not found", release_id)
            return False

        if strategy == ReleaseStrategy.CANARY:
            canary = self.create_canary(release_id)
            self.telemetry["rollouts_canary"] += 1
            logger.info("Canary rollout for release %s at %.1f%%", release_id, canary.initial_percentage)
        elif strategy == ReleaseStrategy.BLUE_GREEN:
            config = BlueGreenConfig(
                release_id=release_id,
                blue_version=release.version,
                green_version="",
                active="blue",
            )
            self.configs[config.id] = config
            self._save()
            self.telemetry["rollouts_blue_green"] += 1
            logger.info("Blue/Green rollout for release %s", release_id)
        else:
            self.telemetry["rollouts_direct"] += 1
            logger.info("Direct rollout for release %s", release_id)

        return self.deploy(release_id)

    def get_active_deployments(self, org_id: Optional[str] = None) -> list[dict]:
        active = []
        for release in self.releases.values():
            if release.status == ReleaseStatus.DEPLOYED:
                if org_id and release.org_id != org_id:
                    continue
                entry = {
                    "id": release.id,
                    "name": release.name,
                    "version": release.version,
                    "strategy": release.strategy.value,
                    "deployed_at": release.deployed_at,
                }
                if release.strategy == ReleaseStrategy.BLUE_GREEN:
                    for config in self.configs.values():
                        if config.release_id == release.id:
                            entry["active_version"] = self.get_active_version(config.id)
                            entry["standby_version"] = self.get_standby_version(config.id)
                            break
                active.append(entry)
        return active

    def get_release_dashboard(self, org_id: Optional[str] = None) -> dict:
        releases = self.list_releases(org_id=org_id)
        total = len(releases)
        by_status = defaultdict(int)
        by_strategy = defaultdict(int)
        for r in releases:
            by_status[r.status.value] += 1
            by_strategy[r.strategy.value] += 1
        return {
            "total_releases": total,
            "by_status": dict(by_status),
            "by_strategy": dict(by_strategy),
            "active_deployments": self.get_active_deployments(org_id),
            "telemetry": dict(self.telemetry),
        }
