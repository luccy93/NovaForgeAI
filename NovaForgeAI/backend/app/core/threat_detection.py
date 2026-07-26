"""Threat detection — brute force, credential stuffing, suspicious activity."""

import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional


class ThreatDetector:
    """Detects and flags suspicious security activity."""

    def __init__(self):
        self._attempts: dict[str, list[float]] = defaultdict(list)
        self._flagged_ips: dict[str, float] = {}

    def record_event(self, event_type: str, ip: str, email: Optional[str] = None, user_id: Optional[str] = None) -> Optional[dict]:
        now = time.time()
        key = f"{event_type}:{ip}"
        self._attempts[key].append(now)
        self._attempts[key] = [t for t in self._attempts[key] if now - t < 3600]

        alert = None

        if event_type == "auth_failure":
            count_5m = sum(1 for t in self._attempts[key] if now - t < 300)
            if count_5m >= 10:
                alert = self._create_alert("brute_force", ip, email, count_5m)
            if self._is_credential_stuffing(ip, email):
                alert = self._create_alert("credential_stuffing", ip, email)

        elif event_type == "api_key_failure":
            if len(self._attempts[key]) >= 5:
                alert = self._create_alert("api_key_abuse", ip, email)

        elif event_type == "suspicious_request":
            if len(self._attempts[key]) >= 20:
                alert = self._create_alert("suspicious_activity", ip)

        return alert

    def _is_credential_stuffing(self, ip: str, email: Optional[str]) -> bool:
        if not email:
            return False
        attempts = self._attempts.get(f"auth_failure:{ip}", [])
        if len(attempts) < 20:
            return False
        now = time.time()
        recent = [t for t in attempts if now - t < 60]
        return len(recent) >= 5

    def _create_alert(self, threat_type: str, ip: str, email: Optional[str] = None, count: Optional[int] = None) -> dict:
        self._flagged_ips[ip] = time.time()
        alert = {
            "type": threat_type,
            "ip": ip,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": "high" if threat_type in ("brute_force", "credential_stuffing") else "medium",
        }
        if email:
            alert["email"] = email
        if count:
            alert["attempts"] = count
        return alert

    def is_ip_flagged(self, ip: str) -> bool:
        flagged_time = self._flagged_ips.get(ip)
        if flagged_time and time.time() - flagged_time < 900:
            return True
        return False

    def get_recent_alerts(self, limit: int = 50) -> list[dict]:
        now = time.time()
        alerts = []
        for ip, ts in self._flagged_ips.items():
            if now - ts < 3600:
                alerts.append({
                    "type": "flagged_ip",
                    "ip": ip,
                    "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
                })
        return alerts[:limit]


threat_detector = ThreatDetector()
