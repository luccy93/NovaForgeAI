"""Volume 62 — Multi-Region package (global control plane + regional data plane)."""

from app.regions.registry import RegionService, region_service
from app.regions.placement import PlacementService, placement_service
from app.regions.routing import RoutingService, routing_service
from app.regions.replication import ReplicationService, replication_service
from app.regions.config import GlobalConfigService, global_config_service
from app.regions.failover import FailoverService, failover_service

__all__ = [
    "RegionService", "region_service",
    "PlacementService", "placement_service",
    "RoutingService", "routing_service",
    "ReplicationService", "replication_service",
    "GlobalConfigService", "global_config_service",
    "FailoverService", "failover_service",
]
