"""Multimodal memory: per-tenant usage, budgets, analytics, cost tracking.

Budgets are read from NOVAFORGE_* config (see common/base Config) or env with
sane defaults. All counters are per-tenant and isolated. The cost ledger keeps
an append-only per-operation record mirroring the `multimodal_cost_ledger`
table (operation, provider, model, tokens, cost_usd).
"""
import logging, os, time, uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

LEDGER_LIMIT = 10_000  # bound in-memory ledger growth per process


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


@dataclass
class CostLedgerEntry:
    id: str
    organization_id: str
    operation: str
    cost_usd: float = 0.0
    provider: str = ""
    model: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    asset_id: str = ""
    recorded_at: str = ""

    def to_dict(self) -> dict:
        return {"id": self.id, "organization_id": self.organization_id,
                "operation": self.operation, "cost_usd": round(self.cost_usd, 6),
                "provider": self.provider, "model": self.model,
                "tokens_in": self.tokens_in, "tokens_out": self.tokens_out,
                "asset_id": self.asset_id, "recorded_at": self.recorded_at}


class MultimodalMemory:
    """Per-tenant analytics with budget enforcement and a cost ledger."""

    def __init__(self,
                 max_assets_per_tenant: int = 0,
                 max_chunks_per_tenant: int = 0,
                 max_bytes_per_tenant: int = 0,
                 max_cost_per_tenant: float = 0.0,
                 storage=None):
        self.max_assets = max_assets_per_tenant or _env_int("NOVAFORGE_MM_MAX_ASSETS", 0)
        self.max_chunks = max_chunks_per_tenant or _env_int("NOVAFORGE_MM_MAX_CHUNKS", 0)
        self.max_bytes = max_bytes_per_tenant or _env_int("NOVAFORGE_MM_MAX_BYTES", 0)
        self.max_cost = max_cost_per_tenant or float(
            os.getenv("NOVAFORGE_MM_MAX_COST_USD", "0") or 0)
        self.storage = storage  # Optional[JsonFileStorage]; may be None
        self._usage: dict[str, TenantUsage] = {}
        self._ledger: list[CostLedgerEntry] = []
        self._load_ledger()

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
                "totals": self.totals(),
                "ledger_entries": len(self._ledger)}

    # ------------------------------------------------------------- cost ledger
    def record_cost(self, tenant: str, operation: str, cost_usd: float = 0.0,
                    provider: str = "", model: str = "", tokens_in: int = 0,
                    tokens_out: int = 0, asset_id: str = "") -> dict:
        """Append one cost-ledger entry and fold it into the tenant totals.

        Honest by construction: callers pass the actual measured cost; free
        paths (local heuristic embedding, in-process OCR) record 0.0.
        """
        entry = CostLedgerEntry(
            id=uuid.uuid4().hex[:16], organization_id=tenant,
            operation=operation, cost_usd=round(max(cost_usd, 0.0), 6),
            provider=provider, model=model, tokens_in=tokens_in,
            tokens_out=tokens_out, asset_id=asset_id,
            recorded_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
        self._ledger.append(entry)
        if len(self._ledger) > LEDGER_LIMIT:
            self._ledger = self._ledger[-LEDGER_LIMIT:]
        usage = self._get(tenant)
        usage.cost_usd += entry.cost_usd
        usage.last_active = time.time()
        self._flush_ledger()
        return entry.to_dict()

    def ledger(self, tenant: str = "", limit: int = 100) -> list[dict]:
        rows = [e.to_dict() for e in self._ledger
                if not tenant or e.organization_id == tenant]
        return rows[-limit:][::-1]

    def cost_totals(self) -> dict:
        totals: dict[str, dict] = {}
        for e in self._ledger:
            bucket = totals.setdefault(
                e.organization_id,
                {"operations": {}, "cost_usd": 0.0, "tokens_in": 0,
                 "tokens_out": 0, "entries": 0})
            bucket["cost_usd"] += e.cost_usd
            bucket["tokens_in"] += e.tokens_in
            bucket["tokens_out"] += e.tokens_out
            bucket["entries"] += 1
            op = bucket["operations"].setdefault(
                e.operation, {"count": 0, "cost_usd": 0.0})
            op["count"] += 1
            op["cost_usd"] += e.cost_usd
        return {tenant: {**b,
                         "cost_usd": round(b["cost_usd"], 6),
                         "operations": {k: {**v, "cost_usd": round(v["cost_usd"], 6)}
                                        for k, v in b["operations"].items()}}
                for tenant, b in totals.items()}

    def _load_ledger(self) -> None:
        if self.storage is None:
            return
        try:
            raw = self.storage.get("ledger") or []
            for row in raw:
                if isinstance(row, dict):
                    self._ledger.append(CostLedgerEntry(
                        **{k: v for k, v in row.items()
                           if k in CostLedgerEntry.__dataclass_fields__}))
        except Exception as exc:
            logger.warning("cost ledger load failed: %s", exc)

    def _flush_ledger(self) -> None:
        if self.storage is None:
            return
        try:
            self.storage.set("ledger",
                             [e.to_dict() for e in self._ledger[-LEDGER_LIMIT:]])
        except Exception as exc:
            logger.warning("cost ledger flush failed: %s", exc)