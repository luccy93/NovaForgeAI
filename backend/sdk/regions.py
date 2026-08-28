"""Multi-Region SDK mixin — Volume 62 Commit 1.

Exposes regions, placement, routing, failover, replication, health. Additive,
tenant isolation enforced server-side. No placeholders.
"""

from typing import Any, Dict, Optional


class RegionsMixin:
    """Synchronous Multi-Region mixin."""

    def region_register(self, region_id: str, name: str, provider: str, location: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"region_id": region_id, "name": name, "provider": provider, "location": location}
        for k in ("environment", "data_residency", "capacity", "status", "capabilities"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/regions/regions"), data=payload)

    def region_list(self, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        return self.get(self._build_url("/regions/regions"), params=params or None)

    def region_get(self, region_id: str) -> dict:
        return self.get(self._build_url(f"/regions/regions/{region_id}"))

    def region_status(self, region_id: str, status: str, reason: Optional[str] = None) -> dict:
        return self.patch(self._build_url(f"/regions/regions/{region_id}/status"), data={"status": status, "reason": reason})

    def region_capabilities_set(self, region_id: str, capabilities: dict) -> dict:
        return self.post(self._build_url(f"/regions/regions/{region_id}/capabilities"), data={"capabilities": capabilities})

    def region_capabilities(self, region_id: str) -> dict:
        return self.get(self._build_url(f"/regions/regions/{region_id}/capabilities"))

    def region_health(self, region_id: str, status: str, checks: Optional[dict] = None) -> dict:
        return self.post(self._build_url(f"/regions/regions/{region_id}/health"), data={"status": status, "checks": checks or {}})

    def region_health_get(self, region_id: str) -> dict:
        return self.get(self._build_url(f"/regions/regions/{region_id}/health"))

    def region_health_all(self) -> dict:
        return self.get(self._build_url("/regions/regions/health"))

    def region_capacity(self, region_id: str) -> dict:
        return self.get(self._build_url(f"/regions/regions/{region_id}/capacity"))

    def region_drain(self, region_id: str, reason: Optional[str] = None) -> dict:
        return self.post(self._build_url(f"/regions/regions/{region_id}/drain"), data={"reason": reason} if reason else {})

    def region_drain_complete(self, region_id: str) -> dict:
        return self.post(self._build_url(f"/regions/regions/{region_id}/drain/complete"), data={})

    def region_placement_set(self, primary_region: Optional[str] = None, secondary_region: Optional[str] = None,
                             allowed_regions: Optional[list] = None, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {
            "primary_region": primary_region,
            "secondary_region": secondary_region,
            "allowed_regions": allowed_regions or [],
        }
        for k in ("data_classification", "residency_policy", "policy_version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return self.post(self._build_url("/regions/placements"), data=payload)

    def region_placement_get(self, tenant_id: str) -> dict:
        return self.get(self._build_url(f"/regions/placements/{tenant_id}"))

    def region_placement_evaluate(self, tenant_id: str, region: str, data_classification: Optional[str] = None,
                                  provider: Optional[str] = None, capacity: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"region": region, "data_classification": data_classification,
                                   "provider": provider, "capacity": capacity or {}}
        return self.post(self._build_url(f"/regions/placements/{tenant_id}/evaluate"), data=payload)

    def region_route(self, service: str, data_classification: Optional[str] = None, preferred_region: Optional[str] = None,
                     criticality: str = "HIGH", capacity_aware: bool = True) -> dict:
        payload: Dict[str, Any] = {"service": service, "data_classification": data_classification,
                                   "preferred_region": preferred_region, "criticality": criticality, "capacity_aware": capacity_aware}
        return self.post(self._build_url("/regions/routing/resolve"), data=payload)

    def region_routing_policy(self, service: str, primary_region: Optional[str] = None, preferred_secondary: Optional[str] = None,
                              emergency_fallback: Optional[str] = None, consistency: str = "CONFIGURABLE", metadata: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"service": service, "primary_region": primary_region,
                                   "preferred_secondary": preferred_secondary, "emergency_fallback": emergency_fallback,
                                   "consistency": consistency, "metadata": metadata or {}}
        return self.post(self._build_url("/regions/routing-policies"), data=payload)

    def region_config_publish(self, service: str, primary_region: Optional[str] = None, preferred_secondary: Optional[str] = None,
                              emergency_fallback: Optional[str] = None, consistency: str = "CONFIGURABLE", region_overrides: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"service": service, "primary_region": primary_region,
                                   "preferred_secondary": preferred_secondary, "emergency_fallback": emergency_fallback,
                                   "consistency": consistency, "metadata": region_overrides or {}}
        return self.post(self._build_url("/regions/config"), data=payload)

    def region_config_list(self, tenant: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if tenant is not None:
            params["tenant"] = tenant
        return self.get(self._build_url("/regions/config"), params=params or None)

    def region_slo(self, region_id: str) -> dict:
        return self.get(self._build_url(f"/regions/regions/{region_id}/slo"))

    def region_replication_record(self, source_region: str, dest_region: str, resource: str, resource_type: Optional[str] = None,
                                  tenant: str = "", lag_seconds: float = 0.0, status: str = "HEALTHY") -> dict:
        payload: Dict[str, Any] = {"source_region": source_region, "dest_region": dest_region, "resource": resource,
                                   "resource_type": resource_type, "tenant": tenant, "lag_seconds": lag_seconds, "status": status}
        return self.post(self._build_url("/regions/replication"), data=payload)

    def region_replication_list(self, tenant: Optional[str] = None, source_region: Optional[str] = None, dest_region: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if tenant is not None:
            params["tenant"] = tenant
        if source_region is not None:
            params["source_region"] = source_region
        if dest_region is not None:
            params["dest_region"] = dest_region
        return self.get(self._build_url("/regions/replication"), params=params or None)

    def region_failover(self, source_region: str, target_region: str, service: Optional[str] = None,
                        data_classification: Optional[str] = None, authorized_by: Optional[str] = None, failover_type: str = "failover") -> dict:
        payload: Dict[str, Any] = {"source_region": source_region, "target_region": target_region, "service": service,
                                   "data_classification": data_classification, "authorized_by": authorized_by, "failover_type": failover_type}
        return self.post(self._build_url("/regions/failover"), data=payload)

    def region_failover_complete(self, record_id: int, health_verified: Optional[bool] = None) -> dict:
        payload: Dict[str, Any] = {}
        if health_verified is not None:
            payload["health_verified"] = health_verified
        return self.post(self._build_url(f"/regions/failover/{record_id}/complete"), data=payload)

    def region_failover_fail(self, record_id: int, reason: Optional[str] = None) -> dict:
        payload: Dict[str, Any] = {}
        if reason is not None:
            payload["reason"] = reason
        return self.post(self._build_url(f"/regions/failover/{record_id}/fail"), data=payload)

    def region_failback(self, source_region: str, target_region: str, service: Optional[str] = None,
                        data_classification: Optional[str] = None, authorized_by: Optional[str] = None) -> dict:
        return self.region_failover(source_region, target_region, service=service, data_classification=data_classification,
                                    authorized_by=authorized_by, failover_type="failback")


class AsyncRegionsMixin:
    """Async Multi-Region mixin — mirrors RegionsMixin with await."""

    async def region_register(self, region_id: str, name: str, provider: str, location: str, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"region_id": region_id, "name": name, "provider": provider, "location": location}
        for k in ("environment", "data_residency", "capacity", "status", "capabilities"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/regions/regions"), data=payload)

    async def region_list(self, status: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if status is not None:
            params["status"] = status
        return await self.get(self._build_url("/regions/regions"), params=params or None)

    async def region_get(self, region_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/regions/{region_id}"))

    async def region_status(self, region_id: str, status: str, reason: Optional[str] = None) -> dict:
        return await self.patch(self._build_url(f"/regions/regions/{region_id}/status"), data={"status": status, "reason": reason})

    async def region_capabilities_set(self, region_id: str, capabilities: dict) -> dict:
        return await self.post(self._build_url(f"/regions/regions/{region_id}/capabilities"), data={"capabilities": capabilities})

    async def region_capabilities(self, region_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/regions/{region_id}/capabilities"))

    async def region_health(self, region_id: str, status: str, checks: Optional[dict] = None) -> dict:
        return await self.post(self._build_url(f"/regions/regions/{region_id}/health"), data={"status": status, "checks": checks or {}})

    async def region_health_get(self, region_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/regions/{region_id}/health"))

    async def region_health_all(self) -> dict:
        return await self.get(self._build_url("/regions/regions/health"))

    async def region_capacity(self, region_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/regions/{region_id}/capacity"))

    async def region_drain(self, region_id: str, reason: Optional[str] = None) -> dict:
        body = {"reason": reason} if reason else {}
        return await self.post(self._build_url(f"/regions/regions/{region_id}/drain"), data=body)

    async def region_drain_complete(self, region_id: str) -> dict:
        return await self.post(self._build_url(f"/regions/regions/{region_id}/drain/complete"), data={})

    async def region_placement_set(self, primary_region: Optional[str] = None, secondary_region: Optional[str] = None,
                                   allowed_regions: Optional[list] = None, **kwargs: Any) -> dict:
        payload: Dict[str, Any] = {"primary_region": primary_region, "secondary_region": secondary_region, "allowed_regions": allowed_regions or []}
        for k in ("data_classification", "residency_policy", "policy_version"):
            if k in kwargs and kwargs[k] is not None:
                payload[k] = kwargs[k]
        return await self.post(self._build_url("/regions/placements"), data=payload)

    async def region_placement_get(self, tenant_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/placements/{tenant_id}"))

    async def region_placement_evaluate(self, tenant_id: str, region: str, data_classification: Optional[str] = None,
                                        provider: Optional[str] = None, capacity: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"region": region, "data_classification": data_classification, "provider": provider, "capacity": capacity or {}}
        return await self.post(self._build_url(f"/regions/placements/{tenant_id}/evaluate"), data=payload)

    async def region_route(self, service: str, data_classification: Optional[str] = None, preferred_region: Optional[str] = None,
                           criticality: str = "HIGH", capacity_aware: bool = True) -> dict:
        payload: Dict[str, Any] = {"service": service, "data_classification": data_classification,
                                   "preferred_region": preferred_region, "criticality": criticality, "capacity_aware": capacity_aware}
        return await self.post(self._build_url("/regions/routing/resolve"), data=payload)

    async def region_routing_policy(self, service: str, primary_region: Optional[str] = None, preferred_secondary: Optional[str] = None,
                                    emergency_fallback: Optional[str] = None, consistency: str = "CONFIGURABLE", metadata: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"service": service, "primary_region": primary_region, "preferred_secondary": preferred_secondary,
                                   "emergency_fallback": emergency_fallback, "consistency": consistency, "metadata": metadata or {}}
        return await self.post(self._build_url("/regions/routing-policies"), data=payload)

    async def region_config_publish(self, service: str, primary_region: Optional[str] = None, preferred_secondary: Optional[str] = None,
                                    emergency_fallback: Optional[str] = None, consistency: str = "CONFIGURABLE", region_overrides: Optional[dict] = None) -> dict:
        payload: Dict[str, Any] = {"service": service, "primary_region": primary_region, "preferred_secondary": preferred_secondary,
                                   "emergency_fallback": emergency_fallback, "consistency": consistency, "metadata": region_overrides or {}}
        return await self.post(self._build_url("/regions/config"), data=payload)

    async def region_config_list(self, tenant: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if tenant is not None:
            params["tenant"] = tenant
        return await self.get(self._build_url("/regions/config"), params=params or None)

    async def region_slo(self, region_id: str) -> dict:
        return await self.get(self._build_url(f"/regions/regions/{region_id}/slo"))

    async def region_replication_record(self, source_region: str, dest_region: str, resource: str, resource_type: Optional[str] = None,
                                        tenant: str = "", lag_seconds: float = 0.0, status: str = "HEALTHY") -> dict:
        payload: Dict[str, Any] = {"source_region": source_region, "dest_region": dest_region, "resource": resource,
                                   "resource_type": resource_type, "tenant": tenant, "lag_seconds": lag_seconds, "status": status}
        return await self.post(self._build_url("/regions/replication"), data=payload)

    async def region_replication_list(self, tenant: Optional[str] = None, source_region: Optional[str] = None, dest_region: Optional[str] = None) -> dict:
        params: Dict[str, Any] = {}
        if tenant is not None:
            params["tenant"] = tenant
        if source_region is not None:
            params["source_region"] = source_region
        if dest_region is not None:
            params["dest_region"] = dest_region
        return await self.get(self._build_url("/regions/replication"), params=params or None)

    async def region_failover(self, source_region: str, target_region: str, service: Optional[str] = None,
                              data_classification: Optional[str] = None, authorized_by: Optional[str] = None, failover_type: str = "failover") -> dict:
        payload: Dict[str, Any] = {"source_region": source_region, "target_region": target_region, "service": service,
                                   "data_classification": data_classification, "authorized_by": authorized_by, "failover_type": failover_type}
        return await self.post(self._build_url("/regions/failover"), data=payload)

    async def region_failover_complete(self, record_id: int, health_verified: Optional[bool] = None) -> dict:
        payload: Dict[str, Any] = {}
        if health_verified is not None:
            payload["health_verified"] = health_verified
        return await self.post(self._build_url(f"/regions/failover/{record_id}/complete"), data=payload)

    async def region_failover_fail(self, record_id: int, reason: Optional[str] = None) -> dict:
        body = {"reason": reason} if reason else {}
        return await self.post(self._build_url(f"/regions/failover/{record_id}/fail"), data=body)

    async def region_failback(self, source_region: str, target_region: str, service: Optional[str] = None,
                              data_classification: Optional[str] = None, authorized_by: Optional[str] = None) -> dict:
        return await self.region_failover(source_region, target_region, service=service, data_classification=data_classification,
                                          authorized_by=authorized_by, failover_type="failback")
