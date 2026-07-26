import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class AIServiceType(Enum):
    LLM_CHAT = "llm_chat"
    LLM_COMPLETION = "llm_completion"
    EMBEDDING = "embedding"
    IMAGE_GENERATION = "image_generation"
    AUDIO_TRANSCRIPTION = "audio_transcription"
    AUDIO_GENERATION = "audio_generation"
    CODE_GENERATION = "code_generation"
    REASONING = "reasoning"
    RAG = "rag"
    AGENT_EXECUTION = "agent_execution"
    TOOL_CALLING = "tool_calling"
    STREAMING = "streaming"
    BATCH_INFERENCE = "batch_inference"
    FINE_TUNING = "fine_tuning"


class ModelTier(Enum):
    FREE = "free"
    STANDARD = "standard"
    PREMIUM = "premium"
    ENTERPRISE = "enterprise"
    CUSTOM = "custom"


class CostUnit(Enum):
    PER_TOKEN = "per_token"
    PER_REQUEST = "per_request"
    PER_SECOND = "per_second"
    PER_CHAR = "per_char"
    PER_IMAGE = "per_image"
    PER_AUDIO_SEC = "per_audio_sec"
    PER_RUN = "per_run"
    PER_CALL = "per_call"


class TokenType(Enum):
    PROMPT = "prompt"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    REWRITING = "rewriting"
    CLASSIFICATION = "classification"
    SEARCH = "search"


@dataclass
class TokenUsage:
    id: str
    org_id: str
    workspace_id: str
    user_id: str
    model: str
    provider: str
    token_type: TokenType
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    session_id: str = ""
    request_id: str = ""
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total_tokens == 0:
            self.total_tokens = self.prompt_tokens + self.completion_tokens

    def to_dict(self) -> dict:
        d = asdict(self)
        d["token_type"] = self.token_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TokenUsage":
        data["token_type"] = TokenType(data.get("token_type", "prompt"))
        return cls(**data)


@dataclass
class AICostEntry:
    id: str
    org_id: str
    workspace_id: str
    user_id: str
    service: AIServiceType
    model: str
    provider: str
    tier: ModelTier
    unit: CostUnit
    usage_amount: float = 0.0
    unit_price: float = 0.0
    total_cost: float = 0.0
    tokens: Optional[TokenUsage] = None
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tags: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["service"] = self.service.value
        d["tier"] = self.tier.value
        d["unit"] = self.unit.value
        if self.tokens:
            d["tokens"] = self.tokens.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "AICostEntry":
        data["service"] = AIServiceType(data.get("service", "llm_chat"))
        data["tier"] = ModelTier(data.get("tier", "standard"))
        data["unit"] = CostUnit(data.get("unit", "per_token"))
        if data.get("tokens") and isinstance(data["tokens"], dict):
            data["tokens"] = TokenUsage.from_dict(data["tokens"])
        return cls(**data)


@dataclass
class ProviderCostRate:
    id: str
    provider: str
    model: str
    tier: ModelTier
    unit: CostUnit
    prompt_rate_per_million: float = 0.0
    completion_rate_per_million: float = 0.0
    embedding_rate_per_million: float = 0.0
    request_rate: float = 0.0
    hourly_rate: float = 0.0
    effective_from: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_to: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["tier"] = self.tier.value
        d["unit"] = self.unit.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ProviderCostRate":
        data["tier"] = ModelTier(data.get("tier", "standard"))
        data["unit"] = CostUnit(data.get("unit", "per_token"))
        return cls(**data)


@dataclass
class DailyAICost:
    id: str
    org_id: str
    date: str
    total_cost: float = 0.0
    by_service: dict = field(default_factory=dict)
    by_model: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_workspace: dict = field(default_factory=dict)
    total_tokens: int = 0
    total_requests: int = 0
    avg_latency_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "DailyAICost":
        return cls(**data)


@dataclass
class AICostReport:
    id: str
    org_id: str
    start_date: str
    end_date: str
    total_cost: float = 0.0
    by_model: dict = field(default_factory=dict)
    by_provider: dict = field(default_factory=dict)
    by_service: dict = field(default_factory=dict)
    by_workspace: dict = field(default_factory=dict)
    token_breakdown: dict = field(default_factory=dict)
    cost_per_request: float = 0.0
    cost_per_token: float = 0.0
    top_models: list = field(default_factory=list)
    trends: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "AICostReport":
        return cls(**data)


class AICostTracker:
    def __init__(self, storage_dir: str = "ai_cost_tracking_data"):
        self.storage_dir = storage_dir
        self._token_usage: dict[str, TokenUsage] = {}
        self._ai_cost_entries: dict[str, AICostEntry] = {}
        self._provider_rates: dict[str, ProviderCostRate] = {}
        self._daily_costs: dict[str, DailyAICost] = {}
        self._reports: dict[str, AICostReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _token_usage_path(self) -> str:
        return os.path.join(self.storage_dir, "token_usage.json")

    def _ai_cost_entries_path(self) -> str:
        return os.path.join(self.storage_dir, "ai_cost_entries.json")

    def _provider_rates_path(self) -> str:
        return os.path.join(self.storage_dir, "provider_rates.json")

    def _daily_costs_path(self) -> str:
        return os.path.join(self.storage_dir, "daily_costs.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "reports.json")

    def _save(self) -> None:
        try:
            token_data = {tid: t.to_dict() for tid, t in self._token_usage.items()}
            with open(self._token_usage_path(), "w", encoding="utf-8") as f:
                json.dump(token_data, f, indent=2, default=str)

            entries_data = {eid: e.to_dict() for eid, e in self._ai_cost_entries.items()}
            with open(self._ai_cost_entries_path(), "w", encoding="utf-8") as f:
                json.dump(entries_data, f, indent=2, default=str)

            rates_data = {rid: r.to_dict() for rid, r in self._provider_rates.items()}
            with open(self._provider_rates_path(), "w", encoding="utf-8") as f:
                json.dump(rates_data, f, indent=2, default=str)

            daily_data = {did: d.to_dict() for did, d in self._daily_costs.items()}
            with open(self._daily_costs_path(), "w", encoding="utf-8") as f:
                json.dump(daily_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save AI cost tracking data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._token_usage_path()):
                with open(self._token_usage_path(), "r", encoding="utf-8") as f:
                    token_data = json.load(f)
                for tid, data in token_data.items():
                    try:
                        self._token_usage[tid] = TokenUsage.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed token usage %s: %s", tid, e)

            if os.path.exists(self._ai_cost_entries_path()):
                with open(self._ai_cost_entries_path(), "r", encoding="utf-8") as f:
                    entries_data = json.load(f)
                for eid, data in entries_data.items():
                    try:
                        self._ai_cost_entries[eid] = AICostEntry.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed AI cost entry %s: %s", eid, e)

            if os.path.exists(self._provider_rates_path()):
                with open(self._provider_rates_path(), "r", encoding="utf-8") as f:
                    rates_data = json.load(f)
                for rid, data in rates_data.items():
                    try:
                        self._provider_rates[rid] = ProviderCostRate.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed provider rate %s: %s", rid, e)

            if os.path.exists(self._daily_costs_path()):
                with open(self._daily_costs_path(), "r", encoding="utf-8") as f:
                    daily_data = json.load(f)
                for did, data in daily_data.items():
                    try:
                        self._daily_costs[did] = DailyAICost.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed daily cost %s: %s", did, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = AICostReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load AI cost tracking data: %s", e, exc_info=True)

    def track_usage(self, usage: TokenUsage) -> TokenUsage:
        self._telemetry["track_usage_calls"] += 1
        if not usage.id:
            usage.id = str(uuid.uuid4())
        if not usage.timestamp:
            usage.timestamp = datetime.now(timezone.utc).isoformat()
        usage.total_tokens = usage.prompt_tokens + usage.completion_tokens
        self._token_usage[usage.id] = usage
        self._save()
        logger.info("Tracked token usage %s: %d total tokens for model %s", usage.id, usage.total_tokens, usage.model)
        return usage

    def track_ai_cost(self, entry: AICostEntry) -> AICostEntry:
        self._telemetry["track_ai_cost_calls"] += 1
        if not entry.id:
            entry.id = str(uuid.uuid4())
        if not entry.timestamp:
            entry.timestamp = datetime.now(timezone.utc).isoformat()
        entry.total_cost = round(entry.usage_amount * entry.unit_price, 6)
        self._ai_cost_entries[entry.id] = entry

        today = entry.timestamp[:10]
        daily = self._get_or_create_daily(entry.org_id, today)
        daily.total_cost = round(daily.total_cost + entry.total_cost, 4)
        daily.by_service[entry.service.value] = round(daily.by_service.get(entry.service.value, 0.0) + entry.total_cost, 4)
        daily.by_model[entry.model] = round(daily.by_model.get(entry.model, 0.0) + entry.total_cost, 4)
        daily.by_provider[entry.provider] = round(daily.by_provider.get(entry.provider, 0.0) + entry.total_cost, 4)
        daily.by_workspace[entry.workspace_id] = round(daily.by_workspace.get(entry.workspace_id, 0.0) + entry.total_cost, 4)
        daily.total_requests += 1
        if entry.tokens:
            daily.total_tokens += entry.tokens.total_tokens
        if entry.latency_ms > 0:
            prev_total = daily.avg_latency_ms * (daily.total_requests - 1)
            daily.avg_latency_ms = round((prev_total + entry.latency_ms) / daily.total_requests, 2)

        self._save()
        logger.info("Tracked AI cost entry %s: %.4f for service %s", entry.id, entry.total_cost, entry.service.value)
        return entry

    def _get_or_create_daily(self, org_id: str, date_str: str) -> DailyAICost:
        for d in self._daily_costs.values():
            if d.org_id == org_id and d.date == date_str:
                return d
        daily = DailyAICost(
            id=str(uuid.uuid4()),
            org_id=org_id,
            date=date_str,
        )
        self._daily_costs[daily.id] = daily
        return daily

    def register_provider_rate(self, rate: ProviderCostRate) -> ProviderCostRate:
        self._telemetry["register_provider_rate_calls"] += 1
        if not rate.id:
            rate.id = str(uuid.uuid4())
        if not rate.effective_from:
            rate.effective_from = datetime.now(timezone.utc).isoformat()
        self._provider_rates[rate.id] = rate
        self._save()
        logger.info("Registered provider rate %s for %s/%s", rate.id, rate.provider, rate.model)
        return rate

    def get_provider_rate(self, provider: str, model: str) -> Optional[ProviderCostRate]:
        self._telemetry["get_provider_rate_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        candidates = []
        for rate in self._provider_rates.values():
            if rate.provider.lower() == provider.lower() and rate.model.lower() == model.lower():
                if rate.effective_from <= now:
                    if not rate.effective_to or rate.effective_to >= now:
                        candidates.append(rate)
        if not candidates:
            return None
        candidates.sort(key=lambda r: r.effective_from, reverse=True)
        return candidates[0]

    def calculate_cost(self, model: str, provider: str, prompt_tokens: int, completion_tokens: int) -> dict:
        self._telemetry["calculate_cost_calls"] += 1
        rate = self.get_provider_rate(provider, model)
        if not rate:
            return {
                "model": model,
                "provider": provider,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "prompt_cost": 0.0,
                "completion_cost": 0.0,
                "total_cost": 0.0,
                "note": "No matching rate found. Costs are zero.",
            }

        prompt_cost = (prompt_tokens / 1_000_000) * rate.prompt_rate_per_million
        completion_cost = (completion_tokens / 1_000_000) * rate.completion_rate_per_million
        total_cost = round(prompt_cost + completion_cost, 6)

        return {
            "model": model,
            "provider": provider,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
            "prompt_cost": round(prompt_cost, 6),
            "completion_cost": round(completion_cost, 6),
            "total_cost": total_cost,
            "rate_applied": rate.to_dict(),
        }

    def get_daily_costs(self, org_id: str, start_date: str, end_date: str) -> list[DailyAICost]:
        self._telemetry["get_daily_costs_calls"] += 1
        results = []
        for daily in self._daily_costs.values():
            if daily.org_id == org_id and start_date <= daily.date <= end_date:
                results.append(daily)
        results.sort(key=lambda d: d.date)
        return results

    def get_ai_cost_report(self, org_id: str, start_date: str, end_date: str) -> AICostReport:
        self._telemetry["get_ai_cost_report_calls"] += 1
        filtered_entries = [
            e for e in self._ai_cost_entries.values()
            if e.org_id == org_id and start_date <= e.timestamp[:10] <= end_date
        ]

        total_cost = sum(e.total_cost for e in filtered_entries)
        total_requests = len(filtered_entries)
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0

        by_model: dict[str, float] = defaultdict(float)
        by_provider: dict[str, float] = defaultdict(float)
        by_service: dict[str, float] = defaultdict(float)
        by_workspace: dict[str, float] = defaultdict(float)

        for e in filtered_entries:
            by_model[e.model] += e.total_cost
            by_provider[e.provider] += e.total_cost
            by_service[e.service.value] += e.total_cost
            by_workspace[e.workspace_id] += e.total_cost
            if e.tokens:
                total_prompt_tokens += e.tokens.prompt_tokens
                total_completion_tokens += e.tokens.completion_tokens
                total_tokens += e.tokens.total_tokens

        token_breakdown = {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        }

        cost_per_request = round(total_cost / total_requests, 6) if total_requests > 0 else 0.0
        cost_per_token = round(total_cost / total_tokens, 8) if total_tokens > 0 else 0.0

        sorted_models = sorted(by_model.items(), key=lambda x: x[1], reverse=True)
        top_models = [
            {"model": m, "cost": round(c, 4), "percentage": round(c / total_cost * 100, 2) if total_cost > 0 else 0}
            for m, c in sorted_models[:10]
        ]

        daily_totals: dict[str, float] = defaultdict(float)
        for e in filtered_entries:
            day_key = e.timestamp[:10]
            daily_totals[day_key] += e.total_cost
        trends = [{"date": day, "cost": round(c, 4)} for day, c in sorted(daily_totals.items())]

        report = AICostReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            start_date=start_date,
            end_date=end_date,
            total_cost=round(total_cost, 4),
            by_model={k: round(v, 4) for k, v in by_model.items()},
            by_provider={k: round(v, 4) for k, v in by_provider.items()},
            by_service={k: round(v, 4) for k, v in by_service.items()},
            by_workspace={k: round(v, 4) for k, v in by_workspace.items()},
            token_breakdown=token_breakdown,
            cost_per_request=cost_per_request,
            cost_per_token=cost_per_token,
            top_models=top_models,
            trends=trends,
        )
        self._reports[report.id] = report
        self._save()
        return report

    def get_top_costly_models(self, org_id: str, limit: int = 10) -> list[dict]:
        self._telemetry["get_top_costly_models_calls"] += 1
        model_costs: dict[str, float] = defaultdict(float)
        model_info: dict[str, dict] = {}

        for entry in self._ai_cost_entries.values():
            if entry.org_id == org_id:
                model_costs[entry.model] += entry.total_cost
                if entry.model not in model_info:
                    model_info[entry.model] = {
                        "model": entry.model,
                        "provider": entry.provider,
                        "service": entry.service.value,
                        "tier": entry.tier.value,
                    }

        sorted_models = sorted(model_costs.items(), key=lambda x: x[1], reverse=True)[:limit]
        total = sum(c for _, c in sorted_models)

        results = []
        for model_name, cost in sorted_models:
            info = model_info.get(model_name, {})
            results.append({
                "model": model_name,
                "provider": info.get("provider", ""),
                "service": info.get("service", ""),
                "tier": info.get("tier", ""),
                "total_cost": round(cost, 4),
                "percentage": round(cost / total * 100, 2) if total > 0 else 0,
            })
        return results

    def get_usage_by_workspace(self, org_id: str) -> dict:
        self._telemetry["get_usage_by_workspace_calls"] += 1
        workspace_data: dict[str, dict] = {}

        for entry in self._ai_cost_entries.values():
            if entry.org_id == org_id:
                ws_id = entry.workspace_id
                if ws_id not in workspace_data:
                    workspace_data[ws_id] = {
                        "workspace_id": ws_id,
                        "total_cost": 0.0,
                        "total_tokens": 0,
                        "total_requests": 0,
                        "models": set(),
                        "services": set(),
                    }
                workspace_data[ws_id]["total_cost"] += entry.total_cost
                if entry.tokens:
                    workspace_data[ws_id]["total_tokens"] += entry.tokens.total_tokens
                workspace_data[ws_id]["total_requests"] += 1
                workspace_data[ws_id]["models"].add(entry.model)
                workspace_data[ws_id]["services"].add(entry.service.value)

        for ws_id in workspace_data:
            workspace_data[ws_id]["total_cost"] = round(workspace_data[ws_id]["total_cost"], 4)
            workspace_data[ws_id]["models"] = list(workspace_data[ws_id]["models"])
            workspace_data[ws_id]["services"] = list(workspace_data[ws_id]["services"])

        return dict(workspace_data)

    def get_cost_by_service_type(self, org_id: str) -> dict:
        self._telemetry["get_cost_by_service_type_calls"] += 1
        service_data: dict[str, dict] = {}

        for entry in self._ai_cost_entries.values():
            if entry.org_id == org_id:
                svc = entry.service.value
                if svc not in service_data:
                    service_data[svc] = {
                        "service": svc,
                        "total_cost": 0.0,
                        "total_requests": 0,
                        "total_tokens": 0,
                        "providers": set(),
                        "models": set(),
                    }
                service_data[svc]["total_cost"] += entry.total_cost
                service_data[svc]["total_requests"] += 1
                if entry.tokens:
                    service_data[svc]["total_tokens"] += entry.tokens.total_tokens
                service_data[svc]["providers"].add(entry.provider)
                service_data[svc]["models"].add(entry.model)

        total_cost = sum(d["total_cost"] for d in service_data.values())
        for svc in service_data:
            service_data[svc]["total_cost"] = round(service_data[svc]["total_cost"], 4)
            service_data[svc]["percentage"] = round(service_data[svc]["total_cost"] / total_cost * 100, 2) if total_cost > 0 else 0
            service_data[svc]["providers"] = list(service_data[svc]["providers"])
            service_data[svc]["models"] = list(service_data[svc]["models"])

        return dict(service_data)

    def compare_provider_costs(self, model: str, providers: list[str]) -> list[dict]:
        self._telemetry["compare_provider_costs_calls"] += 1
        results = []

        for provider in providers:
            rate = self.get_provider_rate(provider, model)
            if not rate:
                results.append({
                    "provider": provider,
                    "model": model,
                    "available": False,
                    "prompt_cost_per_million": None,
                    "completion_cost_per_million": None,
                    "embedding_cost_per_million": None,
                    "request_cost": None,
                    "hourly_cost": None,
                    "tier": None,
                    "estimated_cost_10k_prompt_5k_completion": None,
                    "note": "No rate registered for this provider/model combination",
                })
                continue

            est_prompt = (10000 / 1_000_000) * rate.prompt_rate_per_million
            est_completion = (5000 / 1_000_000) * rate.completion_rate_per_million
            est_total = round(est_prompt + est_completion, 6)

            results.append({
                "provider": provider,
                "model": model,
                "available": True,
                "tier": rate.tier.value,
                "unit": rate.unit.value,
                "prompt_cost_per_million": rate.prompt_rate_per_million,
                "completion_cost_per_million": rate.completion_rate_per_million,
                "embedding_cost_per_million": rate.embedding_rate_per_million,
                "request_cost": rate.request_rate,
                "hourly_cost": rate.hourly_rate,
                "estimated_cost_10k_prompt_5k_completion": est_total,
                "effective_from": rate.effective_from,
                "effective_to": rate.effective_to or "ongoing",
            })

        results.sort(key=lambda r: (
            r.get("estimated_cost_10k_prompt_5k_completion") if r.get("estimated_cost_10k_prompt_5k_completion") is not None else float("inf")
        ))
        return results

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
