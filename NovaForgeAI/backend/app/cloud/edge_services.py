"""
Edge Services — Global CDN, Edge API, Regional Cache, Regional Search, Regional AI Inference, Global Router.
"""
import logging
logger = logging.getLogger(__name__)

from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
import json, uuid, hashlib, time, os, threading
from collections import defaultdict


class Region(Enum):
    US_EAST = "us_east"
    US_WEST = "us_west"
    EU_WEST = "eu_west"
    EU_CENTRAL = "eu_central"
    ASIA_EAST = "asia_east"
    ASIA_SOUTH = "asia_south"
    AUSTRALIA = "australia"
    SOUTH_AMERICA = "south_america"
    MIDDLE_EAST = "middle_east"
    AFRICA = "africa"


class CacheStrategy(Enum):
    LRU = "lru"
    LFU = "lfu"
    TTL = "ttl"
    FIFO = "fifo"
    ADAPTIVE = "adaptive"


class RoutingStrategy(Enum):
    LATENCY_BASED = "latency_based"
    ROUND_ROBIN = "round_robin"
    GEOGRAPHIC = "geographic"
    WEIGHTED = "weighted"
    HEALTH_BASED = "health_based"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    key: str
    value: Any = None
    region: Region = Region.US_EAST
    size_bytes: int = 0
    created_at: str = ""
    expires_at: str = ""
    access_count: int = 0
    last_accessed: str = ""
    ttl_seconds: int = 3600

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = self.region.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "CacheEntry":
        data = dict(data)
        data["region"] = Region(data["region"])
        return CacheEntry(**data)


@dataclass
class CacheMetrics:
    region: Region
    total_entries: int = 0
    total_size_bytes: int = 0
    hit_count: int = 0
    miss_count: int = 0
    hit_ratio: float = 0.0
    eviction_count: int = 0
    avg_access_time_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = self.region.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "CacheMetrics":
        data = dict(data)
        data["region"] = Region(data["region"])
        return CacheMetrics(**data)


@dataclass
class EdgeEndpoint:
    id: str
    region: Region
    url: str
    status: str = "active"
    uptime_percent: float = 100.0
    latency_ms: float = 0.0
    capacity: float = 1000.0
    current_load: float = 0.0
    version: str = "1.0.0"
    last_health_check: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = self.region.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "EdgeEndpoint":
        data = dict(data)
        data["region"] = Region(data["region"])
        return EdgeEndpoint(**data)


@dataclass
class CachedResponse:
    key: str
    data: dict = field(default_factory=dict)
    region: Region = Region.US_EAST
    cached_at: str = ""
    ttl_seconds: int = 3600
    compressed: bool = False
    content_type: str = "application/json"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = self.region.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "CachedResponse":
        data = dict(data)
        data["region"] = Region(data["region"])
        return CachedResponse(**data)


@dataclass
class RegionalCluster:
    region: Region
    endpoints: list[EdgeEndpoint] = field(default_factory=list)
    config: dict = field(default_factory=dict)
    created_at: str = ""
    last_scaled: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["region"] = self.region.value
        d["endpoints"] = [e.to_dict() for e in self.endpoints]
        return d

    @staticmethod
    def from_dict(data: dict) -> "RegionalCluster":
        data = dict(data)
        data["region"] = Region(data["region"])
        data["endpoints"] = [EdgeEndpoint.from_dict(e) for e in data.get("endpoints", [])]
        return RegionalCluster(**data)


@dataclass
class GlobalRoute:
    source_region: Region
    target_region: Region
    priority: int = 5
    strategy: RoutingStrategy = RoutingStrategy.LATENCY_BASED
    active: bool = True
    latency_offset_ms: float = 0.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["source_region"] = self.source_region.value
        d["target_region"] = self.target_region.value
        d["strategy"] = self.strategy.value
        return d

    @staticmethod
    def from_dict(data: dict) -> "GlobalRoute":
        data = dict(data)
        data["source_region"] = Region(data["source_region"])
        data["target_region"] = Region(data["target_region"])
        data["strategy"] = RoutingStrategy(data["strategy"])
        return GlobalRoute(**data)


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

class GlobalCDN:
    """Manages global CDN caching with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._cache_file = os.path.join(storage_dir, "cdn_cache.json")
        self._cache: dict[str, CacheEntry] = {}
        self._metrics_file = os.path.join(storage_dir, "cdn_metrics.json")
        self._metrics: dict[str, CacheMetrics] = {}
        self._strategy_file = os.path.join(storage_dir, "cdn_strategy.json")
        self._strategy: dict[str, str] = defaultdict(lambda: CacheStrategy.LRU.value)
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._cache = {k: CacheEntry.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d CDN cache entries", len(self._cache))
        except Exception:
            logger.exception("Failed to load CDN cache; starting fresh")
            self._cache = {}

        try:
            if os.path.exists(self._metrics_file):
                with open(self._metrics_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._metrics = {k: CacheMetrics.from_dict(v) for k, v in data.items()}
        except Exception:
            self._metrics = {}

        try:
            if os.path.exists(self._strategy_file):
                with open(self._strategy_file, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                    self._strategy = defaultdict(lambda: CacheStrategy.LRU.value, stored)
        except Exception:
            self._strategy = defaultdict(lambda: CacheStrategy.LRU.value)

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._cache.items()}
            tmp = self._cache_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._cache_file)
        except Exception:
            logger.exception("Failed to save CDN cache")

        try:
            data = {k: v.to_dict() for k, v in self._metrics.items()}
            tmp = self._metrics_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file)
        except Exception:
            logger.exception("Failed to save CDN metrics")

        try:
            tmp = self._strategy_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._strategy), fh, indent=2, default=str)
            os.replace(tmp, self._strategy_file)
        except Exception:
            logger.exception("Failed to save CDN strategy")

    # -- core operations ----------------------------------------------------

    def cache_response(self, key: str, value: Any, region: Region = Region.US_EAST,
                       ttl_seconds: int = 3600, content_type: str = "application/json",
                       compressed: bool = False) -> CacheEntry:
        try:
            now = datetime.now(timezone.utc).isoformat()
            expires = datetime.fromtimestamp(
                datetime.now(timezone.utc).timestamp() + ttl_seconds
            ).isoformat()
            serialized = json.dumps(value, default=str)
            entry = CacheEntry(
                key=key,
                value=value,
                region=region,
                size_bytes=len(serialized.encode("utf-8")),
                created_at=now,
                expires_at=expires,
                access_count=0,
                last_accessed=now,
                ttl_seconds=ttl_seconds,
            )
            with self._lock:
                self._cache[key] = entry
            self._save()
            self.telemetry["responses_cached"] += 1
            logger.debug("Cached response %s in %s", key, region.value)
            return entry
        except Exception:
            logger.exception("Failed to cache response %s", key)
            raise

    def get_cached(self, key: str) -> Optional[CacheEntry]:
        try:
            entry = self._cache.get(key)
            if entry is None:
                self._record_miss(key)
                return None
            now = datetime.now(timezone.utc)
            if entry.expires_at:
                try:
                    expires = datetime.fromisoformat(entry.expires_at)
                    if now > expires:
                        with self._lock:
                            self._cache.pop(key, None)
                        self._save()
                        self._record_miss(key)
                        self.telemetry["cache_expired"] += 1
                        return None
                except (ValueError, TypeError):
                    pass
            entry.access_count += 1
            entry.last_accessed = now.isoformat()
            self._cache[key] = entry
            self._record_hit(entry.region)
            self.telemetry["cache_hits"] += 1
            return entry
        except Exception:
            logger.exception("Failed to get cached %s", key)
            return None

    def invalidate_cache(self, key: str) -> bool:
        try:
            with self._lock:
                if key in self._cache:
                    del self._cache[key]
                    self._save()
                    self.telemetry["cache_invalidations"] += 1
                    logger.info("Invalidated cache key %s", key)
                    return True
            return False
        except Exception:
            logger.exception("Failed to invalidate cache %s", key)
            return False

    def purge_region(self, region: Region) -> int:
        try:
            keys = [k for k, v in self._cache.items() if v.region == region]
            with self._lock:
                for k in keys:
                    del self._cache[k]
            self._save()
            self.telemetry["regions_purged"] += 1
            logger.info("Purged %d entries from region %s", len(keys), region.value)
            return len(keys)
        except Exception:
            logger.exception("Failed to purge region %s", region.value)
            return 0

    def purge_all(self) -> int:
        try:
            count = len(self._cache)
            with self._lock:
                self._cache.clear()
            self._save()
            self.telemetry["cache_purged_all"] += 1
            logger.info("Purged entire CDN cache (%d entries)", count)
            return count
        except Exception:
            logger.exception("Failed to purge all cache")
            return 0

    def get_cache_metrics(self, region: Optional[Region] = None) -> list[CacheMetrics]:
        try:
            if region:
                m = self._metrics.get(region.value)
                return [m] if m else []
            return list(self._metrics.values())
        except Exception:
            logger.exception("Failed to get cache metrics")
            raise

    def set_cache_strategy(self, region: Region, strategy: CacheStrategy) -> None:
        try:
            self._strategy[region.value] = strategy.value
            self._save()
            self.telemetry["cache_strategies_set"] += 1
            logger.info("Set cache strategy for %s to %s", region.value, strategy.value)
        except Exception:
            logger.exception("Failed to set cache strategy")
            raise

    def warmup_cache(self, keys: list[str], base_region: Region = Region.US_EAST) -> int:
        try:
            warmed = 0
            for key in keys:
                if key not in self._cache:
                    self.cache_response(key, {"warmup": True, "key": key}, base_region, ttl_seconds=7200)
                    warmed += 1
            self.telemetry["cache_warmed"] += warmed
            logger.info("Warmed %d cache entries", warmed)
            return warmed
        except Exception:
            logger.exception("Failed to warmup cache")
            raise

    def get_cache_hit_ratio(self, region: Optional[Region] = None) -> dict:
        try:
            if region:
                metrics_list = [self._metrics.get(region.value)]
            else:
                metrics_list = list(self._metrics.values())
            total_hits = sum(m.hit_count for m in metrics_list if m)
            total_misses = sum(m.miss_count for m in metrics_list if m)
            total = total_hits + total_misses
            return {
                "total_hits": total_hits,
                "total_misses": total_misses,
                "hit_ratio": round((total_hits / total * 100), 2) if total > 0 else 0.0,
            }
        except Exception:
            logger.exception("Failed to get cache hit ratio")
            raise

    # -- internal helpers ---------------------------------------------------

    def _record_hit(self, region: Region) -> None:
        key = region.value
        if key not in self._metrics:
            self._metrics[key] = CacheMetrics(region=region)
        m = self._metrics[key]
        m.hit_count += 1
        total = m.hit_count + m.miss_count
        m.hit_ratio = round((m.hit_count / total * 100), 2) if total > 0 else 0.0

    def _record_miss(self, key: str) -> None:
        entry = self._cache.get(key)
        region = entry.region if entry else Region.US_EAST
        rkey = region.value
        if rkey not in self._metrics:
            self._metrics[rkey] = CacheMetrics(region=region)
        m = self._metrics[rkey]
        m.miss_count += 1
        total = m.hit_count + m.miss_count
        m.hit_ratio = round((m.hit_count / total * 100), 2) if total > 0 else 0.0


class EdgeAPI:
    """Manages edge API endpoints with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._endpoints_file = os.path.join(storage_dir, "edge_endpoints.json")
        self._endpoints: dict[str, EdgeEndpoint] = {}
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._endpoints_file):
                with open(self._endpoints_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._endpoints = {k: EdgeEndpoint.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d edge endpoints", len(self._endpoints))
        except Exception:
            logger.exception("Failed to load edge endpoints; starting fresh")
            self._endpoints = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._endpoints.items()}
            tmp = self._endpoints_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._endpoints_file)
        except Exception:
            logger.exception("Failed to save edge endpoints")

    # -- CRUD ---------------------------------------------------------------

    def register_endpoint(self, region: Region, url: str, capacity: float = 1000.0,
                          version: str = "1.0.0") -> EdgeEndpoint:
        try:
            now = datetime.now(timezone.utc).isoformat()
            endpoint = EdgeEndpoint(
                id=str(uuid.uuid4()),
                region=region,
                url=url,
                status="active",
                uptime_percent=100.0,
                latency_ms=0.0,
                capacity=capacity,
                current_load=0.0,
                version=version,
                last_health_check=now,
            )
            self._endpoints[endpoint.id] = endpoint
            self._save()
            self.telemetry["endpoints_registered"] += 1
            logger.info("Registered endpoint %s at %s (%s)", endpoint.id, url, region.value)
            return endpoint
        except Exception:
            logger.exception("Failed to register endpoint")
            raise

    def unregister_endpoint(self, endpoint_id: str) -> None:
        try:
            if endpoint_id not in self._endpoints:
                raise ValueError(f"Endpoint not found: {endpoint_id}")
            del self._endpoints[endpoint_id]
            self._save()
            self.telemetry["endpoints_unregistered"] += 1
            logger.info("Unregistered endpoint %s", endpoint_id)
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to unregister endpoint")
            raise

    def get_endpoint(self, endpoint_id: str) -> EdgeEndpoint:
        ep = self._endpoints.get(endpoint_id)
        if ep is None:
            raise ValueError(f"Endpoint not found: {endpoint_id}")
        self.telemetry["endpoints_read"] += 1
        return ep

    def route_request(self, source_region: Region, target_region: Region) -> Optional[EdgeEndpoint]:
        try:
            candidates = [
                e for e in self._endpoints.values()
                if e.region == target_region and e.status == "active"
            ]
            if not candidates:
                logger.warning("No active endpoints in region %s", target_region.value)
                return None
            candidates.sort(key=lambda x: x.current_load)
            chosen = candidates[0]
            chosen.current_load = min(chosen.capacity, chosen.current_load + 1)
            self._endpoints[chosen.id] = chosen
            self._save()
            self.telemetry["requests_routed"] += 1
            return chosen
        except Exception:
            logger.exception("Failed to route request")
            raise

    def get_endpoint_health(self, endpoint_id: str) -> dict:
        try:
            ep = self.get_endpoint(endpoint_id)
            now = datetime.now(timezone.utc).isoformat()
            health = {
                "endpoint_id": ep.id,
                "region": ep.region.value,
                "url": ep.url,
                "status": ep.status,
                "uptime_percent": ep.uptime_percent,
                "latency_ms": ep.latency_ms,
                "load_pct": round((ep.current_load / ep.capacity * 100), 2) if ep.capacity > 0 else 0.0,
                "last_health_check": ep.last_health_check,
                "checked_at": now,
            }
            self.telemetry["health_checks"] += 1
            return health
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to get endpoint health")
            raise

    def get_region_latency(self, region: Region) -> float:
        try:
            region_eps = [e for e in self._endpoints.values() if e.region == region]
            if not region_eps:
                return 999.9
            avg_latency = sum(e.latency_ms for e in region_eps) / len(region_eps)
            return round(avg_latency, 2)
        except Exception:
            return 999.9

    def failover_endpoint(self, endpoint_id: str) -> Optional[EdgeEndpoint]:
        try:
            ep = self.get_endpoint(endpoint_id)
            ep.status = "failover"
            ep.uptime_percent = 0.0
            self._endpoints[endpoint_id] = ep
            failover = self.route_request(ep.region, ep.region)
            self._save()
            self.telemetry["failovers"] += 1
            logger.info("Failover for endpoint %s to %s", endpoint_id, failover.id if failover else "none")
            return failover
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to failover endpoint")
            raise


class RegionalCache:
    """Manages regional cache with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._cache_dir = os.path.join(storage_dir, "regional_cache")
        self._stores: dict[str, dict[str, CachedResponse]] = defaultdict(dict)
        self._metrics: dict[str, CacheMetrics] = {}
        self._strategies: dict[str, str] = defaultdict(lambda: CacheStrategy.LRU.value)
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self._cache_dir, exist_ok=True)
        self._load()

    def _region_file(self, region: Region) -> str:
        return os.path.join(self._cache_dir, f"cache_{region.value}.json")

    def _metrics_file(self) -> str:
        return os.path.join(self._cache_dir, "regional_cache_metrics.json")

    def _strategy_file(self) -> str:
        return os.path.join(self._cache_dir, "regional_cache_strategies.json")

    def _load(self) -> None:
        try:
            if os.path.exists(self._metrics_file()):
                with open(self._metrics_file(), "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._metrics = {k: CacheMetrics.from_dict(v) for k, v in data.items()}
        except Exception:
            self._metrics = {}

        try:
            if os.path.exists(self._strategy_file()):
                with open(self._strategy_file(), "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                    self._strategies = defaultdict(lambda: CacheStrategy.LRU.value, stored)
        except Exception:
            self._strategies = defaultdict(lambda: CacheStrategy.LRU.value)

        for region in Region:
            rfile = self._region_file(region)
            try:
                if os.path.exists(rfile):
                    with open(rfile, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    self._stores[region.value] = {k: CachedResponse.from_dict(v) for k, v in data.items()}
            except Exception:
                logger.warning("Failed to load regional cache for %s", region.value)
                self._stores[region.value] = {}

        logger.info("Loaded regional caches for %d regions", len(self._stores))

    def _save(self) -> None:
        for region_val, store in self._stores.items():
            try:
                rfile = os.path.join(self._cache_dir, f"cache_{region_val}.json")
                data = {k: v.to_dict() for k, v in store.items()}
                tmp = rfile + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, indent=2, default=str)
                os.replace(tmp, rfile)
            except Exception:
                logger.exception("Failed to save regional cache for %s", region_val)

        try:
            data = {k: v.to_dict() for k, v in self._metrics.items()}
            tmp = self._metrics_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file())
        except Exception:
            logger.exception("Failed to save regional cache metrics")

        try:
            tmp = self._strategy_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._strategies), fh, indent=2, default=str)
            os.replace(tmp, self._strategy_file())
        except Exception:
            logger.exception("Failed to save regional cache strategies")

    # -- core operations ----------------------------------------------------

    def put(self, region: Region, key: str, data: dict,
            ttl_seconds: int = 3600, compressed: bool = False,
            content_type: str = "application/json") -> CachedResponse:
        try:
            now = datetime.now(timezone.utc).isoformat()
            resp = CachedResponse(
                key=key,
                data=data,
                region=region,
                cached_at=now,
                ttl_seconds=ttl_seconds,
                compressed=compressed,
                content_type=content_type,
            )
            with self._lock:
                self._stores[region.value][key] = resp
            self._save()
            self.telemetry["regional_cache_puts"] += 1
            logger.debug("Regional cache PUT %s in %s", key, region.value)
            return resp
        except Exception:
            logger.exception("Failed to put regional cache %s", key)
            raise

    def get(self, region: Region, key: str) -> Optional[CachedResponse]:
        try:
            store = self._stores.get(region.value, {})
            resp = store.get(key)
            if resp is None:
                self._record_miss(region)
                return None
            now = datetime.now(timezone.utc)
            cached = datetime.fromisoformat(resp.cached_at)
            elapsed = (now - cached).total_seconds()
            if elapsed > resp.ttl_seconds:
                with self._lock:
                    self._stores[region.value].pop(key, None)
                self._save()
                self._record_miss(region)
                self.telemetry["regional_cache_expired"] += 1
                return None
            self._record_hit(region)
            self.telemetry["regional_cache_hits"] += 1
            return resp
        except Exception:
            logger.exception("Failed to get regional cache %s", key)
            return None

    def delete(self, region: Region, key: str) -> bool:
        try:
            with self._lock:
                store = self._stores.get(region.value, {})
                if key in store:
                    del store[key]
                    self._save()
                    self.telemetry["regional_cache_deletes"] += 1
                    return True
            return False
        except Exception:
            logger.exception("Failed to delete regional cache %s", key)
            return False

    def clear_region(self, region: Region) -> int:
        try:
            with self._lock:
                store = self._stores.get(region.value, {})
                count = len(store)
                store.clear()
            self._save()
            self.telemetry["regional_cache_cleared"] += 1
            logger.info("Cleared regional cache for %s (%d entries)", region.value, count)
            return count
        except Exception:
            logger.exception("Failed to clear region %s", region.value)
            return 0

    def get_region_metrics(self, region: Region) -> Optional[CacheMetrics]:
        return self._metrics.get(region.value)

    def get_regional_hit_ratio(self, region: Region) -> dict:
        try:
            m = self._metrics.get(region.value)
            if m is None:
                return {"region": region.value, "hit_ratio": 0.0, "hits": 0, "misses": 0}
            total = m.hit_count + m.miss_count
            return {
                "region": region.value,
                "hit_ratio": round((m.hit_count / total * 100), 2) if total > 0 else 0.0,
                "hits": m.hit_count,
                "misses": m.miss_count,
            }
        except Exception:
            logger.exception("Failed to get regional hit ratio")
            raise

    def set_region_strategy(self, region: Region, strategy: CacheStrategy) -> None:
        try:
            self._strategies[region.value] = strategy.value
            self._save()
            self.telemetry["regional_strategies_set"] += 1
        except Exception:
            logger.exception("Failed to set region strategy")
            raise

    # -- internal helpers ---------------------------------------------------

    def _record_hit(self, region: Region) -> None:
        key = region.value
        if key not in self._metrics:
            self._metrics[key] = CacheMetrics(region=region)
        m = self._metrics[key]
        m.hit_count += 1
        total = m.hit_count + m.miss_count
        m.hit_ratio = round((m.hit_count / total * 100), 2) if total > 0 else 0.0

    def _record_miss(self, region: Region) -> None:
        key = region.value
        if key not in self._metrics:
            self._metrics[key] = CacheMetrics(region=region)
        m = self._metrics[key]
        m.miss_count += 1
        total = m.hit_count + m.miss_count
        m.hit_ratio = round((m.hit_count / total * 100), 2) if total > 0 else 0.0


class RegionalSearch:
    """Manages regional search indices with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._search_dir = os.path.join(storage_dir, "regional_search")
        self._indices: dict[str, dict[str, dict]] = defaultdict(dict)
        self._metrics: dict[str, dict] = defaultdict(lambda: {"indexed": 0, "searches": 0, "avg_latency_ms": 0.0})
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self._search_dir, exist_ok=True)
        self._load()

    def _index_file(self, region: Region) -> str:
        return os.path.join(self._search_dir, f"index_{region.value}.json")

    def _metrics_file(self) -> str:
        return os.path.join(self._search_dir, "search_metrics.json")

    def _load(self) -> None:
        for region in Region:
            ifile = self._index_file(region)
            try:
                if os.path.exists(ifile):
                    with open(ifile, "r", encoding="utf-8") as fh:
                        data = json.load(fh)
                    self._indices[region.value] = data
            except Exception:
                self._indices[region.value] = {}

        try:
            if os.path.exists(self._metrics_file()):
                with open(self._metrics_file(), "r", encoding="utf-8") as fh:
                    self._metrics = defaultdict(lambda: {"indexed": 0, "searches": 0, "avg_latency_ms": 0.0}, json.load(fh))
        except Exception:
            pass

        logger.info("Loaded search indices for %d regions", len(self._indices))

    def _save(self) -> None:
        for region_val, index in self._indices.items():
            try:
                ifile = self._index_file(Region(region_val))
                tmp = ifile + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump(index, fh, indent=2, default=str)
                os.replace(tmp, ifile)
            except Exception:
                logger.exception("Failed to save search index for %s", region_val)

        try:
            tmp = self._metrics_file() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._metrics), fh, indent=2, default=str)
            os.replace(tmp, self._metrics_file())
        except Exception:
            logger.exception("Failed to save search metrics")

    # -- core operations ----------------------------------------------------

    def search_region(self, region: Region, query: str, max_results: int = 10) -> list[dict]:
        try:
            index = self._indices.get(region.value, {})
            q = query.lower()
            start = time.time()
            results = []
            for doc_id, doc in index.items():
                if q in doc_id.lower() or any(q in str(v).lower() for v in doc.values()):
                    results.append({"id": doc_id, **doc})
                    if len(results) >= max_results:
                        break
            elapsed = (time.time() - start) * 1000
            m = self._metrics[region.value]
            m["searches"] += 1
            total = m["searches"]
            m["avg_latency_ms"] = round(
                (m["avg_latency_ms"] * (total - 1) + elapsed) / total, 2
            )
            self._save()
            self.telemetry["searches_performed"] += 1
            logger.debug("Searched region %s for '%s' (%d results in %.1fms)", region.value, query, len(results), elapsed)
            return results
        except Exception:
            logger.exception("Failed to search region %s", region.value)
            raise

    def index_document(self, region: Region, doc_id: str, content: dict) -> dict:
        try:
            with self._lock:
                self._indices[region.value][doc_id] = content
            m = self._metrics[region.value]
            m["indexed"] += 1
            self._save()
            self.telemetry["documents_indexed"] += 1
            logger.info("Indexed document %s in %s", doc_id, region.value)
            return {"doc_id": doc_id, "region": region.value, "status": "indexed"}
        except Exception:
            logger.exception("Failed to index document %s", doc_id)
            raise

    def remove_document(self, region: Region, doc_id: str) -> bool:
        try:
            with self._lock:
                index = self._indices.get(region.value, {})
                if doc_id in index:
                    del index[doc_id]
                    self._save()
                    self.telemetry["documents_removed"] += 1
                    logger.info("Removed document %s from %s", doc_id, region.value)
                    return True
            return False
        except Exception:
            logger.exception("Failed to remove document %s", doc_id)
            return False

    def rebuild_index(self, region: Region) -> int:
        try:
            with self._lock:
                previous = len(self._indices.get(region.value, {}))
                self._indices[region.value] = {}
            self._save()
            self.telemetry["indices_rebuilt"] += 1
            logger.info("Rebuilt search index for %s (removed %d entries)", region.value, previous)
            return previous
        except Exception:
            logger.exception("Failed to rebuild index for %s", region.value)
            return 0

    def get_search_metrics(self, region: Optional[Region] = None) -> dict:
        try:
            if region:
                m = self._metrics.get(region.value, {"indexed": 0, "searches": 0, "avg_latency_ms": 0.0})
                return {"region": region.value, **m}
            result = {}
            for rval, m in self._metrics.items():
                result[rval] = dict(m)
            return result
        except Exception:
            logger.exception("Failed to get search metrics")
            raise


class RegionalAIInference:
    """Manages regional AI inference capabilities with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._capabilities_file = os.path.join(storage_dir, "regional_ai_capabilities.json")
        self._capabilities: dict[str, dict] = {}
        self._latency_file = os.path.join(storage_dir, "regional_ai_latency.json")
        self._latency: dict[str, float] = defaultdict(lambda: 100.0)
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _load(self) -> None:
        try:
            if os.path.exists(self._capabilities_file):
                with open(self._capabilities_file, "r", encoding="utf-8") as fh:
                    self._capabilities = json.load(fh)
        except Exception:
            self._capabilities = {}
        try:
            if os.path.exists(self._latency_file):
                with open(self._latency_file, "r", encoding="utf-8") as fh:
                    stored = json.load(fh)
                    self._latency = defaultdict(lambda: 100.0, stored)
        except Exception:
            self._latency = defaultdict(lambda: 100.0)
        logger.info("Loaded regional AI capabilities for %d regions", len(self._capabilities))

    def _save(self) -> None:
        try:
            tmp = self._capabilities_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._capabilities, fh, indent=2, default=str)
            os.replace(tmp, self._capabilities_file)
        except Exception:
            logger.exception("Failed to save regional AI capabilities")
        try:
            tmp = self._latency_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(dict(self._latency), fh, indent=2, default=str)
            os.replace(tmp, self._latency_file)
        except Exception:
            logger.exception("Failed to save regional AI latency")

    # -- core operations ----------------------------------------------------

    def run_inference(self, region: Region, model: str, input_data: dict) -> dict:
        try:
            caps = self._capabilities.get(region.value, {})
            supported = caps.get("supported_models", [])
            if supported and model not in supported:
                raise ValueError(f"Model '{model}' not supported in region {region.value}")

            start = time.time()
            simulated_latency = self._latency.get(region.value, 100.0) / 1000.0
            time.sleep(min(simulated_latency, 0.1))
            elapsed_ms = (time.time() - start) * 1000

            result = {
                "inference_id": str(uuid.uuid4()),
                "region": region.value,
                "model": model,
                "status": "completed",
                "latency_ms": round(elapsed_ms, 2),
                "output": {"prediction": f"simulated_result_{hashlib.sha256(str(input_data).encode()).hexdigest()[:8]}"},
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["inferences_run"] += 1
            logger.info("Ran inference on %s (model=%s, latency=%.1fms)", region.value, model, elapsed_ms)
            return result
        except ValueError:
            raise
        except Exception:
            logger.exception("Failed to run inference in %s", region.value)
            raise

    def get_capabilities(self, region: Region) -> dict:
        try:
            caps = self._capabilities.get(region.value, {})
            return {"region": region.value, **caps}
        except Exception:
            logger.exception("Failed to get capabilities for %s", region.value)
            raise

    def get_region_latency(self, region: Region) -> float:
        return self._latency.get(region.value, 100.0)

    def optimize_for_region(self, region: Region, config: dict) -> dict:
        try:
            self._capabilities[region.value] = {
                **self._capabilities.get(region.value, {}),
                "optimized_config": config,
                "optimized_at": datetime.now(timezone.utc).isoformat(),
            }
            self._latency[region.value] = config.get("target_latency_ms", self._latency.get(region.value, 100.0))
            self._save()
            self.telemetry["regions_optimized"] += 1
            logger.info("Optimized AI config for region %s", region.value)
            return {"region": region.value, "status": "optimized", "config": config}
        except Exception:
            logger.exception("Failed to optimize region %s", region.value)
            raise


class GlobalRouter:
    """Manages global routing between regions with JSON persistence."""

    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        self._routes_file = os.path.join(storage_dir, "global_routes.json")
        self._routes: dict[str, GlobalRoute] = {}
        self._routing_table_file = os.path.join(storage_dir, "routing_table.json")
        self._routing_table: dict[str, str] = {}
        self._lock = threading.Lock()
        self.telemetry: dict = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        try:
            if os.path.exists(self._routes_file):
                with open(self._routes_file, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                self._routes = {k: GlobalRoute.from_dict(v) for k, v in data.items()}
                logger.info("Loaded %d global routes", len(self._routes))
        except Exception:
            logger.exception("Failed to load global routes; starting fresh")
            self._routes = {}

        try:
            if os.path.exists(self._routing_table_file):
                with open(self._routing_table_file, "r", encoding="utf-8") as fh:
                    self._routing_table = json.load(fh)
        except Exception:
            self._routing_table = {}

    def _save(self) -> None:
        try:
            data = {k: v.to_dict() for k, v in self._routes.items()}
            tmp = self._routes_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2, default=str)
            os.replace(tmp, self._routes_file)
        except Exception:
            logger.exception("Failed to save global routes")

        try:
            tmp = self._routing_table_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._routing_table, fh, indent=2, default=str)
            os.replace(tmp, self._routing_table_file)
        except Exception:
            logger.exception("Failed to save routing table")

    # -- core operations ----------------------------------------------------

    def register_route(self, source_region: Region, target_region: Region,
                       priority: int = 5, strategy: RoutingStrategy = RoutingStrategy.LATENCY_BASED,
                       latency_offset_ms: float = 0.0) -> GlobalRoute:
        try:
            route_id = f"{source_region.value}->{target_region.value}"
            route = GlobalRoute(
                source_region=source_region,
                target_region=target_region,
                priority=priority,
                strategy=strategy,
                active=True,
                latency_offset_ms=latency_offset_ms,
            )
            with self._lock:
                self._routes[route_id] = route
            self._save()
            self.telemetry["routes_registered"] += 1
            logger.info("Registered route %s (priority=%d, strategy=%s)", route_id, priority, strategy.value)
            return route
        except Exception:
            logger.exception("Failed to register route")
            raise

    def get_route(self, source_region: Region, target_region: Region) -> Optional[GlobalRoute]:
        route_id = f"{source_region.value}->{target_region.value}"
        route = self._routes.get(route_id)
        if route and route.active:
            self.telemetry["routes_read"] += 1
            return route
        return None

    def route_request(self, source_region: Region, target_region: Region) -> dict:
        try:
            route = self.get_route(source_region, target_region)
            if route is None:
                # fallback: use default route
                route = GlobalRoute(
                    source_region=source_region,
                    target_region=target_region,
                    priority=0,
                    strategy=RoutingStrategy.GEOGRAPHIC,
                    active=True,
                )
            routing = {
                "source": source_region.value,
                "target": target_region.value,
                "strategy": route.strategy.value,
                "latency_offset_ms": route.latency_offset_ms,
                "routed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["requests_routed"] += 1
            return routing
        except Exception:
            logger.exception("Failed to route request")
            raise

    def get_optimal_region(self, source_region: Region, target_regions: list[Region]) -> dict:
        try:
            best = None
            best_latency = float("inf")
            for target in target_regions:
                route = self.get_route(source_region, target)
                if route is None:
                    continue
                total_latency = route.latency_offset_ms
                if total_latency < best_latency:
                    best_latency = total_latency
                    best = target
            if best is None and target_regions:
                best = target_regions[0]
                best_latency = 999.9
            return {
                "optimal_region": best.value if best else None,
                "estimated_latency_ms": best_latency,
                "source_region": source_region.value,
                "candidates": [r.value for r in target_regions],
            }
        except Exception:
            logger.exception("Failed to get optimal region")
            raise

    def get_route_metrics(self) -> dict:
        try:
            active_routes = sum(1 for r in self._routes.values() if r.active)
            inactive_routes = sum(1 for r in self._routes.values() if not r.active)
            return {
                "total_routes": len(self._routes),
                "active_routes": active_routes,
                "inactive_routes": inactive_routes,
                "routing_table_entries": len(self._routing_table),
            }
        except Exception:
            logger.exception("Failed to get route metrics")
            raise

    def update_routing_table(self, table: dict[str, str]) -> None:
        try:
            with self._lock:
                self._routing_table.update(table)
            self._save()
            self.telemetry["routing_tables_updated"] += 1
            logger.info("Updated routing table with %d entries", len(table))
        except Exception:
            logger.exception("Failed to update routing table")
            raise

    def failover(self, region: Region) -> dict:
        try:
            failover_targets = []
            for route_id, route in self._routes.items():
                if route.source_region == region and route.active:
                    route.active = False
                    self._routes[route_id] = route
                elif route.target_region == region and route.active:
                    failover_targets.append(route.source_region.value)
            self._save()
            self.telemetry["route_failovers"] += 1
            logger.info("Failover for region %s, affected %d routes", region.value, len(failover_targets))
            return {
                "failed_region": region.value,
                "routes_affected": len(self._routes),
                "failover_targets": failover_targets,
                "failed_over_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to failover region %s", region.value)
            raise


class EdgeServiceManager(GlobalCDN, EdgeAPI, RegionalCache, RegionalSearch, RegionalAIInference, GlobalRouter):
    """Unified edge services manager combining CDN, API, cache, search, inference, and routing."""

    def __init__(self, storage_dir: str):
        GlobalCDN.__init__(self, storage_dir)
        EdgeAPI.__init__(self, storage_dir)
        RegionalCache.__init__(self, storage_dir)
        RegionalSearch.__init__(self, storage_dir)
        RegionalAIInference.__init__(self, storage_dir)
        GlobalRouter.__init__(self, storage_dir)
        self.telemetry: dict = defaultdict(int)
        logger.info("EdgeServiceManager initialized at %s", storage_dir)

    def get_global_health(self) -> dict:
        try:
            all_endpoints = list(self._endpoints.values())
            total = len(all_endpoints)
            active = sum(1 for e in all_endpoints if e.status == "active")
            failover = sum(1 for e in all_endpoints if e.status == "failover")
            cache_metrics = self.get_cache_metrics()
            routes_metrics = self.get_route_metrics()
            health = {
                "status": "healthy" if active == total else "degraded",
                "endpoints": {
                    "total": total,
                    "active": active,
                    "failover": failover,
                },
                "cache": {
                    "total_regions": len(cache_metrics),
                    "total_hits": sum(m.hit_count for m in cache_metrics if m),
                    "total_misses": sum(m.miss_count for m in cache_metrics if m),
                },
                "routes": routes_metrics,
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.telemetry["health_checks"] += 1
            return health
        except Exception:
            logger.exception("Failed to get global health")
            raise

    def get_global_metrics(self) -> dict:
        try:
            cdn_metrics = self.get_cache_metrics()
            region_cache_metrics = {}
            for region in Region:
                m = self.get_region_metrics(region)
                if m:
                    region_cache_metrics[region.value] = m.to_dict()
            return {
                "cdn": [m.to_dict() for m in cdn_metrics],
                "regional_cache": region_cache_metrics,
                "search": self.get_search_metrics(),
                "routes": self.get_route_metrics(),
                "endpoint_count": len(self._endpoints),
                "gathered_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to get global metrics")
            raise

    def optimize_global_routing(self) -> dict:
        try:
            optimizations = []
            for region in Region:
                latency = self.get_region_latency(region)
                if latency > 200:
                    self.set_cache_strategy(region, CacheStrategy.ADAPTIVE)
                    self.optimize_for_region(region, {"target_latency_ms": 150, "cache_ttl": 300})
                    optimizations.append({
                        "region": region.value,
                        "action": "optimized",
                        "original_latency": latency,
                        "target_latency": 150,
                    })
            for src in Region:
                for tgt in Region:
                    if src != tgt:
                        route = self.get_route(src, tgt)
                        if route is None:
                            self.register_route(src, tgt, priority=1, strategy=RoutingStrategy.LATENCY_BASED)
                            optimizations.append({
                                "source": src.value,
                                "target": tgt.value,
                                "action": "route_created",
                            })
            self.telemetry["global_routing_optimized"] += 1
            logger.info("Optimized global routing with %d actions", len(optimizations))
            return {
                "optimizations": optimizations,
                "total_actions": len(optimizations),
                "completed_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception:
            logger.exception("Failed to optimize global routing")
            raise
