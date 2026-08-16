"""Evaluation reports (Volume 34).

Human-readable report generation from runs, comparisons, reviews and
gates. Plain-text + structured markdown so reports can be attached to CI
runs, PRs and dashboards without any UI changes.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class ReportBuilder:
    """Builds evaluation reports from stored artifacts."""

    def run_report(self, run: dict) -> dict:
        """Compact report for a single benchmark run."""
        metrics = run.get("metrics", {})
        return {
            "title": f"Benchmark {run.get('id')}",
            "run_id": run.get("id"),
            "dataset_id": run.get("dataset_id"),
            "dataset_version": run.get("dataset_version"),
            "model": run.get("model"),
            "provider": run.get("provider"),
            "status": run.get("status"),
            "overall": metrics.get("overall"),
            "pass_rate": metrics.get("pass_rate"),
            "correct_rate": metrics.get("correct_rate"),
            "examples": len(run.get("results", [])),
            "errors": len(run.get("errors", [])),
            "cost": run.get("cost"),
            "mean_latency_ms": metrics.get("mean_latency_ms"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def comparison_report(self, baseline: dict, candidate: dict,
                          deltas: dict, verdict: str = "") -> dict:
        """Side-by-side comparison report for a gate decision."""
        return {
            "title": "Run Comparison",
            "baseline": {"run_id": baseline.get("id"), "model": baseline.get("model"),
                         "overall": baseline.get("metrics", {}).get("overall"),
                         "pass_rate": baseline.get("metrics", {}).get("pass_rate"),
                         "cost": baseline.get("cost")},
            "candidate": {"run_id": candidate.get("id"), "model": candidate.get("model"),
                          "overall": candidate.get("metrics", {}).get("overall"),
                          "pass_rate": candidate.get("metrics", {}).get("pass_rate"),
                          "cost": candidate.get("cost")},
            "deltas": deltas,
            "verdict": verdict,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def markdown(self, report: dict) -> str:
        """Render a report dict as markdown for PR/CI attachments."""
        lines = [f"# {report.get('title', 'Evaluation Report')}"]
        lines.append("")
        for key, value in report.items():
            if key in ("title", "baseline", "candidate", "deltas"):
                continue
            if isinstance(value, dict):
                lines.append(f"**{key}**:")
                for k, v in value.items():
                    lines.append(f"  - {k}: {v}")
            else:
                lines.append(f"**{key}**: {value}")
        return "\n".join(lines)
