"""Team Intelligence — analytics, velocity, knowledge sharing, participation, adoption."""
import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger(__name__)

@dataclass
class TeamMetrics:
    period: str; total_members: int = 0; active_members: int = 0
    messages_sent: int = 0; reviews_participated: int = 0; knowledge_articles: int = 0
    meetings_held: int = 0; tasks_completed: int = 0; ai_sessions: int = 0
    collaboration_score: float = 0.0; knowledge_sharing_score: float = 0.0

class TeamIntelligence:
    def __init__(self, storage_dir: str = "rtc_data/insights"):
        self.storage_dir = storage_dir; self._metrics: dict[str, TeamMetrics] = {}
        os.makedirs(self.storage_dir, exist_ok=True); self._load()

    def _path(self) -> str: return os.path.join(self.storage_dir, "metrics.json")

    def _load(self) -> None:
        if os.path.exists(self._path()):
            try:
                with open(self._path(), "r") as f: data = json.load(f)
                for k, v in data.items():
                    try: self._metrics[k] = TeamMetrics(**v)
                    except Exception as e: logger.warning("Skipping %s: %s", k, e)
            except Exception as e: logger.error("Load error: %s", e)

    def _save(self) -> None:
        try:
            with open(self._path(), "w") as f:
                json.dump({k: asdict(v) for k, v in self._metrics.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Save error: %s", e)

    def record(self, org_id: str, metrics: dict) -> TeamMetrics:
        m = TeamMetrics(period=datetime.now(timezone.utc).strftime("%Y-%m"), **{k: v for k, v in metrics.items() if hasattr(TeamMetrics, k)})
        key = f"{org_id}_{m.period}"
        self._metrics[key] = m; self._save(); return m

    def get_team_health(self, org_id: str) -> dict:
        relevant = [m for k, m in self._metrics.items() if k.startswith(org_id)]
        if not relevant: return {"org_id": org_id, "health": "insufficient_data"}
        latest = sorted(relevant, key=lambda m: m.period, reverse=True)[0]
        return {"org_id": org_id, "period": latest.period, "active_members": latest.active_members, "collaboration_score": latest.collaboration_score}
