"""Autonomous Learning — continuously learn repository patterns, architecture patterns, coding standards, review standards, developer preferences, organization rules, engineering decisions, historical knowledge."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class LearningDomain(Enum):
    REPO_PATTERNS = "repo_patterns"
    ARCHITECTURE_PATTERNS = "architecture_patterns"
    CODING_STANDARDS = "coding_standards"
    REVIEW_STANDARDS = "review_standards"
    DEVELOPER_PREFERENCES = "developer_preferences"
    ORGANIZATION_RULES = "organization_rules"
    ENGINEERING_DECISIONS = "engineering_decisions"
    HISTORICAL_KNOWLEDGE = "historical_knowledge"


class LearningSource(Enum):
    CODE_ANALYSIS = "code_analysis"
    COMMIT_HISTORY = "commit_history"
    CODE_REVIEW = "code_review"
    USER_FEEDBACK = "user_feedback"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    BENCHMARK = "benchmark"
    EXPERIMENT = "experiment"


@dataclass
class LearnedPattern:
    id: str
    domain: LearningDomain
    pattern: str
    confidence: float = 0.0
    source: LearningSource = LearningSource.CODE_ANALYSIS
    evidence: list = field(default_factory=list)
    examples: list = field(default_factory=list)
    tags: list = field(default_factory=list)
    derived_from: str = ""
    active: bool = True
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        d["source"] = self.source.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LearnedPattern":
        data = data.copy()
        data["domain"] = LearningDomain(data.get("domain", "repo_patterns"))
        data["source"] = LearningSource(data.get("source", "code_analysis"))
        return cls(**data)


@dataclass
class LearningSession:
    id: str
    org_id: str
    domain: LearningDomain
    sources_analyzed: int = 0
    patterns_found: int = 0
    new_patterns: int = 0
    duration_ms: float = 0.0
    status: str = "completed"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["domain"] = self.domain.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "LearningSession":
        data = data.copy()
        data["domain"] = LearningDomain(data.get("domain", "repo_patterns"))
        return cls(**data)


class AutonomousLearning:
    def __init__(self, storage_dir: str = "research_data/learning"):
        self.storage_dir = storage_dir
        self._patterns: dict[str, LearnedPattern] = {}
        self._sessions: dict[str, LearningSession] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _patterns_path(self) -> str: return os.path.join(self.storage_dir, "patterns.json")
    def _sessions_path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        for path, store, cls in [
            (self._patterns_path(), self._patterns, LearnedPattern),
            (self._sessions_path(), self._sessions, LearningSession),
        ]:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for k, v in data.items():
                        try: store[k] = cls.from_dict(v)
                        except Exception as e: logger.warning("Skipping %s: %s", k, e)
                except Exception as e: logger.error("Failed to load learning data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._patterns_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._patterns.items()}, f, indent=2, default=str)
            with open(self._sessions_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save learning data: %s", e)

    def learn_pattern(self, domain: LearningDomain, pattern: str, confidence: float, source: LearningSource = LearningSource.CODE_ANALYSIS, evidence: list = None, examples: list = None, tags: list = None) -> LearnedPattern:
        lp = LearnedPattern(
            id=str(uuid.uuid4()), domain=domain, pattern=pattern, confidence=confidence,
            source=source, evidence=evidence or [], examples=examples or [], tags=tags or [],
        )
        self._patterns[lp.id] = lp
        self._save()
        return lp

    def get_pattern(self, pattern_id: str) -> Optional[LearnedPattern]: return self._patterns.get(pattern_id)

    def update_pattern(self, pattern_id: str, updates: dict) -> Optional[LearnedPattern]:
        pattern = self._patterns.get(pattern_id)
        if not pattern: return None
        for k, v in updates.items():
            if hasattr(pattern, k) and k not in ("id", "created_at"):
                if k == "domain": setattr(pattern, k, LearningDomain(v) if isinstance(v, str) else v)
                elif k == "source": setattr(pattern, k, LearningSource(v) if isinstance(v, str) else v)
                else: setattr(pattern, k, v)
        pattern.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return pattern

    def search_patterns(self, query: str, domain: Optional[LearningDomain] = None) -> list[LearnedPattern]:
        q = query.lower()
        results = []
        for p in self._patterns.values():
            if domain and p.domain != domain: continue
            if q in p.pattern.lower() or any(q in t.lower() for t in p.tags):
                results.append(p)
        return sorted(results, key=lambda p: p.confidence, reverse=True)

    def record_session(self, org_id: str, domain: LearningDomain, sources_analyzed: int, patterns_found: int, new_patterns: int, duration_ms: float) -> LearningSession:
        session = LearningSession(id=str(uuid.uuid4()), org_id=org_id, domain=domain, sources_analyzed=sources_analyzed, patterns_found=patterns_found, new_patterns=new_patterns, duration_ms=duration_ms)
        self._sessions[session.id] = session
        self._save()
        return session

    def get_knowledge_base(self, domain: Optional[LearningDomain] = None) -> dict:
        patterns = [p for p in self._patterns.values() if p.active]
        if domain: patterns = [p for p in patterns if p.domain == domain]
        return {
            "total_patterns": len(patterns),
            "by_domain": {d.value: len([p for p in patterns if p.domain == d]) for d in LearningDomain},
            "avg_confidence": round(sum(p.confidence for p in patterns) / len(patterns), 4) if patterns else 0.0,
            "patterns": [{"id": p.id, "domain": p.domain.value, "pattern": p.pattern[:100], "confidence": p.confidence} for p in patterns[:50]],
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
