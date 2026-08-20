"""AI Software Quality Engine -- Report Generation (Volume 48).

Generates review reports, PR summaries, and inline comments.
"""

from __future__ import annotations

from typing import Any


class ReportService:
    """Generate structured review reports from findings and scores."""

    def generate_report(
        self,
        review: dict[str, Any],
        findings: list[dict[str, Any]],
        gate_results: list[dict[str, Any]] | None = None,
        risk_assessment: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        severity_counts = self._count_by_severity(findings)
        category_counts = self._count_by_category(findings)
        inline_comments = self._build_inline_comments(findings)
        recommendations = self._generate_recommendations(findings, severity_counts)

        return {
            "review_id": review.get("id", ""),
            "summary": {
                "review_type": review.get("review_type", ""),
                "mode": review.get("mode", ""),
                "total_findings": review.get("total_findings", 0),
                "severity_breakdown": severity_counts,
                "category_breakdown": category_counts,
                "quality_scores": review.get("quality_scores", {}),
                "risk_score": review.get("risk_score", 0.0),
                "gate_passed": review.get("gate_passed"),
                "duration_ms": review.get("duration_ms", 0),
            },
            "findings": findings,
            "inline_comments": inline_comments,
            "quality_scores": review.get("quality_scores", {}),
            "gate_results": gate_results or [],
            "risk_assessment": risk_assessment or {},
            "recommendations": recommendations,
        }

    def generate_pr_summary(
        self,
        review: dict[str, Any],
        findings: list[dict[str, Any]],
    ) -> dict[str, Any]:
        severity_counts = self._count_by_severity(findings)
        categories = set(f.get("category", "") for f in findings)

        risk_level = "low"
        if severity_counts.get("critical", 0) > 0:
            risk_level = "critical"
        elif severity_counts.get("high", 0) > 0:
            risk_level = "high"
        elif severity_counts.get("medium", 0) > 0:
            risk_level = "medium"

        affected_files = list(set(f.get("file_path", "") for f in findings if f.get("file_path")))
        security_findings = [f for f in findings if f.get("category") == "security"]
        test_findings = [f for f in findings if f.get("category") == "testing"]

        parts = []
        if severity_counts.get("critical", 0):
            parts.append(f"{severity_counts['critical']} critical issue(s)")
        if severity_counts.get("high", 0):
            parts.append(f"{severity_counts['high']} high issue(s)")
        if severity_counts.get("medium", 0):
            parts.append(f"{severity_counts['medium']} medium issue(s)")

        what_changed = f"Changes in {len(affected_files)} file(s)" if affected_files else "No changes analyzed"
        security_status = f"{len(security_findings)} security finding(s)" if security_findings else "No security issues"
        tests_status = f"{len(test_findings)} test finding(s)" if test_findings else "No test issues"

        return {
            "review_id": review.get("id", ""),
            "what_changed": what_changed,
            "why_changed": review.get("metadata_extra", {}).get("description", ""),
            "risk_level": risk_level,
            "affected_components": affected_files[:10],
            "tests_status": tests_status,
            "security_status": security_status,
            "deployment_impact": self._assess_deployment_impact(severity_counts, categories),
            "findings_summary": {
                "total": len(findings),
                "by_severity": severity_counts,
                "by_category": self._count_by_category(findings),
            },
        }

    def build_inline_comments(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._build_inline_comments(findings)

    def _build_inline_comments(self, findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        comments = []
        for f in findings:
            if not f.get("file_path"):
                continue
            comments.append({
                "file": f.get("file_path", ""),
                "line": f.get("line_start", 0),
                "severity": f.get("severity", "info"),
                "finding": f.get("description", ""),
                "evidence": self._format_evidence(f.get("evidence", {})),
                "suggestion": f.get("suggestion", "") or f.get("recommendation", ""),
                "rule_id": f.get("rule_id", ""),
                "category": f.get("category", ""),
            })
        return sorted(comments, key=lambda c: (c["file"], c["line"]))

    def _format_evidence(self, evidence: dict[str, Any]) -> str:
        if not evidence:
            return ""
        parts = []
        for key, value in evidence.items():
            if isinstance(value, str):
                parts.append(f"{key}: {value}")
            elif isinstance(value, (int, float, bool)):
                parts.append(f"{key}: {value}")
        return "; ".join(parts) if parts else str(evidence)

    def _generate_recommendations(
        self, findings: list[dict[str, Any]], severity_counts: dict[str, int]
    ) -> list[str]:
        recs: list[str] = []
        if severity_counts.get("critical", 0) > 0:
            recs.append("Address critical findings before merge")
        if severity_counts.get("high", 0) > 2:
            recs.append("Review high-severity findings for blocking issues")
        categories = set(f.get("category", "") for f in findings)
        if "security" in categories:
            recs.append("Run security scan for detailed vulnerability analysis")
        if "testing" in categories:
            recs.append("Improve test coverage for changed code")
        if "architecture" in categories:
            recs.append("Review architectural implications of changes")
        if not recs:
            recs.append("No critical recommendations")
        return recs

    def _assess_deployment_impact(
        self, severity_counts: dict[str, int], categories: set[str]
    ) -> str:
        if severity_counts.get("critical", 0) > 0:
            return "BLOCK - Critical findings present"
        if "api_compat" in categories:
            return "HIGH - API compatibility changes detected"
        if "database" in categories:
            return "MEDIUM - Database changes require migration review"
        if severity_counts.get("high", 0) > 0:
            return "MEDIUM - High findings require attention"
        return "LOW - No deployment-blocking issues"

    def _count_by_severity(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            sev = f.get("severity", "info")
            counts[sev] = counts.get(sev, 0) + 1
        return counts

    def _count_by_category(self, findings: list[dict]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in findings:
            cat = f.get("category", "unknown")
            counts[cat] = counts.get(cat, 0) + 1
        return counts
