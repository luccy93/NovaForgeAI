import json
import uuid
import hashlib
import time
import math
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class TaskType(Enum):
    CHAT = "chat"
    CODE_GENERATION = "code_generation"
    CODE_REVIEW = "code_review"
    EMBEDDING = "embedding"
    SUMMARIZATION = "summarization"
    CLASSIFICATION = "classification"
    EXTRACTION = "extraction"
    REASONING = "reasoning"
    CREATIVE_WRITING = "creative_writing"
    TRANSLATION = "translation"
    ANALYTICS = "analytics"
    SECURITY = "security"
    TESTING = "testing"
    DOCUMENTATION = "documentation"
    SEARCH = "search"
    TOOL_CALLING = "tool_calling"
    RAG = "rag"
    AGENT = "agent"


class RoutingStrategy(Enum):
    WEIGHTED = "weighted"
    LATENCY_OPTIMAL = "latency_optimal"
    COST_OPTIMAL = "cost_optimal"
    ACCURACY_OPTIMAL = "accuracy_optimal"
    FALLBACK_CHAIN = "fallback_chain"
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    CONTEXT_AWARE = "context_aware"


@dataclass
class ModelScore:
    model_id: str
    provider: str
    task_type: TaskType
    accuracy_score: float = 0.0
    latency_score: float = 0.0
    cost_score: float = 0.0
    overall_score: float = 0.0
    weight: float = 1.0

    def to_dict(self) -> dict:
        d = asdict(self)
        d["task_type"] = self.task_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModelScore":
        data["task_type"] = TaskType(data["task_type"])
        return cls(**data)


@dataclass
class RoutingRule:
    id: str
    org_id: str
    task_type: TaskType
    strategy: RoutingStrategy
    models: list[str] = field(default_factory=list)
    weights: list[float] = field(default_factory=list)
    fallback_models: list[str] = field(default_factory=list)
    min_accuracy: float = 0.0
    max_cost: float = float("inf")
    max_latency_ms: float = float("inf")
    require_tool_calling: bool = False
    require_vision: bool = False
    require_streaming: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["task_type"] = self.task_type.value
        d["strategy"] = self.strategy.value
        if math.isinf(self.max_cost):
            d["max_cost"] = "inf"
        if math.isinf(self.max_latency_ms):
            d["max_latency_ms"] = "inf"
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingRule":
        data["task_type"] = TaskType(data["task_type"])
        data["strategy"] = RoutingStrategy(data["strategy"])
        if data.get("max_cost") == "inf" or data.get("max_cost") is None:
            data["max_cost"] = float("inf")
        if data.get("max_latency_ms") == "inf" or data.get("max_latency_ms") is None:
            data["max_latency_ms"] = float("inf")
        return cls(**data)


@dataclass
class RoutingDecision:
    id: str
    request_id: str
    task_type: TaskType
    selected_model: str
    selected_provider: str
    score: float = 0.0
    alternatives: list[dict] = field(default_factory=list)
    decision_factors: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["task_type"] = self.task_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "RoutingDecision":
        data["task_type"] = TaskType(data["task_type"])
        return cls(**data)


@dataclass
class RouterMetrics:
    total_routes: int = 0
    successful_routes: int = 0
    failed_routes: int = 0
    fallback_routes: int = 0
    avg_latency_ms: float = 0.0
    avg_cost: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RouterMetrics":
        return cls(**data)


class ModelRouter:
    def __init__(self, storage_dir: str = "router_data"):
        self.storage_dir = storage_dir
        self._rules: dict[str, RoutingRule] = {}
        self._decisions: list[RoutingDecision] = []
        self._model_scores: dict[str, list[ModelScore]] = defaultdict(list)
        self._metrics = RouterMetrics()
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rules_path(self) -> str:
        return os.path.join(self.storage_dir, "rules.json")

    def _decisions_path(self) -> str:
        return os.path.join(self.storage_dir, "decisions.json")

    def _scores_path(self) -> str:
        return os.path.join(self.storage_dir, "scores.json")

    def _metrics_path(self) -> str:
        return os.path.join(self.storage_dir, "metrics.json")

    def _save(self) -> None:
        try:
            rules_data = {rid: r.to_dict() for rid, r in self._rules.items()}
            with open(self._rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2, default=str)

            decisions_data = [d.to_dict() for d in self._decisions[-1000:]]
            with open(self._decisions_path(), "w", encoding="utf-8") as f:
                json.dump(decisions_data, f, indent=2, default=str)

            scores_data = {mid: [s.to_dict() for s in slist] for mid, slist in self._model_scores.items()}
            with open(self._scores_path(), "w", encoding="utf-8") as f:
                json.dump(scores_data, f, indent=2, default=str)

            with open(self._metrics_path(), "w", encoding="utf-8") as f:
                json.dump(self._metrics.to_dict(), f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save router data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._rules_path()):
                with open(self._rules_path(), "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                for rid, data in rules_data.items():
                    try:
                        self._rules[rid] = RoutingRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed rule %s: %s", rid, e)

            if os.path.exists(self._decisions_path()):
                with open(self._decisions_path(), "r", encoding="utf-8") as f:
                    decisions_data = json.load(f)
                for ddata in decisions_data:
                    try:
                        self._decisions.append(RoutingDecision.from_dict(ddata))
                    except Exception as e:
                        logger.warning("Skipping malformed decision: %s", e)

            if os.path.exists(self._scores_path()):
                with open(self._scores_path(), "r", encoding="utf-8") as f:
                    scores_data = json.load(f)
                for mid, slist in scores_data.items():
                    self._model_scores[mid] = []
                    for sdata in slist:
                        try:
                            self._model_scores[mid].append(ModelScore.from_dict(sdata))
                        except Exception as e:
                            logger.warning("Skipping malformed score for %s: %s", mid, e)

            if os.path.exists(self._metrics_path()):
                with open(self._metrics_path(), "r", encoding="utf-8") as f:
                    metrics_data = json.load(f)
                self._metrics = RouterMetrics.from_dict(metrics_data)
        except Exception as e:
            logger.error("Failed to load router data: %s", e, exc_info=True)

    def set_routing_rule(self, rule: RoutingRule) -> RoutingRule:
        self._telemetry["set_routing_rule_calls"] += 1
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        self._rules[rule.id] = rule
        self._save()
        logger.info("Set routing rule %s for task %s", rule.id, rule.task_type.value)
        return rule

    def get_routing_rule(self, rule_id: str) -> Optional[RoutingRule]:
        self._telemetry["get_routing_rule_calls"] += 1
        return self._rules.get(rule_id)

    def get_fallback_chain(self, task_type: TaskType) -> list[str]:
        self._telemetry["get_fallback_chain_calls"] += 1
        for rule in self._rules.values():
            if rule.task_type == task_type and rule.fallback_models:
                return rule.fallback_models
        return []

    def calculate_weighted_score(self, model_id: str, task_type: TaskType, scores: list[ModelScore]) -> float:
        self._telemetry["calculate_weighted_score_calls"] += 1
        matched = [s for s in scores if s.model_id == model_id and s.task_type == task_type]
        if not matched:
            return 0.0
        total_weight = sum(s.weight for s in matched)
        if total_weight == 0:
            return 0.0
        weighted = sum(s.overall_score * s.weight for s in matched)
        return weighted / total_weight

    def route(self, task_type: TaskType, request_id: str, context: Optional[dict] = None) -> RoutingDecision:
        self._telemetry["route_calls"] += 1
        start = time.time()
        context = context or {}

        rule = self._find_rule_for_task(task_type)
        if not rule:
            rule_id = f"rule_{uuid.uuid4().hex[:12]}"
            rule = RoutingRule(
                id=rule_id,
                org_id=context.get("org_id", "default"),
                task_type=task_type,
                strategy=RoutingStrategy.WEIGHTED,
                models=context.get("models", []),
            )
            self.set_routing_rule(rule)

        decision = self.select_best_model(rule, context)
        decision.request_id = request_id
        decision.task_type = task_type
        decision.id = str(uuid.uuid4())
        decision.latency_ms = (time.time() - start) * 1000
        decision.created_at = datetime.now(timezone.utc).isoformat()

        self._decisions.append(decision)
        self._metrics.total_routes += 1
        if decision.selected_model:
            self._metrics.successful_routes += 1
        else:
            self._metrics.failed_routes += 1
        n = self._metrics.total_routes
        self._metrics.avg_latency_ms = ((self._metrics.avg_latency_ms * (n - 1)) + decision.latency_ms) / n
        self._save()
        return decision

    def select_best_model(self, rule: RoutingRule, context: dict) -> RoutingDecision:
        self._telemetry["select_best_model_calls"] += 1
        alternatives = []
        decision_factors = {"strategy": rule.strategy.value, "task_type": rule.task_type.value}

        candidate_models = rule.models
        if context.get("available_models"):
            candidate_models = [m for m in candidate_models if m in context["available_models"]]

        if not candidate_models:
            if rule.fallback_models:
                decision_factors["using_fallback"] = True
                candidate_models = rule.fallback_models
                self._metrics.fallback_routes += 1
            else:
                return RoutingDecision(
                    id="", request_id="", task_type=rule.task_type,
                    selected_model="", selected_provider="", score=0.0,
                    alternatives=[], decision_factors={"error": "No models available"},
                )

        strategy_fn = self._get_strategy_fn(rule.strategy)
        selected, score, alts = strategy_fn(rule, candidate_models, context)

        decision_factors["total_candidates"] = len(candidate_models)
        decision_factors["selected_index"] = (
            [m["model_id"] for m in alts].index(selected) if any(m["model_id"] == selected for m in alts) else -1
        )

        return RoutingDecision(
            id="", request_id="", task_type=rule.task_type,
            selected_model=selected,
            selected_provider=self._extract_provider(selected),
            score=score,
            alternatives=alts,
            decision_factors=decision_factors,
        )

    def _extract_provider(self, model_id: str) -> str:
        if "/" in model_id:
            return model_id.split("/")[0]
        return "unknown"

    def _find_rule_for_task(self, task_type: TaskType) -> Optional[RoutingRule]:
        for rule in self._rules.values():
            if rule.task_type == task_type:
                return rule
        return None

    def _get_strategy_fn(self, strategy: RoutingStrategy):
        strategies = {
            RoutingStrategy.WEIGHTED: self._weighted_strategy,
            RoutingStrategy.LATENCY_OPTIMAL: self._latency_optimal_strategy,
            RoutingStrategy.COST_OPTIMAL: self._cost_optimal_strategy,
            RoutingStrategy.ACCURACY_OPTIMAL: self._accuracy_optimal_strategy,
            RoutingStrategy.FALLBACK_CHAIN: self._fallback_chain_strategy,
            RoutingStrategy.ROUND_ROBIN: self._round_robin_strategy,
            RoutingStrategy.LEAST_LOADED: self._least_loaded_strategy,
            RoutingStrategy.CONTEXT_AWARE: self._context_aware_strategy,
        }
        return strategies.get(strategy, self._weighted_strategy)

    def _weighted_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        weights = rule.weights if rule.weights and len(rule.weights) == len(candidates) else [1.0 / len(candidates)] * len(candidates)
        total = sum(weights)
        normalized = [w / total for w in weights]
        alternatives = []
        for i, model in enumerate(candidates):
            alternatives.append({"model_id": model, "weight": normalized[i], "score": normalized[i]})
        r = (hash(context.get("request_id", "")) % 10000) / 10000.0
        cum = 0.0
        for i, model in enumerate(candidates):
            cum += normalized[i]
            if r <= cum:
                return model, normalized[i], alternatives
        return candidates[-1], normalized[-1], alternatives

    def _latency_optimal_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        scored = []
        for model in candidates:
            scores = self._model_scores.get(model, [])
            avg_latency = sum(s.latency_score for s in scores) / max(len(scores), 1)
            scored.append((model, avg_latency))
        scored.sort(key=lambda x: x[1], reverse=True)
        alternatives = [{"model_id": m, "latency_score": s} for m, s in scored]
        best = scored[0] if scored else (candidates[0], 0)
        return best[0], best[1], alternatives

    def _cost_optimal_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        scored = []
        for model in candidates:
            scores = self._model_scores.get(model, [])
            avg_cost = sum(s.cost_score for s in scores) / max(len(scores), 1)
            scored.append((model, avg_cost))
        scored.sort(key=lambda x: x[1], reverse=True)
        alternatives = [{"model_id": m, "cost_score": s} for m, s in scored]
        best = scored[0] if scored else (candidates[0], 0)
        return best[0], best[1], alternatives

    def _accuracy_optimal_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        scored = []
        for model in candidates:
            scores = self._model_scores.get(model, [])
            avg_acc = sum(s.accuracy_score for s in scores) / max(len(scores), 1)
            scored.append((model, avg_acc))
        scored.sort(key=lambda x: x[1], reverse=True)
        alternatives = [{"model_id": m, "accuracy_score": s} for m, s in scored]
        best = scored[0] if scored else (candidates[0], 0)
        return best[0], best[1], alternatives

    def _fallback_chain_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        chain = rule.fallback_models or candidates
        alternatives = [{"model_id": m, "fallback_order": i} for i, m in enumerate(chain)]
        return chain[0], 1.0 / max(len(chain), 1), alternatives

    def _round_robin_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        idx = self._telemetry.get("round_robin_counter", 0) % max(len(candidates), 1)
        self._telemetry["round_robin_counter"] = idx + 1
        alternatives = [{"model_id": m, "round_robin_index": i} for i, m in enumerate(candidates)]
        selected = candidates[idx] if candidates else ""
        return selected, 1.0 / max(len(candidates), 1), alternatives

    def _least_loaded_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        load_counts = {m: self._telemetry.get(f"load_{m}", 0) for m in candidates}
        sorted_models = sorted(load_counts.keys(), key=lambda m: load_counts[m])
        self._telemetry[f"load_{sorted_models[0]}"] = self._telemetry.get(f"load_{sorted_models[0]}", 0) + 1
        alternatives = [{"model_id": m, "load": load_counts[m]} for m in sorted_models]
        return sorted_models[0], 1.0 / max(len(candidates), 1), alternatives

    def _context_aware_strategy(self, rule: RoutingRule, candidates: list[str], context: dict) -> tuple:
        input_length = context.get("input_length", 0)
        requires_vision = context.get("requires_vision", rule.require_vision)
        requires_tools = context.get("requires_tools", rule.require_tool_calling)
        scored = []
        for model in candidates:
            score = 1.0
            if input_length > 100000:
                scores = self._model_scores.get(model, [])
                cscore = sum(s.context_window if hasattr(s, "context_window") else 100000 for s in scores) / max(len(scores), 1) if scores else 100000
                capacity = min(1.0, 100000 / max(input_length, 1))
                score *= capacity
            alternatives = [{"model_id": m, "context_score": s} for m, s in scored] if scored else []
            scored.append((model, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        best = scored[0] if scored else (candidates[0], 0)
        alternatives = [{"model_id": m, "context_score": s} for m, s in scored]
        return best[0], best[1], alternatives

    def get_router_metrics(self) -> RouterMetrics:
        self._telemetry["get_router_metrics_calls"] += 1
        return self._metrics

    def get_route_history(self, limit: int = 100) -> list[RoutingDecision]:
        self._telemetry["get_route_history_calls"] += 1
        return list(self._decisions[-limit:])

    def add_model_score(self, score: ModelScore) -> None:
        self._model_scores[score.model_id].append(score)
        self._save()

    def get_model_scores(self, model_id: str) -> list[ModelScore]:
        return list(self._model_scores.get(model_id, []))


class FallbackChain:
    def __init__(self, name: str = "default"):
        self.name = name
        self._chain: list[str] = []
        self._cursor: int = 0
        self._telemetry: dict[str, int] = defaultdict(int)

    def set_chain(self, models: list[str]) -> None:
        self._telemetry["set_chain_calls"] += 1
        self._chain = list(models)
        self._cursor = 0
        logger.info("Fallback chain '%s' set with %d models", self.name, len(models))

    def get_next(self) -> Optional[str]:
        self._telemetry["get_next_calls"] += 1
        if self._cursor >= len(self._chain):
            return None
        model = self._chain[self._cursor]
        self._cursor += 1
        return model

    def reset_chain(self) -> None:
        self._cursor = 0
        self._telemetry["reset_chain_calls"] += 1

    def add_fallback(self, model: str, position: Optional[int] = None) -> None:
        self._telemetry["add_fallback_calls"] += 1
        if position is not None:
            self._chain.insert(position, model)
        else:
            self._chain.append(model)
        logger.info("Added fallback '%s' to chain '%s'", model, self.name)

    def remove_fallback(self, model: str) -> bool:
        self._telemetry["remove_fallback_calls"] += 1
        if model in self._chain:
            self._chain.remove(model)
            self._cursor = min(self._cursor, len(self._chain))
            logger.info("Removed fallback '%s' from chain '%s'", model, self.name)
            return True
        return False

    def get_chain_status(self) -> dict:
        return {
            "name": self.name,
            "chain": list(self._chain),
            "cursor": self._cursor,
            "remaining": max(0, len(self._chain) - self._cursor),
            "total": len(self._chain),
            "telemetry": dict(self._telemetry),
        }


class WeightedRouter:
    def __init__(self, name: str = "default"):
        self.name = name
        self._weights: dict[str, float] = {}
        self._telemetry: dict[str, int] = defaultdict(int)

    def set_weights(self, weights: dict[str, float]) -> None:
        self._telemetry["set_weights_calls"] += 1
        self._weights = dict(weights)
        self.normalize_weights()
        logger.info("Set weights for %d models in router '%s'", len(weights), self.name)

    def get_weights(self) -> dict[str, float]:
        self._telemetry["get_weights_calls"] += 1
        return dict(self._weights)

    def update_weights(self, model_id: str, weight: float) -> None:
        self._telemetry["update_weights_calls"] += 1
        self._weights[model_id] = max(0.0, weight)
        self.normalize_weights()

    def normalize_weights(self) -> None:
        total = sum(self._weights.values())
        if total > 0:
            for k in self._weights:
                self._weights[k] = round(self._weights[k] / total, 6)
        elif self._weights:
            n = len(self._weights)
            for k in self._weights:
                self._weights[k] = round(1.0 / n, 6)


class RoutingManager(ModelRouter, FallbackChain, WeightedRouter):
    def __init__(self, storage_dir: str = "router_data"):
        ModelRouter.__init__(self, storage_dir=storage_dir)
        FallbackChain.__init__(self, name="global")
        WeightedRouter.__init__(self, name="global")

    def handle_request(self, task_type: TaskType, request_id: str, context: Optional[dict] = None) -> RoutingDecision:
        self._telemetry["handle_request_calls"] += 1
        context = context or {}
        if context.get("strategy") == RoutingStrategy.FALLBACK_CHAIN:
            self.set_chain(context.get("fallback_models", []))
            model = self.get_next()
            if not model and self._chain:
                context["strategy"] = RoutingStrategy.FALLBACK_CHAIN
            context["models"] = [model] if model else context.get("models", [])

        if context.get("weights"):
            self.set_weights(context["weights"])
            context["weighted_models"] = self.get_weights()

        decision = self.route(task_type, request_id, context)
        return decision

    def get_routing_suggestion(self, task_type: TaskType, context: Optional[dict] = None) -> dict:
        self._telemetry["get_routing_suggestion_calls"] += 1
        context = context or {}
        rule = self._find_rule_for_task(task_type)
        if not rule:
            return {"suggestion": "No routing rule configured", "task_type": task_type.value}
        suggestion = {
            "task_type": task_type.value,
            "strategy": rule.strategy.value,
            "recommended_models": rule.models[:3] if rule.models else [],
            "fallback_available": len(rule.fallback_models) > 0,
            "constraints": {
                "min_accuracy": rule.min_accuracy,
                "max_cost": "unlimited" if math.isinf(rule.max_cost) else rule.max_cost,
                "max_latency_ms": "unlimited" if math.isinf(rule.max_latency_ms) else rule.max_latency_ms,
            },
        }
        if context.get("input_length"):
            suggestion["estimated_best_model"] = rule.models[0] if rule.models else None
        return suggestion

    def auto_optimize_routing(self, task_type: TaskType, metric_focus: str = "latency") -> dict:
        self._telemetry["auto_optimize_routing_calls"] += 1
        rule = self._find_rule_for_task(task_type)
        if not rule:
            return {"success": False, "error": f"No rule found for {task_type.value}"}

        strategy_map = {
            "latency": RoutingStrategy.LATENCY_OPTIMAL,
            "cost": RoutingStrategy.COST_OPTIMAL,
            "accuracy": RoutingStrategy.ACCURACY_OPTIMAL,
            "balanced": RoutingStrategy.WEIGHTED,
        }
        new_strategy = strategy_map.get(metric_focus, RoutingStrategy.WEIGHTED)
        rule.strategy = new_strategy
        rule.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()

        history = self.get_route_history(50)
        relevant = [d for d in history if d.task_type == task_type]
        avg_lat = sum(d.latency_ms for d in relevant) / max(len(relevant), 1) if relevant else 0

        return {
            "success": True,
            "task_type": task_type.value,
            "previous_strategy": rule.strategy.value,
            "new_strategy": new_strategy.value,
            "optimization_focus": metric_focus,
            "avg_latency_ms": round(avg_lat, 2),
            "routes_analyzed": len(relevant),
        }
