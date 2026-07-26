"""Knowledge Recommendation — docs, repos, architecture, decisions, incidents, bugs, PRs, standards."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Recommendation:
    id: str; org_id: str; rec_type: str; title: str; description: str = ""
    source: str = ""; target_id: str = ""; confidence: float = 0.0; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeRecommendationEngine:
    def __init__(self, storage_dir: str = "knowledge_data/recommendations"):
        self.storage_dir = storage_dir; self._recs: dict[str, Recommendation] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "recommendations.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._recs[k] = Recommendation(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._recs.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def recommend(self, org_id: str, rec_type: str, title: str, description: str = "", source: str = "", target_id: str = "") -> Recommendation:
        r = Recommendation(id=str(uuid.uuid4()), org_id=org_id, rec_type=rec_type, title=title, description=description, source=source, target_id=target_id, confidence=0.75)
        self._recs[r.id] = r; self._save(); return r

    def get_by_type(self, org_id: str, rec_type: str) -> list[Recommendation]:
        return sorted([r for r in self._recs.values() if r.org_id == org_id and r.rec_type == rec_type], key=lambda r: r.confidence, reverse=True)

    def get_telemetry(self) -> dict: return {"recommendations": len(self._recs)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional, Any

logger = logging.getLogger(__name__)

@dataclass
class DecisionRecord:
    id: str; org_id: str; title: str; decision_type: str; author_id: str = ""
    approver_id: str = ""; reason: str = ""; evidence: list = field(default_factory=list)
    impact: str = ""; rollback_strategy: str = ""; tags: list = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeDecisionMemory:
    def __init__(self, storage_dir: str = "knowledge_data/decisions"):
        self.storage_dir = storage_dir; self._records: dict[str, DecisionRecord] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "records.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._records[k] = DecisionRecord(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._records.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def store(self, org_id: str, title: str, decision_type: str, author_id: str = "", reason: str = "", evidence: list = None) -> DecisionRecord:
        dr = DecisionRecord(id=str(uuid.uuid4()), org_id=org_id, title=title, decision_type=decision_type, author_id=author_id, reason=reason, evidence=evidence or [])
        self._records[dr.id] = dr; self._save(); return dr

    def search(self, org_id: str, query: str) -> list[DecisionRecord]:
        q = query.lower()
        return [d for d in self._records.values() if d.org_id == org_id and (q in d.title.lower() or q in d.reason.lower())]

    def get_telemetry(self) -> dict: return {"records": len(self._records)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class Summary:
    id: str; org_id: str; target_type: str; target_id: str; summary: str = ""
    key_points: list = field(default_factory=list); created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeSummarization:
    def __init__(self, storage_dir: str = "knowledge_data/summaries"):
        self.storage_dir = storage_dir; self._summaries: dict[str, Summary] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "summaries.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._summaries[k] = Summary(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._summaries.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def generate(self, org_id: str, target_type: str, target_id: str, content: str = "") -> Summary:
        s = Summary(id=str(uuid.uuid4()), org_id=org_id, target_type=target_type, target_id=target_id, summary=f"Auto-generated summary of {target_type}: {content[:100]}...", key_points=[f"Key point from {target_type}"])
        self._summaries[s.id] = s; self._save(); return s

    def get_latest(self, org_id: str, target_type: str) -> list[Summary]:
        return sorted([s for s in self._summaries.values() if s.org_id == org_id and s.target_type == target_type], key=lambda s: s.created_at, reverse=True)[:10]

    def get_telemetry(self) -> dict: return {"summaries": len(self._summaries)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class EvolutionTrack:
    id: str; org_id: str; track_type: str; target_id: str; state: dict = field(default_factory=dict)
    version: int = 1; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class KnowledgeEvolution:
    def __init__(self, storage_dir: str = "knowledge_data/evolution"):
        self.storage_dir = storage_dir; self._tracks: dict[str, EvolutionTrack] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "tracks.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._tracks[k] = EvolutionTrack(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._tracks.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def track(self, org_id: str, track_type: str, target_id: str, state: dict = None) -> EvolutionTrack:
        t = EvolutionTrack(id=str(uuid.uuid4()), org_id=org_id, track_type=track_type, target_id=target_id, state=state or {})
        self._tracks[t.id] = t; self._save(); return t

    def get_history(self, org_id: str, track_type: str) -> list[EvolutionTrack]:
        return sorted([t for t in self._tracks.values() if t.org_id == org_id and t.track_type == track_type], key=lambda t: t.version)

    def get_telemetry(self) -> dict: return {"tracks": len(self._tracks)}

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class WikiPage:
    id: str; org_id: str; title: str; content: str = ""; category: str = "general"
    auto_generated: bool = True; tags: list = field(default_factory=list)
    version: int = 1; created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

class EnterpriseWiki:
    def __init__(self, storage_dir: str = "knowledge_data/wiki"):
        self.storage_dir = storage_dir; self._pages: dict[str, WikiPage] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "pages.json")
    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._pages[k] = WikiPage(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f: json.dump({k: asdict(v) for k, v in self._pages.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def create_page(self, org_id: str, title: str, content: str = "", category: str = "general") -> WikiPage:
        p = WikiPage(id=str(uuid.uuid4()), org_id=org_id, title=title, content=content, category=category)
        self._pages[p.id] = p; self._save(); return p

    def search(self, org_id: str, query: str) -> list[WikiPage]:
        q = query.lower()
        return [p for p in self._pages.values() if p.org_id == org_id and (q in p.title.lower() or q in p.content.lower())]

    def get_telemetry(self) -> dict: return {"pages": len(self._pages)}
