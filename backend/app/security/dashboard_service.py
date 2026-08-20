"""Security dashboard aggregation service (Volume 47).

Provides aggregated data for the existing security dashboard UI:
severity breakdown, finding trends, top risks, scan history,
gate status, and compliance score.
"""

import logging
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.security.models import SecurityFinding, SecurityScan, SecurityPolicy, SecurityPolicyEvaluation

logger = logging.getLogger(__name__)


class DashboardService:
    """Aggregate security metrics for the frontend dashboard."""

    async def get_dashboard(self, db: AsyncSession, tenant: str, days: int = 30) -> dict:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        severity_stmt = select(
            SecurityFinding.severity, func.count(SecurityFinding.id)
        ).where(and_(SecurityFinding.tenant == tenant, SecurityFinding.created_at >= cutoff))
        severity_stmt = severity_stmt.group_by(SecurityFinding.severity)
        severity_result = await db.execute(severity_stmt)
        severity_breakdown = {row[0]: row[1] for row in severity_result}

        status_stmt = select(
            SecurityFinding.status, func.count(SecurityFinding.id)
        ).where(and_(SecurityFinding.tenant == tenant, SecurityFinding.created_at >= cutoff))
        status_stmt = status_stmt.group_by(SecurityFinding.status)
        status_result = await db.execute(status_stmt)
        status_breakdown = {row[0]: row[1] for row in status_result}

        top_risks_stmt = (
            select(SecurityFinding)
            .where(and_(
                SecurityFinding.tenant == tenant,
                SecurityFinding.status.in_(["open", "acknowledged"]),
            ))
            .order_by(desc(SecurityFinding.risk_score))
            .limit(10)
        )
        top_risks_result = await db.execute(top_risks_stmt)
        top_risks = [
            {"id": str(f.id), "severity": f.severity, "rule": f.rule, "message": f.message, "risk_score": f.risk_score, "repository": f.repository}
            for f in top_risks_result.scalars().all()
        ]

        scans_stmt = (
            select(SecurityScan)
            .where(and_(SecurityScan.tenant == tenant, SecurityScan.created_at >= cutoff))
            .order_by(desc(SecurityScan.created_at))
            .limit(10)
        )
        scans_result = await db.execute(scans_stmt)
        scan_history = [
            {"id": str(s.id), "type": s.scan_type, "status": s.status, "target": s.target_id, "findings": s.findings_count, "duration_ms": s.duration_ms}
            for s in scans_result.scalars().all()
        ]

        gate_stmt = (
            select(SecurityPolicyEvaluation)
            .where(and_(SecurityPolicyEvaluation.tenant == tenant, SecurityPolicyEvaluation.created_at >= cutoff))
            .order_by(desc(SecurityPolicyEvaluation.created_at))
            .limit(20)
        )
        gate_result = await db.execute(gate_stmt)
        gate_evals = gate_result.scalars().all()
        gate_pass = sum(1 for g in gate_evals if g.decision == "allow")
        gate_total = len(gate_evals) or 1
        gate_status = {
            "pass_rate": round(gate_pass / gate_total * 100, 1),
            "total_evaluations": len(gate_evals),
            "blocked": sum(1 for g in gate_evals if g.decision == "block"),
            "warned": sum(1 for g in gate_evals if g.decision == "warn"),
            "passed": gate_pass,
        }

        total_findings = sum(severity_breakdown.values())
        critical_high = severity_breakdown.get("critical", 0) + severity_breakdown.get("high", 0)
        compliance_score = max(0, 100 - (critical_high * 5 + severity_breakdown.get("medium", 0) * 2))

        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period_days": days,
            "severity_breakdown": severity_breakdown,
            "status_breakdown": status_breakdown,
            "total_findings": total_findings,
            "top_risks": top_risks,
            "scan_history": scan_history,
            "gate_status": gate_status,
            "compliance_score": min(100, compliance_score),
            "summary": {
                "critical": severity_breakdown.get("critical", 0),
                "high": severity_breakdown.get("high", 0),
                "medium": severity_breakdown.get("medium", 0),
                "low": severity_breakdown.get("low", 0),
                "informational": severity_breakdown.get("informational", 0),
                "open": status_breakdown.get("open", 0),
                "fixed": status_breakdown.get("fixed", 0) + status_breakdown.get("verified", 0),
            },
        }


dashboard_service = DashboardService()
