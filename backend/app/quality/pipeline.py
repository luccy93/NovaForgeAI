"""AI Software Quality Engine -- Main Review Pipeline (Volume 48).

Orchestrates the full review pipeline:
Code/PR → Context → Change Analysis → Parallel Analyzers → Correlation → Gates → Report
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from app.quality.analyzers import get_analyzers
from app.quality.analyzers.base import AnalyzerResult, ReviewContext
from app.quality.baseline import BaselineService
from app.quality.config import CATEGORY_WEIGHTS, ReviewConfig
from app.quality.correlation import FindingCorrelator
from app.quality.dedup import FindingDeduplicator
from app.quality.finding_model import FindingData
from app.quality.gates import QualityGateEngine
from app.quality.risk_scorer import RiskScorer
from app.quality.review_service import ReviewService


@dataclass
class PipelineResult:
    review_id: str
    status: str
    findings: list[dict[str, Any]] = field(default_factory=list)
    deduplicated: list[dict[str, Any]] = field(default_factory=list)
    correlated: list[dict[str, Any]] = field(default_factory=list)
    quality_scores: dict[str, float] = field(default_factory=dict)
    risk_score: float = 0.0
    gate_result: dict[str, Any] = field(default_factory=dict)
    analyzer_results: list[dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    error: str | None = None


class ReviewPipeline:
    """Main orchestrator for quality reviews."""

    def __init__(self):
        self.review_service = ReviewService()
        self.risk_scorer = RiskScorer()
        self.deduplicator = FindingDeduplicator()
        self.correlator = FindingCorrelator()
        self.gate_engine = QualityGateEngine()
        self.baseline_service = BaselineService()

    async def run_review(
        self,
        context: ReviewContext,
        config: ReviewConfig | None = None,
        gate_rules: list[dict[str, Any]] | None = None,
    ) -> PipelineResult:
        start_time = time.monotonic()
        if config is None:
            config = ReviewConfig.from_mode(context.review_mode)

        review = self.review_service.create_review(
            tenant=context.tenant,
            repo_id=context.repo_id,
            review_type="file" if len(context.changed_files) <= 1 else "branch",
            target_ref=", ".join(context.changed_files[:5]),
            mode=config.mode,
        )
        review_id = review["id"]

        try:
            self.review_service.transition(review_id, "analyzing")

            if gate_rules:
                self.gate_engine = QualityGateEngine(gate_rules)

            analyzer_results = await self._run_analyzers(context, config)

            all_findings_data: list[FindingData] = []
            for result in analyzer_results:
                all_findings_data.extend(result.findings)

            all_findings_dicts = [f.to_dict() for f in all_findings_data]

            dedup_groups = self.deduplicator.deduplicate(all_findings_dicts)
            deduped = self.deduplicator.to_dicts(dedup_groups)

            correlated = self.correlator.correlate(deduped)

            self.review_service.add_findings(review_id, deduped)

            quality_scores = self._compute_quality_scores(deduped)
            risk_result = self.risk_scorer.score_findings(deduped)
            risk_score = risk_result.score

            gate_result = self.gate_engine.evaluate(
                findings=deduped,
                quality_scores={**quality_scores, "risk_score": risk_score},
            )

            self.review_service.set_quality_scores(review_id, quality_scores)
            self.review_service.set_risk_score(review_id, risk_score)
            self.review_service.set_gate_passed(review_id, gate_result.verdict == "pass")

            final_status = "completed"
            if gate_result.verdict == "block":
                final_status = "blocked"
            self.review_service.transition(review_id, final_status)

            duration_ms = int((time.monotonic() - start_time) * 1000)

            analyzer_summaries = [
                {
                    "name": r.analyzer_name,
                    "findings_count": len(r.findings),
                    "tokens_used": r.tokens_used,
                    "duration_ms": r.duration_ms,
                    "error": r.error,
                }
                for r in analyzer_results
            ]

            return PipelineResult(
                review_id=review_id,
                status=final_status,
                findings=all_findings_dicts,
                deduplicated=deduped,
                correlated=[
                    {
                        "group_id": c.group_id,
                        "categories": c.categories,
                        "combined_severity": c.combined_severity,
                        "combined_confidence": c.combined_confidence,
                        "description": c.description,
                        "cascading_risk": c.cascading_risk,
                    }
                    for c in correlated
                ],
                quality_scores=quality_scores,
                risk_score=risk_score,
                gate_result={
                    "verdict": gate_result.verdict,
                    "score": gate_result.score,
                    "failures": [
                        {"rule": f.rule_type, "message": f.message}
                        for f in gate_result.failures
                    ],
                },
                analyzer_results=analyzer_summaries,
                duration_ms=duration_ms,
            )

        except Exception as e:
            self.review_service.transition(review_id, "failed")
            review = self.review_service.get_review(review_id)
            if review:
                review["error"] = str(e)
            duration_ms = int((time.monotonic() - start_time) * 1000)
            return PipelineResult(
                review_id=review_id,
                status="failed",
                duration_ms=duration_ms,
                error=str(e),
            )

    async def _run_analyzers(
        self, context: ReviewContext, config: ReviewConfig
    ) -> list[AnalyzerResult]:
        analyzers = get_analyzers(config.analyzers)
        if not analyzers:
            return []

        results: list[AnalyzerResult] = []
        tasks = []
        for analyzer in analyzers:
            tasks.append(self._run_single_analyzer(analyzer, context))

        done = await asyncio.gather(*tasks, return_exceptions=True)
        for item in done:
            if isinstance(item, Exception):
                results.append(AnalyzerResult(
                    analyzer_name="unknown", error=str(item),
                ))
            elif isinstance(item, AnalyzerResult):
                results.append(item)
        return results

    async def _run_single_analyzer(
        self, analyzer: Any, context: ReviewContext
    ) -> AnalyzerResult:
        try:
            return await analyzer.analyze(context)
        except Exception as e:
            return AnalyzerResult(
                analyzer_name=analyzer.name, error=str(e),
            )

    def _compute_quality_scores(self, findings: list[dict[str, Any]]) -> dict[str, float]:
        scores: dict[str, float] = {}
        for category, weight in CATEGORY_WEIGHTS.items():
            cat_findings = [f for f in findings if f.get("category") == category]
            if not cat_findings:
                scores[category] = 1.0
                continue
            critical = sum(1 for f in cat_findings if f.get("severity") == "critical")
            high = sum(1 for f in cat_findings if f.get("severity") == "high")
            medium = sum(1 for f in cat_findings if f.get("severity") == "medium")
            penalty = critical * 0.3 + high * 0.15 + medium * 0.05
            scores[category] = max(0.0, 1.0 - penalty)

        overall = sum(
            scores.get(cat, 1.0) * w
            for cat, w in CATEGORY_WEIGHTS.items()
        )
        scores["overall"] = round(overall, 4)
        return scores
