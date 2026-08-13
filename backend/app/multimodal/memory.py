"""Multimodal memory: per-tenant usage, budgets, analytics, cost tracking.

Budgets are read from NOVAFORGE_* config (see common/base Config) or env with
sane defaults. All counters are per-tenant and isolated.
"""
import logging, os, time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


@dataclass
class TenantUsage:
    tenant: str
    assets_ingested: int = 0
    chunks_indexed: int = 0
    ocr_calls: int = 0
    vision_calls: int = 0
    embed_calls: int = 0
    rag_searches: int = 0
    llm_calls: int = 0
    cost_usd: float = 0.0
    bytes_ingested: int = 0
    last_active: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {"tenant": self.tenant, "assets_ingested": self.assets_ingested,
                "chunks_indexed": self.chunks_indexed, "ocr_calls": self.ocr_calls,
                "vision_calls": self.vision_calls, "embed_calls": self.embed_calls,
                "rag_searches": self.rag_searches, "llm_calls": self.llm_calls,
                "cost_usd": round(self.cost_usd, 6),
                "bytes_ingested": self.bytes_ingested,
                "last_active": self.last_active}


class MultimodalMemory:
    """Per-tenant analytics with budget enforcement."""

    def __init__(self,
                 max_assets_per_tenant: int = 0,
                 max_chunks_per_tenant: int = 0,
                 max_bytes_per_tenant: int = 0,
                 max_cost_per_tenant: float = 0.0):
        self.max_assets = max_assets_per_tenant or _env_int("NOVAFORGE_MM_MAX_ASSETS", 0)
        self.max_chunks = max_chunks_per_tenant or _env_int("NOVAFORGE_MM_MAX_CHUNKS", 0)
        self.max_bytes = max_bytes_per_tenant or _env_int("NOVAFORGE_MM_MAX_BYTES", 0)
        self.max_cost = max_cost_per_tenant or float(
            os.getenv("NOVAFORGE_MM_MAX_COST_USD", "0") or 0)
        self._usage: dict[str, TenantUsage] = {}

    def _get(self, tenant: str) -> TenantUsage:
        if tenant not in self._usage:
            self._usage[tenant] = TenantUsage(tenant=tenant)
        return self._usage[tenant]

    def record(self, tenant: str, **fields) -> None:
        usage = self._get(tenant)
        for k, v in fields.items():
            if hasattr(usage, k):
                setattr(usage, k, getattr(usage, k) + v)
        usage.last_active = time.time()

    def can_ingest(self, tenant: str, size_bytes: int, extra_chunks: int = 0) -> dict:
        usage = self._get(tenant)
        if self.max_assets and usage.assets_ingested >= self.max_assets:
            return {"allowed": False,
                    "reason": f"asset budget reached ({self.max_assets})"}
        if self.max_bytes and usage.bytes_ingested + size_bytes > self.max_bytes:
            return {"allowed": False,
                    "reason": f"storage budget would be exceeded ({self.max_bytes} bytes)"}
        if self.max_chunks and usage.chunks_indexed + extra_chunks > self.max_chunks:
            return {"allowed": False,
                    "reason": f"chunk budget reached ({self.max_chunks})"}
        if self.max_cost and usage.cost_usd >= self.max_cost:
            return {"allowed": False,
                    "reason": f"cost budget reached (${self.max_cost:.2f})"}
        return {"allowed": True}

    def snapshot(self, tenant: str) -> dict:
        return self._get(tenant).to_dict()

    def all_usage(self) -> list[dict]:
        return [u.to_dict() for u in self._usage.values()]

    def totals(self) -> dict:
        keys = ["assets_ingested", "chunks_indexed", "ocr_calls", "vision_calls",
                "embed_calls", "rag_searches", "llm_calls", "bytes_ingested"]
        out = {k: sum(getattr(u, k) for u in self._usage.values()) for k in keys}
        out["cost_usd"] = round(sum(u.cost_usd for u in self._usage.values()), 6)
        out["tenants"] = len(self._usage)
        return out

    def health(self) -> dict:
        return {"budgets": {"max_assets_per_tenant": self.max_assets,
                            "max_chunks_per_tenant": self.max_chunks,
                            "max_bytes_per_tenant": self.max_bytes,
                            "max_cost_per_tenant": self.max_cost},
                "totals": self.totals()}