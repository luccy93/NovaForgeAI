"""Incident Response Platform -- Investigation Agent (Volume 49).

AI-powered read-only investigation agent that searches logs, queries metrics,
inspects traces, examines code intelligence, and searches RAG.
No production write access by default.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


class InvestigationAgent:
    """Read-only incident investigation agent."""

    def __init__(self):
        self._investigations: dict[str, dict[str, Any]] = {}
        self._log_entries: list[dict[str, Any]] = []
        self._metric_queries: list[dict[str, Any]] = []
        self._trace_entries: list[dict[str, Any]] = []

    def add_log_entry(self, service: str, level: str, message: str,
                      timestamp: str = "", request_id: str = "",
                      trace_id: str = "", metadata: dict | None = None) -> dict:
        entry = {"service": service, "level": level, "message": message,
                 "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                 "request_id": request_id, "trace_id": trace_id,
                 "metadata": metadata or {}}
        self._log_entries.append(entry)
        return entry

    def add_trace_entry(self, service: str, operation: str, duration_ms: float,
                        status: str = "ok", trace_id: str = "",
                        parent_id: str = "", timestamp: str = "",
                        metadata: dict | None = None) -> dict:
        entry = {"service": service, "operation": operation, "duration_ms": duration_ms,
                 "status": status, "trace_id": trace_id, "parent_id": parent_id,
                 "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
                 "metadata": metadata or {}}
        self._trace_entries.append(entry)
        return entry

    def record_metric_query(self, query: str, service: str, result: dict,
                            queried_at: str = "") -> dict:
        entry = {"query": query, "service": service, "result": result,
                 "queried_at": queried_at or datetime.now(timezone.utc).isoformat()}
        self._metric_queries.append(entry)
        return entry

    def search_logs(self, service: str = "", level: str = "",
                    time_range_hours: int = 1, request_id: str = "",
                    trace_id: str = "", keyword: str = "",
                    limit: int = 100) -> list[dict[str, Any]]:
        results = []
        for entry in self._log_entries:
            if service and entry.get("service") != service:
                continue
            if level and entry.get("level") != level:
                continue
            if request_id and entry.get("request_id") != request_id:
                continue
            if trace_id and entry.get("trace_id") != trace_id:
                continue
            if keyword and keyword.lower() not in entry.get("message", "").lower():
                continue
            results.append(entry)
        return results[:limit]

    def search_traces(self, service: str = "", operation: str = "",
                      status: str = "", slow_threshold_ms: float = 0,
                      limit: int = 50) -> list[dict[str, Any]]:
        results = []
        for entry in self._trace_entries:
            if service and entry.get("service") != service:
                continue
            if operation and entry.get("operation") != operation:
                continue
            if status and entry.get("status") != status:
                continue
            if slow_threshold_ms and entry.get("duration_ms", 0) < slow_threshold_ms:
                continue
            results.append(entry)
        results.sort(key=lambda e: e.get("duration_ms", 0), reverse=True)
        return results[:limit]

    def find_slow_spans(self, service: str = "", threshold_ms: float = 1000) -> list[dict]:
        return self.search_traces(service=service, slow_threshold_ms=threshold_ms)

    def find_error_traces(self, service: str = "") -> list[dict]:
        return self.search_traces(service=service, status="error")

    def investigate(self, incident: dict, focus_areas: list[str] | None = None,
                    max_tokens: int = 5000) -> dict[str, Any]:
        investigation_id = str(uuid4())
        service = incident.get("service", "")
        incident_id = incident.get("id", "")

        logs = self.search_logs(service=service, level="error")
        slow_spans = self.find_slow_spans(service=service)
        error_traces = self.find_error_traces(service=service)

        hypotheses = []
        if logs:
            hypotheses.append({
                "hypothesis": f"Found {len(logs)} error logs for service '{service}'",
                "confidence": 0.6,
                "evidence": [{"type": "logs", "count": len(logs), "samples": logs[:3]}],
                "source": "investigation_agent",
            })
        if slow_spans:
            hypotheses.append({
                "hypothesis": f"Found {len(slow_spans)} slow spans (>{slow_spans[0].get('duration_ms', 0):.0f}ms)",
                "confidence": 0.5,
                "evidence": [{"type": "traces", "count": len(slow_spans), "samples": slow_spans[:3]}],
                "source": "investigation_agent",
            })
        if error_traces:
            hypotheses.append({
                "hypothesis": f"Found {len(error_traces)} error traces in service '{service}'",
                "confidence": 0.7,
                "evidence": [{"type": "error_traces", "count": len(error_traces)}],
                "source": "investigation_agent",
            })

        investigation = {
            "id": investigation_id,
            "incident_id": incident_id,
            "service": service,
            "hypotheses": hypotheses,
            "logs_analyzed": len(logs),
            "traces_analyzed": len(slow_spans) + len(error_traces),
            "focus_areas": focus_areas or [],
            "tokens_used": min(max_tokens, len(str(hypotheses)) // 4),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        self._investigations[investigation_id] = investigation
        return investigation

    def get_investigation(self, investigation_id: str) -> dict[str, Any] | None:
        return self._investigations.get(investigation_id)

    def list_investigations(self, incident_id: str = "", limit: int = 20) -> list[dict]:
        results = []
        for inv in self._investigations.values():
            if incident_id and inv.get("incident_id") != incident_id:
                continue
            results.append(inv)
        return results[:limit]
