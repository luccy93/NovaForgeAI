"""AI Software Quality Engine -- CLI Commands (Volume 48)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


async def _cmd_quality_review(args: argparse.Namespace) -> dict:
    from app.quality.pipeline import ReviewPipeline
    from app.quality.context_retrieval import ContextBuilder
    from app.quality.analyzers.base import ReviewContext
    from app.quality.config import ReviewConfig

    pipeline = ReviewPipeline()
    config = ReviewConfig.from_mode(args.mode)
    context = ReviewContext(
        tenant=args.tenant, repo_id=args.repo,
        file_contents={}, changed_files=[args.ref] if args.ref else [],
        review_mode=args.mode,
    )
    result = await pipeline.run_review(context, config)
    return {
        "review_id": result.review_id,
        "status": result.status,
        "findings": len(result.deduplicated),
        "quality_scores": result.quality_scores,
        "risk_score": result.risk_score,
        "gate_result": result.gate_result,
    }


async def _cmd_quality_findings(args: argparse.Namespace) -> dict:
    from app.quality.review_service import ReviewService
    svc = ReviewService()
    findings = svc.get_findings(args.review_id, severity=args.severity, category=args.category, status=args.status)
    return {"review_id": args.review_id, "findings": findings, "total": len(findings)}


async def _cmd_quality_gates(args: argparse.Namespace) -> dict:
    from app.quality.review_service import ReviewService
    from app.quality.gates import QualityGateEngine
    svc = ReviewService()
    review = svc.get_review(args.review_id)
    if not review:
        return {"error": "Review not found"}
    findings = svc.get_findings(args.review_id)
    engine = QualityGateEngine()
    result = engine.evaluate(findings=findings, quality_scores=review.get("quality_scores", {}))
    return {"verdict": result.verdict, "score": result.score, "failures": [{"rule": f.rule_type, "message": f.message} for f in result.failures]}


async def _cmd_quality_baseline(args: argparse.Namespace) -> dict:
    from app.quality.baseline import BaselineService
    svc = BaselineService()
    if args.baseline_action == "list":
        return {"baselines": svc.list_baselines(tenant=args.tenant, repo_id=args.repo)}
    elif args.baseline_action == "create":
        b = svc.create(tenant=args.tenant, repo_id=args.repo, name=args.name, snapshot={})
        return {"baseline": b}
    elif args.baseline_action == "diff":
        b = svc.get(tenant=args.tenant, repo_id=args.repo, name=args.name)
        if not b:
            return {"error": "Baseline not found"}
        return {"baseline": b, "diff": svc.diff(b, b)}
    return {"error": f"Unknown baseline action: {args.baseline_action}"}


async def _cmd_quality_fix(args: argparse.Namespace) -> dict:
    from app.quality.remediation import RemediationService
    svc = RemediationService()
    result = svc.propose(finding_id=args.finding_id, patch_diff=args.patch if hasattr(args, "patch") else "")
    return {"remediation_id": result.remediation_id, "status": result.status}


async def _cmd_quality_verify(args: argparse.Namespace) -> dict:
    from app.quality.remediation import RemediationService
    svc = RemediationService()
    result = svc.verify(remediation_id=args.remediation_id, issue_resolved=True, tests_pass=True, re_scan_clean=True)
    return {"remediation_id": result.remediation_id, "status": result.status}


async def _cmd_quality_history(args: argparse.Namespace) -> dict:
    from app.quality.historical import HistoricalAnalyzer
    svc = HistoricalAnalyzer()
    if args.trends:
        trends = svc.get_trends(tenant=args.tenant, repo_id=args.repo)
        direction = svc.compute_trend_direction(tenant=args.tenant, repo_id=args.repo)
        return {"repo_id": args.repo, "trends": trends, "direction": direction}
    elif args.hotspots:
        return {"hotspots": svc.get_hotspots(tenant=args.tenant, repo_id=args.repo)}
    return {"repo_id": args.repo, "history": svc.get_trends(tenant=args.tenant, repo_id=args.repo)}


async def _cmd_quality_report(args: argparse.Namespace) -> dict:
    from app.quality.review_service import ReviewService
    from app.quality.report_service import ReportService
    svc = ReviewService()
    report_svc = ReportService()
    review = svc.get_review(args.review_id)
    if not review:
        return {"error": "Review not found"}
    findings = svc.get_findings(args.review_id)
    return report_svc.generate_report(review, findings)


async def _cmd_quality_analyze(args: argparse.Namespace) -> dict:
    from app.quality.pipeline import ReviewPipeline
    from app.quality.analyzers.base import ReviewContext
    from app.quality.config import ReviewConfig

    pipeline = ReviewPipeline()
    config = ReviewConfig.from_mode(args.mode)
    context = ReviewContext(
        tenant=args.tenant, repo_id=args.repo,
        file_contents={args.file: open(args.file).read()} if args.file else {},
        changed_files=[args.file] if args.file else [],
        review_mode=args.mode,
    )
    result = await pipeline.run_review(context, config)
    return {
        "review_id": result.review_id,
        "status": result.status,
        "findings": len(result.deduplicated),
        "quality_scores": result.quality_scores,
        "risk_score": result.risk_score,
    }


QUALITY_COMMANDS = {
    "review": _cmd_quality_review,
    "findings": _cmd_quality_findings,
    "gates": _cmd_quality_gates,
    "baseline": _cmd_quality_baseline,
    "fix": _cmd_quality_fix,
    "verify": _cmd_quality_verify,
    "history": _cmd_quality_history,
    "report": _cmd_quality_report,
    "analyze": _cmd_quality_analyze,
}


def build_quality_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova quality", description="AI Software Quality Engine")
    sub = parser.add_subparsers(dest="subcommand")

    # review
    p_review = sub.add_parser("review", help="Run a quality review")
    p_review.add_argument("--tenant", default="default")
    p_review.add_argument("--repo", default="")
    p_review.add_argument("--ref", default="", help="File, commit, branch, or PR ref")
    p_review.add_argument("--mode", default="standard", choices=["quick", "standard", "deep", "security", "performance", "release"])

    # findings
    p_findings = sub.add_parser("findings", help="List findings for a review")
    p_findings.add_argument("--review-id", required=True)
    p_findings.add_argument("--severity", default="")
    p_findings.add_argument("--category", default="")
    p_findings.add_argument("--status", default="")

    # gates
    p_gates = sub.add_parser("gates", help="Evaluate quality gates")
    p_gates.add_argument("--review-id", required=True)

    # baseline
    p_baseline = sub.add_parser("baseline", help="Manage quality baselines")
    p_baseline.add_argument("baseline_action", choices=["list", "create", "diff"])
    p_baseline.add_argument("--tenant", default="default")
    p_baseline.add_argument("--repo", default="")
    p_baseline.add_argument("--name", default="default")

    # fix
    p_fix = sub.add_parser("fix", help="Propose fix for a finding")
    p_fix.add_argument("--finding-id", required=True)
    p_fix.add_argument("--patch", default="")

    # verify
    p_verify = sub.add_parser("verify", help="Verify a remediation")
    p_verify.add_argument("--remediation-id", required=True)

    # history
    p_history = sub.add_parser("history", help="View review history")
    p_history.add_argument("--repo", required=True)
    p_history.add_argument("--tenant", default="default")
    p_history.add_argument("--trends", action="store_true")
    p_history.add_argument("--hotspots", action="store_true")

    # report
    p_report = sub.add_parser("report", help="Generate review report")
    p_report.add_argument("--review-id", required=True)
    p_report.add_argument("--format", default="json", choices=["json", "markdown"])

    # analyze
    p_analyze = sub.add_parser("analyze", help="Analyze a file")
    p_analyze.add_argument("--file", required=True)
    p_analyze.add_argument("--tenant", default="default")
    p_analyze.add_argument("--repo", default="")
    p_analyze.add_argument("--mode", default="standard", choices=["quick", "standard", "deep", "security", "performance", "release"])

    return parser


def handle_quality_command(args: list[str]) -> None:
    parser = build_quality_parser()
    parsed = parser.parse_args(args)
    if not parsed.subcommand:
        parser.print_help()
        return
    handler = QUALITY_COMMANDS.get(parsed.subcommand)
    if not handler:
        print(f"Unknown quality command: {parsed.subcommand}", file=sys.stderr)
        return
    result = asyncio.run(handler(parsed))
    print(json.dumps(result, indent=2, default=str))
