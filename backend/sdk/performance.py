"""Performance SDK mixin — Volume 61 Commit 1.

Expects host to provide get/post/put/_build_url. Additive, no placeholders.
Reuses app.performance.* via API; tenant isolation enforced server-side.
"""

from typing import Any, Dict, Optional


class PerformanceMixin:
    """Synchronous Performance mixin."""

    # ── budgets ──────────────────────────────────────────────────────────
    def performance_create_budget(
        self,
        service: str,
        metric_type: str,
        metric_name: str,
        target: float,
        window: str = "1h",
        owner: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "service": service,
            "metric_type": metric_type,
            "metric_name": metric_name,
            "target": float(target),
            "window": window,
        }
        if owner is not None:
            payload["owner"] = owner
        # allow extra fields like dimensions without overwriting required
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        return self.post(self._build_url("/performance/budgets"), data=payload)

    def performance_list_budgets(
        self,
        service: Optional[str] = None,
        metric_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if service is not None:
            params["service"] = service
        if metric_type is not None:
            params["metric_type"] = metric_type
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/budgets"), params=params)

    def performance_check_budget(
        self,
        budget_id: str,
        observed: float,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"observed": float(observed)}
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url(f"/performance/budgets/{budget_id}/status"), params=params)

    # ── metrics ──────────────────────────────────────────────────────────
    def performance_record_metric(
        self,
        service: str,
        metric_name: str,
        value: float,
        granularity: str = "minute",
        dimensions: Optional[dict] = None,
        timestamp: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "service": service,
            "metric_name": metric_name,
            "value": float(value),
            "granularity": granularity,
            "dimensions": dimensions or {},
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        # filter None values but keep dimensions even if empty
        payload = {k: v for k, v in payload.items() if v is not None}
        return self.post(self._build_url("/performance/metrics/record"), data=payload)

    def performance_query_metrics(
        self,
        service: Optional[str] = None,
        metric_name: Optional[str] = None,
        granularity: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        timeout: int = 5,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "timeout": timeout}
        if service is not None:
            params["service"] = service
        if metric_name is not None:
            params["metric_name"] = metric_name
        if granularity is not None:
            params["granularity"] = granularity
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        # aliases: from/to, from_time/to_time, from_ts/to_ts
        for k in ("from_time", "to_time", "from", "to", "from_ts", "to_ts", "start", "end"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        # also handle explicit kwargs for start_time/end_time overrides
        for k in ("start_time", "end_time"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return self.get(self._build_url("/performance/metrics/query"), params=params)

    def performance_get_service_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        granularity: str = "hour",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> dict:
        if not service:
            raise ValueError("service is required")
        params: Dict[str, Any] = {"granularity": granularity, "limit": limit}
        if metric_name is not None:
            params["metric_name"] = metric_name
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url(f"/performance/services/{service}/metrics"), params=params)

    def performance_get_endpoint_metrics(
        self,
        route: Optional[str] = None,
        method: Optional[str] = None,
        service: str = "api",
        status: Optional[str] = None,
        granularity: Optional[str] = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"service": service, "limit": limit}
        if route is not None:
            params["route"] = route
        if method is not None:
            params["method"] = method
        if status is not None:
            params["status"] = status
        if granularity is not None:
            params["granularity"] = granularity
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/endpoints/metrics"), params=params)

    def performance_get_database_metrics(
        self,
        threshold_ms: float = 500,
        limit: int = 20,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"threshold_ms": float(threshold_ms), "limit": limit, "offset": offset}
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/database/metrics"), params=params)

    def performance_get_queue_metrics(
        self,
        queue_name: Optional[str] = None,
        queue: Optional[str] = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if queue_name is not None:
            params["queue_name"] = queue_name
        if queue is not None:
            params["queue"] = queue
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/queues/metrics"), params=params)

    def performance_get_capacity(
        self,
        resource: Optional[str] = None,
        pool_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if resource is not None:
            params["resource"] = resource
        if pool_type is not None:
            params["pool_type"] = pool_type
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/capacity"), params=params)

    def performance_get_recommendations(
        self,
        type: Optional[str] = None,
        status: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if type is not None:
            params["type"] = type
        if status is not None:
            params["status"] = status
        if resource is not None:
            params["resource"] = resource
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/recommendations"), params=params)

    def performance_scaling_event(
        self,
        resource: str,
        direction: str,
        reason: str,
        from_count: int,
        to_count: int,
        triggered_by: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "resource": resource,
            "direction": direction,
            "reason": reason,
            "from_count": int(from_count),
            "to_count": int(to_count),
        }
        if triggered_by is not None:
            payload["triggered_by"] = triggered_by
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        return self.post(self._build_url("/performance/scaling-events"), data=payload)

    # optional: list scaling events (additive convenience, not required but useful)
    def performance_list_scaling_events(
        self,
        resource: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if resource is not None:
            params["resource"] = resource
        if direction is not None:
            params["direction"] = direction
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return self.get(self._build_url("/performance/scaling-events"), params=params)


class AsyncPerformanceMixin:
    """Async Performance mixin — mirrors PerformanceMixin with await."""

    async def performance_create_budget(
        self,
        service: str,
        metric_type: str,
        metric_name: str,
        target: float,
        window: str = "1h",
        owner: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "service": service,
            "metric_type": metric_type,
            "metric_name": metric_name,
            "target": float(target),
            "window": window,
        }
        if owner is not None:
            payload["owner"] = owner
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        return await self.post(self._build_url("/performance/budgets"), data=payload)

    async def performance_list_budgets(
        self,
        service: Optional[str] = None,
        metric_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if service is not None:
            params["service"] = service
        if metric_type is not None:
            params["metric_type"] = metric_type
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/budgets"), params=params)

    async def performance_check_budget(
        self,
        budget_id: str,
        observed: float,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"observed": float(observed)}
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url(f"/performance/budgets/{budget_id}/status"), params=params)

    async def performance_record_metric(
        self,
        service: str,
        metric_name: str,
        value: float,
        granularity: str = "minute",
        dimensions: Optional[dict] = None,
        timestamp: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "service": service,
            "metric_name": metric_name,
            "value": float(value),
            "granularity": granularity,
            "dimensions": dimensions or {},
        }
        if timestamp is not None:
            payload["timestamp"] = timestamp
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        payload = {k: v for k, v in payload.items() if v is not None}
        return await self.post(self._build_url("/performance/metrics/record"), data=payload)

    async def performance_query_metrics(
        self,
        service: Optional[str] = None,
        metric_name: Optional[str] = None,
        granularity: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
        timeout: int = 5,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "timeout": timeout}
        if service is not None:
            params["service"] = service
        if metric_name is not None:
            params["metric_name"] = metric_name
        if granularity is not None:
            params["granularity"] = granularity
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        for k in ("from_time", "to_time", "from", "to", "from_ts", "to_ts", "start", "end"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        for k in ("start_time", "end_time"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return await self.get(self._build_url("/performance/metrics/query"), params=params)

    async def performance_get_service_metrics(
        self,
        service: str,
        metric_name: Optional[str] = None,
        granularity: str = "hour",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> dict:
        if not service:
            raise ValueError("service is required")
        params: Dict[str, Any] = {"granularity": granularity, "limit": limit}
        if metric_name is not None:
            params["metric_name"] = metric_name
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url(f"/performance/services/{service}/metrics"), params=params)

    async def performance_get_endpoint_metrics(
        self,
        route: Optional[str] = None,
        method: Optional[str] = None,
        service: str = "api",
        status: Optional[str] = None,
        granularity: Optional[str] = None,
        limit: int = 500,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"service": service, "limit": limit}
        if route is not None:
            params["route"] = route
        if method is not None:
            params["method"] = method
        if status is not None:
            params["status"] = status
        if granularity is not None:
            params["granularity"] = granularity
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/endpoints/metrics"), params=params)

    async def performance_get_database_metrics(
        self,
        threshold_ms: float = 500,
        limit: int = 20,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"threshold_ms": float(threshold_ms), "limit": limit, "offset": offset}
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/database/metrics"), params=params)

    async def performance_get_queue_metrics(
        self,
        queue_name: Optional[str] = None,
        queue: Optional[str] = None,
        limit: int = 100,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        if queue_name is not None:
            params["queue_name"] = queue_name
        if queue is not None:
            params["queue"] = queue
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/queues/metrics"), params=params)

    async def performance_get_capacity(
        self,
        resource: Optional[str] = None,
        pool_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if resource is not None:
            params["resource"] = resource
        if pool_type is not None:
            params["pool_type"] = pool_type
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/capacity"), params=params)

    async def performance_get_recommendations(
        self,
        type: Optional[str] = None,
        status: Optional[str] = None,
        resource: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if type is not None:
            params["type"] = type
        if status is not None:
            params["status"] = status
        if resource is not None:
            params["resource"] = resource
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/recommendations"), params=params)

    async def performance_scaling_event(
        self,
        resource: str,
        direction: str,
        reason: str,
        from_count: int,
        to_count: int,
        triggered_by: Optional[str] = None,
        **kwargs: Any,
    ) -> dict:
        payload: Dict[str, Any] = {
            "resource": resource,
            "direction": direction,
            "reason": reason,
            "from_count": int(from_count),
            "to_count": int(to_count),
        }
        if triggered_by is not None:
            payload["triggered_by"] = triggered_by
        for k, v in kwargs.items():
            if v is not None:
                payload[k] = v
        return await self.post(self._build_url("/performance/scaling-events"), data=payload)

    async def performance_list_scaling_events(
        self,
        resource: Optional[str] = None,
        direction: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        **kwargs: Any,
    ) -> dict:
        params: Dict[str, Any] = {"limit": limit, "offset": offset}
        if resource is not None:
            params["resource"] = resource
        if direction is not None:
            params["direction"] = direction
        for k, v in kwargs.items():
            if v is not None:
                params[k] = v
        return await self.get(self._build_url("/performance/scaling-events"), params=params)
