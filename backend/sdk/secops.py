"""SecOps SDK mixin — Volume 63 Commit 1."""

from typing import Any, Dict, Optional


class SecOpsMixin:
    """Synchronous SecOps mixin."""

    def secops_ingest_event(self, **kwargs: Any) -> dict:
        return self.post(self._build_url("/secops/security-events"), data=kwargs)

    def secops_list_events(self, limit: int = 50, category: Optional[str] = None, severity: Optional[str] = None, actor: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if severity:
            params["severity"] = severity
        if actor:
            params["actor"] = actor
        return self.get(self._build_url("/secops/security-events"), params=params)

    def secops_get_event(self, event_id: str) -> dict:
        return self.get(self._build_url(f"/secops/security-events/{event_id}"))

    def secops_create_rule(self, name: str, rule_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "rule_type": rule_type}
        for k in ("description", "category", "severity", "conditions", "threshold", "time_window_seconds", "confidence", "owner", "enabled", "baseline_config", "change_reason"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/secops/detections/rules"), data=payload)

    def secops_list_rules(self, limit: int = 50, category: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        return self.get(self._build_url("/secops/detections/rules"), params=params)

    def secops_get_rule(self, rule_id: str) -> dict:
        return self.get(self._build_url(f"/secops/detections/rules/{rule_id}"))

    def secops_evaluate(self, events: list) -> dict:
        return self.post(self._build_url("/secops/detections/evaluate"), data={"events": events})

    def secops_list_alerts(self, status: Optional[str] = None, severity: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        return self.get(self._build_url("/secops/security-alerts"), params=params)

    def secops_get_alert(self, alert_id: str) -> dict:
        return self.get(self._build_url(f"/secops/security-alerts/{alert_id}"))

    def secops_acknowledge_alert(self, alert_id: str) -> dict:
        return self.post(self._build_url(f"/secops/security-alerts/{alert_id}/acknowledge"), data={})

    def secops_update_alert_status(self, alert_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/secops/security-alerts/{alert_id}/status"), data={"status": status})

    def secops_suppress_alerts(self, fingerprint: str, reason: str, owner: str, expiration: str) -> dict:
        return self.post(self._build_url("/secops/security-alerts/suppress"), data={"fingerprint": fingerprint, "reason": reason, "owner": owner, "expiration": expiration})

    def secops_create_finding(self, finding: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"finding": finding}
        for k in ("resource", "resource_type", "resource_id", "evidence", "policy", "policy_version", "severity", "owner", "status", "confidence", "exposure", "blast_radius"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/secops/findings"), data=payload)

    def secops_list_findings(self, status: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/secops/findings"), params=params)

    def secops_get_finding(self, finding_id: str) -> dict:
        return self.get(self._build_url(f"/secops/findings/{finding_id}"))

    def secops_update_finding_status(self, finding_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/secops/findings/{finding_id}/status"), data={"status": status})

    def secops_create_case(self, **kwargs: Any) -> dict:
        return self.post(self._build_url("/secops/cases"), data=kwargs)

    def secops_list_cases(self, status: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/secops/cases"), params=params)

    def secops_get_case(self, case_id: str) -> dict:
        return self.get(self._build_url(f"/secops/cases/{case_id}"))

    def secops_update_case_status(self, case_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/secops/cases/{case_id}/status"), data={"status": status})

    def secops_add_case_evidence(self, case_id: str, **kwargs: Any) -> dict:
        return self.post(self._build_url(f"/secops/cases/{case_id}/evidence"), data=kwargs)

    def secops_get_investigation(self, case_or_alert_id: str) -> dict:
        return self.get(self._build_url(f"/secops/investigations/{case_or_alert_id}"))

    def secops_create_indicator(self, indicator: str, indicator_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"indicator": indicator, "indicator_type": indicator_type}
        for k in ("source", "confidence", "expiration", "status", "feed_id"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/secops/indicators"), data=payload)

    def secops_list_indicators(self, limit: int = 50, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return self.get(self._build_url("/secops/indicators"), params=params)

    def secops_match_indicators(self, telemetry: list) -> dict:
        return self.post(self._build_url("/secops/indicators/match"), data={"telemetry": telemetry})

    def secops_update_indicator_status(self, indicator_id: str, status: str) -> dict:
        return self.post(self._build_url(f"/secops/indicators/{indicator_id}/status"), data={"status": status})

    def secops_calculate_risk(self, **kwargs: Any) -> dict:
        return self.post(self._build_url("/secops/risk/calculate"), data=kwargs)

    def secops_get_risk(self, resource_type: Optional[str] = None, resource_id: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if resource_type:
            params["resource_type"] = resource_type
        if resource_id:
            params["resource_id"] = resource_id
        return self.get(self._build_url("/secops/risk"), params=params or None)

    def secops_dashboard(self) -> dict:
        return self.get(self._build_url("/secops/dashboard"))


class AsyncSecOpsMixin:
    """Async SecOps mixin."""

    async def secops_ingest_event(self, **kwargs: Any) -> dict:
        return await self.post(self._build_url("/secops/security-events"), data=kwargs)

    async def secops_list_events(self, limit: int = 50, category: Optional[str] = None, severity: Optional[str] = None, actor: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        if severity:
            params["severity"] = severity
        if actor:
            params["actor"] = actor
        return await self.get(self._build_url("/secops/security-events"), params=params)

    async def secops_get_event(self, event_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/security-events/{event_id}"))

    async def secops_create_rule(self, name: str, rule_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "rule_type": rule_type}
        for k in ("description", "category", "severity", "conditions", "threshold", "time_window_seconds", "confidence", "owner", "enabled", "baseline_config", "change_reason"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/secops/detections/rules"), data=payload)

    async def secops_list_rules(self, limit: int = 50, category: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if category:
            params["category"] = category
        return await self.get(self._build_url("/secops/detections/rules"), params=params)

    async def secops_get_rule(self, rule_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/detections/rules/{rule_id}"))

    async def secops_evaluate(self, events: list) -> dict:
        return await self.post(self._build_url("/secops/detections/evaluate"), data={"events": events})

    async def secops_list_alerts(self, status: Optional[str] = None, severity: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        if severity:
            params["severity"] = severity
        return await self.get(self._build_url("/secops/security-alerts"), params=params)

    async def secops_get_alert(self, alert_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/security-alerts/{alert_id}"))

    async def secops_acknowledge_alert(self, alert_id: str) -> dict:
        return await self.post(self._build_url(f"/secops/security-alerts/{alert_id}/acknowledge"), data={})

    async def secops_update_alert_status(self, alert_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/secops/security-alerts/{alert_id}/status"), data={"status": status})

    async def secops_suppress_alerts(self, fingerprint: str, reason: str, owner: str, expiration: str) -> dict:
        return await self.post(self._build_url("/secops/security-alerts/suppress"), data={"fingerprint": fingerprint, "reason": reason, "owner": owner, "expiration": expiration})

    async def secops_create_finding(self, finding: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"finding": finding}
        for k in ("resource", "resource_type", "resource_id", "evidence", "policy", "policy_version", "severity", "owner", "status", "confidence", "exposure", "blast_radius"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/secops/findings"), data=payload)

    async def secops_list_findings(self, status: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/secops/findings"), params=params)

    async def secops_get_finding(self, finding_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/findings/{finding_id}"))

    async def secops_update_finding_status(self, finding_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/secops/findings/{finding_id}/status"), data={"status": status})

    async def secops_create_case(self, **kwargs: Any) -> dict:
        return await self.post(self._build_url("/secops/cases"), data=kwargs)

    async def secops_list_cases(self, status: Optional[str] = None, limit: int = 50) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/secops/cases"), params=params)

    async def secops_get_case(self, case_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/cases/{case_id}"))

    async def secops_update_case_status(self, case_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/secops/cases/{case_id}/status"), data={"status": status})

    async def secops_add_case_evidence(self, case_id: str, **kwargs: Any) -> dict:
        return await self.post(self._build_url(f"/secops/cases/{case_id}/evidence"), data=kwargs)

    async def secops_get_investigation(self, case_or_alert_id: str) -> dict:
        return await self.get(self._build_url(f"/secops/investigations/{case_or_alert_id}"))

    async def secops_create_indicator(self, indicator: str, indicator_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"indicator": indicator, "indicator_type": indicator_type}
        for k in ("source", "confidence", "expiration", "status", "feed_id"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/secops/indicators"), data=payload)

    async def secops_list_indicators(self, limit: int = 50, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if status:
            params["status"] = status
        return await self.get(self._build_url("/secops/indicators"), params=params)

    async def secops_match_indicators(self, telemetry: list) -> dict:
        return await self.post(self._build_url("/secops/indicators/match"), data={"telemetry": telemetry})

    async def secops_update_indicator_status(self, indicator_id: str, status: str) -> dict:
        return await self.post(self._build_url(f"/secops/indicators/{indicator_id}/status"), data={"status": status})

    async def secops_calculate_risk(self, **kwargs: Any) -> dict:
        return await self.post(self._build_url("/secops/risk/calculate"), data=kwargs)

    async def secops_get_risk(self, resource_type: Optional[str] = None, resource_id: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if resource_type:
            params["resource_type"] = resource_type
        if resource_id:
            params["resource_id"] = resource_id
        return await self.get(self._build_url("/secops/risk"), params=params or None)

    async def secops_dashboard(self) -> dict:
        return await self.get(self._build_url("/secops/dashboard"))
