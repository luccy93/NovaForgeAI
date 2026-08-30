"""Data Platform SDK mixin — Volume 65."""

from typing import Any, Dict, Optional


class DataPlatformMixin:
    """Synchronous Data Platform mixin."""

    def dp_create_dataset(self, name: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name}
        for k in ("description", "workspace", "project", "owner", "team", "classification", "region", "status", "retention_days"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/datasets"), data=payload)

    def dp_list_datasets(self, limit: int = 50, **kwargs: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        for k in ("status", "classification", "owner"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return self.get(self._build_url("/data-platform/datasets"), params=params)

    def dp_get_dataset(self, dataset_id: str) -> dict:
        return self.get(self._build_url(f"/data-platform/datasets/{dataset_id}"))

    def dp_create_source(self, name: str, connector: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "connector": connector}
        for k in ("credentials", "region", "classification", "owner", "config"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/sources"), data=payload)

    def dp_create_schema(self, dataset_id: str, fields: list, version: str = "1.0", **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"version": version, "fields": fields}
        for k in ("classification",):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/schemas"), data=payload, params={"dataset_id": dataset_id})

    def dp_create_pipeline(self, name: str, steps: list, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "steps": steps}
        for k in ("description", "dependencies", "schedule", "owner", "region", "priority", "resource_limits", "status"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/pipelines"), data=payload)

    def dp_run_pipeline(self, pipeline_id: str, payload: dict | None = None) -> dict:
        return self.post(self._build_url(f"/data-platform/pipelines/{pipeline_id}/runs"), data=payload or {})

    def dp_create_quality_rule(self, dataset_id: str, name: str, rule_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "rule_type": rule_type}
        for k in ("params", "version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/quality/rules"), data=payload, params={"dataset_id": dataset_id})

    def dp_run_quality(self, dataset_id: str, records: list) -> dict:
        return self.post(self._build_url("/data-platform/quality/jobs"), data={"dataset_id": dataset_id, "records": records})

    def dp_create_lineage(self, source: str, target: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"source": source, "target": target}
        for k in ("transformation", "pipeline_id", "column_lineage"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/lineage"), data=payload)

    def dp_get_lineage(self, node: str, direction: str = "upstream", depth: int = 3) -> dict:
        return self.get(self._build_url(f"/data-platform/lineage/{node}/{direction}"), params={"depth": depth})

    def dp_search_catalog(self, q: str | None = None, semantic: bool = False, offline: bool = False, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit, "semantic": semantic, "offline": offline}
        if q:
            params["q"] = q
        return self.get(self._build_url("/data-platform/catalog/search"), params=params)

    def dp_create_stream(self, topic: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"topic": topic}
        for k in ("partition", "consumer_group", "region"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/streams"), data=payload)

    def dp_ingest_stream(self, topic: str, payload: dict) -> dict:
        return self.post(self._build_url(f"/data-platform/streams/{topic}/ingest"), data=payload)

    # Commit 2 additions
    def dp_write_tier(self, dataset_id: str, tier: str, records: list, fmt: str = "json") -> dict:
        return self.post(self._build_url(f"/data-platform/lakehouse/{dataset_id}/tier"), data={"tier": tier, "records": records, "format": fmt})

    def dp_get_freshness(self, dataset_id: str) -> dict:
        return self.get(self._build_url(f"/data-platform/freshness/{dataset_id}"))

    def dp_update_freshness(self, dataset_id: str, expected_interval_hours: int = 24) -> dict:
        return self.post(self._build_url(f"/data-platform/freshness/{dataset_id}"), data={"expected_interval_hours": expected_interval_hours})

    def dp_check_drift(self, dataset_id: str, current_schema: list, previous_schema: list | None = None) -> dict:
        return self.post(self._build_url(f"/data-platform/drift/{dataset_id}/check"), data={"current_schema": current_schema, "previous_schema": previous_schema})

    def dp_create_product(self, name: str, owner: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "owner": owner}
        for k in ("description", "contract", "classification", "domain", "slo", "status"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/data-products"), data=payload)

    def dp_list_products(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/data-platform/data-products"), params={"limit": limit})

    def dp_create_domain(self, name: str, owner: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "owner": owner}
        for k in ("description",):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/data-platform/data-domains"), data=payload)

    def dp_reconcile(self, source_count: int, processed_count: int, output_count: int) -> dict:
        return self.post(self._build_url("/data-platform/reconciliation"), data={"source_count": source_count, "processed_count": processed_count, "output_count": output_count})

    def dp_replay(self, topic: str, scope: dict | None = None) -> dict:
        return self.post(self._build_url("/data-platform/replay"), data={"topic": topic, "scope": scope or {}})

    def dp_export(self, dataset_id: str, purpose: str = "analysis", destination: str = "s3") -> dict:
        return self.post(self._build_url("/data-platform/exports"), data={"dataset_id": dataset_id, "purpose": purpose, "destination": destination})

    def dp_get_anomalies(self, limit: int = 20) -> dict:
        return self.get(self._build_url("/data-platform/access-anomalies"), params={"limit": limit})


class AsyncDataPlatformMixin:
    """Async Data Platform mixin."""

    async def dp_create_dataset(self, name: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name}
        for k in ("description", "workspace", "project", "owner", "team", "classification", "region", "status", "retention_days"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/datasets"), data=payload)

    async def dp_list_datasets(self, limit: int = 50, **kwargs: Any) -> dict:
        params: Dict[str, Any] = {"limit": limit}
        for k in ("status", "classification", "owner"):
            if k in kwargs and kwargs[k] is not None:
                params[k] = kwargs[k]
        return await self.get(self._build_url("/data-platform/datasets"), params=params)

    async def dp_get_dataset(self, dataset_id: str) -> dict:
        return await self.get(self._build_url(f"/data-platform/datasets/{dataset_id}"))

    async def dp_create_source(self, name: str, connector: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "connector": connector}
        for k in ("credentials", "region", "classification", "owner", "config"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/sources"), data=payload)

    async def dp_create_schema(self, dataset_id: str, fields: list, version: str = "1.0", **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"version": version, "fields": fields}
        for k in ("classification",):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/schemas"), data=payload, params={"dataset_id": dataset_id})

    async def dp_create_pipeline(self, name: str, steps: list, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "steps": steps}
        for k in ("description", "dependencies", "schedule", "owner", "region", "priority", "resource_limits", "status"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/pipelines"), data=payload)

    async def dp_run_pipeline(self, pipeline_id: str, payload: dict | None = None) -> dict:
        return await self.post(self._build_url(f"/data-platform/pipelines/{pipeline_id}/runs"), data=payload or {})

    async def dp_create_quality_rule(self, dataset_id: str, name: str, rule_type: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "rule_type": rule_type}
        for k in ("params", "version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/quality/rules"), data=payload, params={"dataset_id": dataset_id})

    async def dp_run_quality(self, dataset_id: str, records: list) -> dict:
        return await self.post(self._build_url("/data-platform/quality/jobs"), data={"dataset_id": dataset_id, "records": records})

    async def dp_create_lineage(self, source: str, target: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"source": source, "target": target}
        for k in ("transformation", "pipeline_id", "column_lineage"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/lineage"), data=payload)

    async def dp_get_lineage(self, node: str, direction: str = "upstream", depth: int = 3) -> dict:
        return await self.get(self._build_url(f"/data-platform/lineage/{node}/{direction}"), params={"depth": depth})

    async def dp_search_catalog(self, q: str | None = None, semantic: bool = False, offline: bool = False, limit: int = 20) -> dict:
        params: Dict[str, Any] = {"limit": limit, "semantic": semantic, "offline": offline}
        if q:
            params["q"] = q
        return await self.get(self._build_url("/data-platform/catalog/search"), params=params)

    async def dp_create_stream(self, topic: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"topic": topic}
        for k in ("partition", "consumer_group", "region"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/streams"), data=payload)

    async def dp_ingest_stream(self, topic: str, payload: dict) -> dict:
        return await self.post(self._build_url(f"/data-platform/streams/{topic}/ingest"), data=payload)

    async def dp_write_tier(self, dataset_id: str, tier: str, records: list, fmt: str = "json") -> dict:
        return await self.post(self._build_url(f"/data-platform/lakehouse/{dataset_id}/tier"), data={"tier": tier, "records": records, "format": fmt})

    async def dp_get_freshness(self, dataset_id: str) -> dict:
        return await self.get(self._build_url(f"/data-platform/freshness/{dataset_id}"))

    async def dp_update_freshness(self, dataset_id: str, expected_interval_hours: int = 24) -> dict:
        return await self.post(self._build_url(f"/data-platform/freshness/{dataset_id}"), data={"expected_interval_hours": expected_interval_hours})

    async def dp_check_drift(self, dataset_id: str, current_schema: list, previous_schema: list | None = None) -> dict:
        return await self.post(self._build_url(f"/data-platform/drift/{dataset_id}/check"), data={"current_schema": current_schema, "previous_schema": previous_schema})

    async def dp_create_product(self, name: str, owner: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "owner": owner}
        for k in ("description", "contract", "classification", "domain", "slo", "status"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/data-products"), data=payload)

    async def dp_list_products(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/data-platform/data-products"), params={"limit": limit})

    async def dp_create_domain(self, name: str, owner: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"name": name, "owner": owner}
        for k in ("description",):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/data-platform/data-domains"), data=payload)

    async def dp_reconcile(self, source_count: int, processed_count: int, output_count: int) -> dict:
        return await self.post(self._build_url("/data-platform/reconciliation"), data={"source_count": source_count, "processed_count": processed_count, "output_count": output_count})

    async def dp_replay(self, topic: str, scope: dict | None = None) -> dict:
        return await self.post(self._build_url("/data-platform/replay"), data={"topic": topic, "scope": scope or {}})

    async def dp_export(self, dataset_id: str, purpose: str = "analysis", destination: str = "s3") -> dict:
        return await self.post(self._build_url("/data-platform/exports"), data={"dataset_id": dataset_id, "purpose": purpose, "destination": destination})

    async def dp_get_anomalies(self, limit: int = 20) -> dict:
        return await self.get(self._build_url("/data-platform/access-anomalies"), params={"limit": limit})
