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
