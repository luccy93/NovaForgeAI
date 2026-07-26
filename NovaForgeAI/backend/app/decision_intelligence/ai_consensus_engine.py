"""AI Consensus Engine — single model, multi-model voting, multi-agent, weighted, human approval."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class ConsensusVote:
    id: str; decision_id: str; voter: str; voter_type: str  # model, agent, human
    vote: str = ""; confidence: float = 0.0; reasoning: str = ""
    weight: float = 1.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "ConsensusVote": return cls(**data)

@dataclass
class ConsensusResult:
    id: str; decision_id: str; consensus_type: str  # single, multi_model, multi_agent, majority, weighted, expert, human
    votes: list = field(default_factory=list); final_decision: str = ""
    agreement_score: float = 0.0; total_votes: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class AIConsensusEngine:
    def __init__(self, storage_dir: str = "decision_data/consensus"):
        self.storage_dir = storage_dir; self._results: dict[str, ConsensusResult] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "results.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._results[k] = ConsensusResult.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._results.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def run_consensus(self, decision_id: str, consensus_type: str = "multi_agent", votes: list = None) -> ConsensusResult:
        result = ConsensusResult(id=str(uuid.uuid4()), decision_id=decision_id, consensus_type=consensus_type, votes=votes or [], total_votes=len(votes or []))
        if votes:
            approved = sum(1 for v in votes if v.get("vote") == "approve" and v.get("weight", 1))
            total_weight = sum(v.get("weight", 1) for v in votes)
            result.agreement_score = approved / total_weight if total_weight > 0 else 0
            result.final_decision = "approved" if result.agreement_score > 0.5 else "rejected"
        self._results[result.id] = result; self._save(); return result

    def get_by_decision(self, decision_id: str) -> Optional[ConsensusResult]:
        for r in self._results.values():
            if r.decision_id == decision_id: return r
        return None

    def get_telemetry(self) -> dict: return {"results": len(self._results)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class DecisionMemoryEntry:
    id: str; org_id: str; decision_id: str; title: str; decision_type: str
    status: str = ""; author_id: str = ""; approver_id: str = ""
    evidence_summary: str = ""; reasoning_summary: str = ""
    outcome: str = ""; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "DecisionMemoryEntry": return cls(**data)

class DecisionMemory:
    def __init__(self, storage_dir: str = "decision_data/memory"):
        self.storage_dir = storage_dir; self._entries: dict[str, DecisionMemoryEntry] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "memory.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._entries[k] = DecisionMemoryEntry.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._entries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def store(self, org_id: str, decision_id: str, title: str, decision_type: str, status: str, author_id: str = "", approver_id: str = "") -> DecisionMemoryEntry:
        e = DecisionMemoryEntry(id=str(uuid.uuid4()), org_id=org_id, decision_id=decision_id, title=title, decision_type=decision_type, status=status, author_id=author_id, approver_id=approver_id)
        self._entries[e.id] = e; self._save(); return e

    def search(self, org_id: str, query: str) -> list[DecisionMemoryEntry]:
        q = query.lower()
        return [e for e in self._entries.values() if e.org_id == org_id and (q in e.title.lower() or q in e.decision_type.lower())]

    def get_by_type(self, org_id: str, decision_type: str) -> list[DecisionMemoryEntry]:
        return [e for e in self._entries.values() if e.org_id == org_id and e.decision_type == decision_type]

    def get_telemetry(self) -> dict: return {"entries": len(self._entries)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class LearningEvent:
    id: str; org_id: str; event_type: str  # developer_feedback, accepted, rejected, repo_evolution, arch_change, deployment_outcome, incident
    source: str = ""; content: str = ""
    feedback_value: float = 0.0; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class LearningEngine:
    def __init__(self, storage_dir: str = "decision_data/learning"):
        self.storage_dir = storage_dir; self._events: dict[str, LearningEvent] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "events.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._events[k] = LearningEvent(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._events.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, event_type: str, content: str, feedback: float = 0.0, source: str = "") -> LearningEvent:
        e = LearningEvent(id=str(uuid.uuid4()), org_id=org_id, event_type=event_type, content=content, feedback_value=feedback, source=source)
        self._events[e.id] = e; self._save(); return e

    def get_insights(self, org_id: str) -> dict:
        evts = [e for e in self._events.values() if e.org_id == org_id]
        return {"total_events": len(evts), "avg_feedback": sum(e.feedback_value for e in evts if e.feedback_value) / max(len([e for e in evts if e.feedback_value]), 1)}

    def get_telemetry(self) -> dict: return {"events": len(self._events)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Explanation:
    id: str; decision_id: str; title: str; why: str = ""; how: str = ""
    evidence: list = field(default_factory=list); alternatives: list = field(default_factory=list)
    tradeoffs: list = field(default_factory=list); risk: str = ""
    expected_result: str = ""; rollback_strategy: str = ""
    confidence: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict: return asdict(self)
    @classmethod
    def from_dict(cls, data: dict) -> "Explanation": return cls(**data)

class ExplainableAI:
    def __init__(self, storage_dir: str = "decision_data/explain"):
        self.storage_dir = storage_dir; self._explanations: dict[str, Explanation] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "explanations.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._explanations[k] = Explanation.from_dict(v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: v.to_dict() for k, v in self._explanations.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def explain(self, decision_id: str, title: str, why: str = "", how: str = "", expected_result: str = "", confidence: float = 0.0) -> Explanation:
        exp = Explanation(id=str(uuid.uuid4()), decision_id=decision_id, title=title, why=why, how=how, expected_result=expected_result, confidence=confidence)
        self._explanations[exp.id] = exp; self._save(); return exp

    def get_by_decision(self, decision_id: str) -> Optional[Explanation]:
        for e in self._explanations.values():
            if e.decision_id == decision_id: return e
        return None

    def generate_markdown(self, decision_id: str) -> str:
        exp = self.get_by_decision(decision_id)
        if not exp: return "No explanation available."
        return (f"### {exp.title}\n\n**Why:** {exp.why}\n\n**How:** {exp.how}\n\n"
                f"**Expected Result:** {exp.expected_result}\n\n"
                f"**Confidence:** {exp.confidence}\n\n"
                f"**Risk:** {exp.risk}\n\n"
                f"**Rollback:** {exp.rollback_strategy}")

    def get_telemetry(self) -> dict: return {"explanations": len(self._explanations)}
