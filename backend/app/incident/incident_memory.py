"""Incident Response Platform -- Incident Memory (Volume 49).

Stores verified incident patterns, timelines, root causes, remediations,
runbooks, and lessons. Feeds RAG. Never stores unverified AI hypotheses.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class IncidentMemory:
    """Verified incident knowledge store."""

    def __init__(self):
        self._memories: dict[str, dict[str, Any]] = {}

    def store_verified_incident(self, incident: dict, postmortem: dict | None = None,
                                lessons: list | None = None) -> dict[str, Any]:
        memory_id = str(uuid4())
        memory = {
            "id": memory_id,
            "incident_id": incident.get("id", ""),
            "title": incident.get("title", ""),
            "service": incident.get("service", ""),
            "severity": incident.get("severity", ""),
            "root_cause": incident.get("root_cause", ""),
            "remediation": incident.get("remediation", ""),
            "fingerprint": incident.get("fingerprint", ""),
            "resolved_at": incident.get("resolved_at", ""),
            "postmortem_summary": postmortem.get("summary", "") if postmortem else "",
            "lessons": lessons or [],
            "verified": True,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        self._memories[memory_id] = memory
        return memory

    def store_runbook_knowledge(self, runbook: dict, incident_type: str,
                                success_rate: float = 1.0) -> dict[str, Any]:
        memory_id = str(uuid4())
        memory = {
            "id": memory_id,
            "type": "runbook_knowledge",
            "runbook_id": runbook.get("id", ""),
            "runbook_name": runbook.get("name", ""),
            "incident_type": incident_type,
            "success_rate": success_rate,
            "verified": True,
            "stored_at": datetime.now(timezone.utc).isoformat(),
        }
        self._memories[memory_id] = memory
        return memory

    def search(self, query: str = "", service: str = "",
               incident_type: str = "", limit: int = 20) -> list[dict[str, Any]]:
        results = []
        for mem in self._memories.values():
            if not mem.get("verified"):
                continue
            if service and mem.get("service") != service:
                continue
            if query:
                query_lower = query.lower()
                text = f"{mem.get('title', '')} {mem.get('root_cause', '')} {mem.get('remediation', '')}".lower()
                if query_lower not in text:
                    continue
            results.append(mem)
        return results[:limit]

    def get_similar_incidents(self, incident: dict, limit: int = 5) -> list[dict[str, Any]]:
        service = incident.get("service", "")
        fingerprint = incident.get("fingerprint", "")
        results = []
        for mem in self._memories.values():
            if not mem.get("verified"):
                continue
            score = 0
            if service and mem.get("service") == service:
                score += 1
            if fingerprint and mem.get("fingerprint") == fingerprint:
                score += 3
            if score > 0:
                results.append({**mem, "_relevance_score": score})
        results.sort(key=lambda m: m.get("_relevance_score", 0), reverse=True)
        return results[:limit]

    def get_stats(self) -> dict[str, Any]:
        total = len(self._memories)
        verified = sum(1 for m in self._memories.values() if m.get("verified"))
        services = set(m.get("service", "") for m in self._memories.values() if m.get("verified"))
        return {"total_memories": total, "verified": verified,
                "services_covered": len(services)}

    def get_knowledge_for_rag(self, service: str = "", limit: int = 10) -> list[dict]:
        return self.search(service=service, limit=limit)
