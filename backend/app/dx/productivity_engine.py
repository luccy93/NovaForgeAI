"""Productivity Engine — measure, analyze, and optimize developer productivity across all engineering activities."""
import json, uuid, os, logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class ActivityType(Enum):
    CODING = "coding"
    REVIEWING = "reviewing"
    DEBUGGING = "debugging"
    TESTING = "testing"
    DEPLOYING = "deploying"
    DOCUMENTING = "documenting"
    SEARCHING = "searching"
    CHATTING = "chatting"
    PLANNING = "planning"


@dataclass
class ProductivitySession:
    id: str
    user_id: str
    org_id: str
    activity_type: ActivityType
    start_time: str
    end_time: str = ""
    duration_minutes: float = 0.0
    output_count: int = 0
    ai_assisted: bool = False
    interrupted: bool = False
    focus_score: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["activity_type"] = self.activity_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProductivitySession":
        data = data.copy()
        data["activity_type"] = ActivityType(data.get("activity_type", "coding"))
        return cls(**data)


class ProductivityEngine:
    def __init__(self, storage_dir: str = "dx_data/productivity"):
        self.storage_dir = storage_dir
        self._sessions: dict[str, ProductivitySession] = {}
        self._telemetry: dict[str, int] = {}
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _store_path(self) -> str: return os.path.join(self.storage_dir, "sessions.json")

    def _load(self) -> None:
        path = self._store_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    try: self._sessions[k] = ProductivitySession.from_dict(v)
                    except Exception as e: logger.warning("Skipping session %s: %s", k, e)
            except Exception as e: logger.error("Failed to load productivity data: %s", e)

    def _save(self) -> None:
        try:
            with open(self._store_path(), "w", encoding="utf-8") as f:
                json.dump({k: v.to_dict() for k, v in self._sessions.items()}, f, indent=2, default=str)
        except Exception as e: logger.error("Failed to save productivity data: %s", e)

    def start_session(self, user_id: str, org_id: str, activity_type: ActivityType, ai_assisted: bool = False) -> ProductivitySession:
        session = ProductivitySession(id=str(uuid.uuid4()), user_id=user_id, org_id=org_id, activity_type=activity_type, start_time=datetime.now(timezone.utc).isoformat(), ai_assisted=ai_assisted)
        self._sessions[session.id] = session
        self._save()
        return session

    def end_session(self, session_id: str, output_count: int = 0, interrupted: bool = False) -> bool:
        session = self._sessions.get(session_id)
        if not session: return False
        session.end_time = datetime.now(timezone.utc).isoformat()
        start = datetime.fromisoformat(session.start_time)
        end = datetime.fromisoformat(session.end_time)
        session.duration_minutes = round((end - start).total_seconds() / 60, 2)
        session.output_count = output_count
        session.interrupted = interrupted
        session.focus_score = round(1.0 - (0.3 if interrupted else 0.0), 2)
        self._save()
        return True

    def get_daily_summary(self, user_id: str, date: str = "") -> dict:
        if not date: date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        sessions = [s for s in self._sessions.values() if s.user_id == user_id and s.start_time.startswith(date)]
        total_time = sum(s.duration_minutes for s in sessions if s.end_time)
        return {
            "date": date, "total_sessions": len(sessions),
            "total_time_minutes": round(total_time, 2),
            "by_activity": {a.value: round(sum(s.duration_minutes for s in sessions if s.activity_type == a and s.end_time), 2) for a in ActivityType},
            "ai_assisted": sum(1 for s in sessions if s.ai_assisted),
            "focus_score": round(sum(s.focus_score for s in sessions if s.end_time) / max(len([s for s in sessions if s.end_time]), 1), 2),
        }

    def get_weekly_report(self, user_id: str) -> dict:
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        sessions = [s for s in self._sessions.values() if s.user_id == user_id and s.start_time >= week_ago]
        total_time = sum(s.duration_minutes for s in sessions if s.end_time)
        return {
            "total_time_minutes": round(total_time, 2),
            "total_sessions": len(sessions),
            "avg_session_minutes": round(total_time / max(len([s for s in sessions if s.end_time]), 1), 2),
            "by_activity": {a.value: len([s for s in sessions if s.activity_type == a]) for a in ActivityType},
        }

    def get_telemetry(self) -> dict: return dict(self._telemetry)
