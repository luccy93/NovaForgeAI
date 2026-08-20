"""Unified DevSecOps Security Platform API (Volume 47).

30+ endpoints under /api/v1/security/ covering scans, findings,
secrets, SAST, dependencies, SBOM, IaC, containers, policies,
risk, supply chain, remediation, reports, and dashboard.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Request / Response models ──────────────────────────────────────────────

class ScanCreateRequest(BaseModel):
    tenant: str = "default"
    scan_type: str
    target_type: str
    target_id: str
    repository: str = ""
    branch: str = "main"
    commit_sha: str = ""


class FindingStatusUpdateRequest(BaseModel):
    status: str


class RiskAcceptRequest(BaseModel):
    authorized_by: str
    reason: str


class PolicyCreateRequest(BaseModel):
    tenant: str = "default"
    name: str
    description: str = ""
    policy_type: str = "gate"
    scope: str = "repository"
    conditions: dict = {}
    actions: dict = {"decision": "warn"}
    priority: int = 100


class PolicyEvaluateRequest(BaseModel):
    tenant: str = "default"
    target_type: str
    target_id: str
    findings: list[dict] = []


class ContentScanRequest(BaseModel):
    tenant: str = "default"
    content: str
    file_path: str = ""
    repository: str = ""
    branch: str = "main"
    commit_sha: str = ""


class SBOMGenerateRequest(BaseModel):
    tenant: str = "default"
    target_type: str
    target_id: str
    components: list[dict]
    repository: str = ""
    format: str = "cyclonedx"


class IaCScanRequest(BaseModel):
    tenant: str = "default"
    files: dict[str, str]
    repository: str = ""
    branch: str = "main"
    commit_sha: str = ""


class ContainerScanRequest(BaseModel):
    tenant: str = "default"
    image_name: str
    image_tag: str = "latest"
    packages: list[dict] = []
    dockerfile_content: str = ""


class PipelineScanRequest(BaseModel):
    tenant: str = "default"
    files: dict[str, str]
    repository: str = ""
    branch: str = "main"
    commit_sha: str = ""


class AgentMonitorRequest(BaseModel):
    tenant: str = "default"
    agent_id: str
    action_type: str
    action_data: dict = {}


class PluginValidateRequest(BaseModel):
    tenant: str = "default"
    plugin_name: str
    requested_permissions: list[str] = []


class MCPValidateRequest(BaseModel):
    tenant: str = "default"
    server_name: str
    config: dict = {}


class ReportRequest(BaseModel):
    tenant: str = "default"
    report_type: str = "executive"
    repository: str = ""
    branch: str = ""
    days: int = 30


class RemediateRequest(BaseModel):
    tenant: str = "default"
    finding_id: str
    approach: str = ""


class DashboardRequest(BaseModel):
    tenant: str = "default"
    days: int = 30


# ── Scans ──────────────────────────────────────────────────────────────────

@router.post("/scans")
async def create_scan(req: ScanCreateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.scan_service import scan_service
    scan = await scan_service.create_scan(db, **req.model_dump())
    await db.commit()
    return {"id": str(scan.id), "status": scan.status, "scan_type": scan.scan_type}


@router.get("/scans")
async def list_scans(
    tenant: str = Query("default"),
    scan_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
):
    from app.security.scan_service import scan_service
    scans = await scan_service.list_scans(db, tenant=tenant, scan_type=scan_type, status=status, limit=limit)
    return [{"id": str(s.id), "scan_type": s.scan_type, "status": s.status, "target_type": s.target_type, "target_id": s.target_id, "findings_count": s.findings_count} for s in scans]


@router.get("/scans/{scan_id}")
async def get_scan(scan_id: str, db: AsyncSession = Depends(get_db)):
    from app.security.scan_service import scan_service
    import uuid
    scan = await scan_service.get_scan(db, uuid.UUID(scan_id))
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {"id": str(scan.id), "scan_type": scan.scan_type, "status": scan.status, "target_type": scan.target_type, "target_id": scan.target_id, "findings_count": scan.findings_count, "duration_ms": scan.duration_ms, "summary": scan.summary}


# ── Findings ───────────────────────────────────────────────────────────────

@router.get("/findings")
async def list_findings(
    tenant: str = Query("default"),
    severity: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    repository: Optional[str] = Query(None),
    finding_type: Optional[str] = Query(None),
    limit: int = Query(50),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    from app.security.findings_service import findings_service
    findings = await findings_service.list_findings(db, tenant=tenant, severity=severity, status=status, source=source, repository=repository, finding_type=finding_type, limit=limit, offset=offset)
    return [{"id": str(f.id), "severity": f.severity, "status": f.status, "rule": f.rule, "message": f.message, "file_path": f.file_path, "risk_score": f.risk_score} for f in findings]


@router.get("/findings/summary")
async def findings_summary(tenant: str = Query("default"), db: AsyncSession = Depends(get_db)):
    from app.security.findings_service import findings_service
    return await findings_service.get_summary(db, tenant)


@router.post("/findings/{finding_id}/status")
async def update_finding_status(finding_id: str, req: FindingStatusUpdateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.findings_service import findings_service
    import uuid
    finding = await findings_service.update_status(db, uuid.UUID(finding_id), req.status)
    if not finding:
        raise HTTPException(status_code=404, detail="Finding not found")
    return {"id": str(finding.id), "status": finding.status}


@router.post("/findings/{finding_id}/accept-risk")
async def accept_risk(finding_id: str, req: RiskAcceptRequest, db: AsyncSession = Depends(get_db)):
    from app.security.findings_service import findings_service
    import uuid
    result = await findings_service.risk_accept(db, uuid.UUID(finding_id), req.authorized_by, req.reason)
    return result


# ── Secret Scanning ────────────────────────────────────────────────────────

@router.post("/secrets/scan")
async def scan_secrets(req: ContentScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.secret_scanner import secret_scanner
    findings = await secret_scanner.scan_content(db, tenant=req.tenant, content=req.content, file_path=req.file_path, repository=req.repository, branch=req.branch, commit_sha=req.commit_sha)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message, "file_path": f.file_path, "line_start": f.line_start} for f in findings]}


# ── SAST ───────────────────────────────────────────────────────────────────

@router.post("/sast/scan")
async def scan_sast(req: ContentScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.sast_scanner import sast_scanner
    findings = await sast_scanner.scan_content(db, tenant=req.tenant, content=req.content, file_path=req.file_path, repository=req.repository, branch=req.branch, commit_sha=req.commit_sha)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message, "file_path": f.file_path, "line_start": f.line_start} for f in findings]}


# ── Dependencies ───────────────────────────────────────────────────────────

@router.post("/dependencies/scan")
async def scan_dependencies(req: IaCScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.dependency_scanner import dependency_scanner
    findings = await dependency_scanner.scan_dependencies(db, tenant=req.tenant, files=req.files, repository=req.repository, branch=req.branch, commit_sha=req.commit_sha)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message, "dependency": f.dependency_name} for f in findings]}


# ── SBOM ───────────────────────────────────────────────────────────────────

@router.post("/sbom/generate")
async def generate_sbom(req: SBOMGenerateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.sbom_generator import sbom_service
    sbom = await sbom_service.generate_sbom(db, tenant=req.tenant, target_type=req.target_type, target_id=req.target_id, components=req.components, repository=req.repository, fmt=req.format)
    await db.commit()
    return {"id": str(sbom.id), "format": sbom.format, "component_count": sbom.component_count, "document_hash": sbom.document_hash}


@router.get("/sbom/list")
async def list_sboms(tenant: str = Query("default"), target_type: Optional[str] = Query(None), limit: int = Query(20), db: AsyncSession = Depends(get_db)):
    from app.security.sbom_generator import sbom_service
    sboms = await sbom_service.list_sboms(db, tenant=tenant, target_type=target_type, limit=limit)
    return [{"id": str(s.id), "target_type": s.target_type, "target_id": s.target_id, "format": s.format, "component_count": s.component_count} for s in sboms]


@router.get("/sbom/{sbom_id}")
async def get_sbom(sbom_id: str, db: AsyncSession = Depends(get_db)):
    from app.security.sbom_generator import sbom_service
    import uuid
    sbom = await sbom_service.get_sbom(db, uuid.UUID(sbom_id))
    if not sbom:
        raise HTTPException(status_code=404, detail="SBOM not found")
    return {"id": str(sbom.id), "format": sbom.format, "component_count": sbom.component_count, "vulnerability_count": sbom.vulnerability_count, "license_summary": sbom.license_summary}


@router.post("/sbom/{sbom_id}/verify")
async def verify_sbom(sbom_id: str, db: AsyncSession = Depends(get_db)):
    from app.security.sbom_generator import sbom_service
    import uuid
    return await sbom_service.verify_integrity(db, uuid.UUID(sbom_id))


# ── IaC ────────────────────────────────────────────────────────────────────

@router.post("/iac/scan")
async def scan_iac(req: IaCScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.iac_scanner import iac_scanner
    findings = await iac_scanner.scan_files(db, tenant=req.tenant, files=req.files, repository=req.repository, branch=req.branch, commit_sha=req.commit_sha)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message, "file_path": f.file_path} for f in findings]}


# ── Containers ─────────────────────────────────────────────────────────────

@router.post("/container/scan")
async def scan_container(req: ContainerScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.container_scanner import container_scanner
    findings = await container_scanner.scan_image(db, tenant=req.tenant, image_name=req.image_name, image_tag=req.image_tag, packages=req.packages, dockerfile_content=req.dockerfile_content)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message} for f in findings]}


# ── Policies ───────────────────────────────────────────────────────────────

@router.get("/policies")
async def list_policies(tenant: str = Query("default"), policy_type: Optional[str] = Query(None), db: AsyncSession = Depends(get_db)):
    from app.security.policy_service import policy_service
    policies = await policy_service.list_policies(db, tenant=tenant, policy_type=policy_type)
    return [{"id": str(p.id), "name": p.name, "policy_type": p.policy_type, "enabled": p.enabled, "priority": p.priority} for p in policies]


@router.post("/policies")
async def create_policy(req: PolicyCreateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.policy_service import policy_service
    policy = await policy_service.create_policy(db, **req.model_dump())
    await db.commit()
    return {"id": str(policy.id), "name": policy.name, "policy_type": policy.policy_type}


@router.post("/policies/evaluate")
async def evaluate_policies(req: PolicyEvaluateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.policy_service import policy_service
    result = await policy_service.evaluate(db, tenant=req.tenant, target_type=req.target_type, target_id=req.target_id, findings=req.findings)
    await db.commit()
    return result


# ── Risk ───────────────────────────────────────────────────────────────────

@router.get("/risk/summary")
async def risk_summary(tenant: str = Query("default"), db: AsyncSession = Depends(get_db)):
    from app.security.findings_service import findings_service
    summary = await findings_service.get_summary(db, tenant)
    total = summary["total"]
    sev = summary["by_severity"]
    risk_score = (sev.get("critical", 0) * 10 + sev.get("high", 0) * 7 + sev.get("medium", 0) * 4 + sev.get("low", 0) * 2) / max(total, 1)
    return {"total_findings": total, "by_severity": sev, "risk_score": round(risk_score, 2), "risk_level": "critical" if risk_score > 7 else "high" if risk_score > 4 else "medium" if risk_score > 2 else "low"}


@router.get("/risk/score")
async def risk_score(tenant: str = Query("default"), db: AsyncSession = Depends(get_db)):
    from app.security.findings_service import findings_service
    summary = await findings_service.get_summary(db, tenant)
    total = summary["total"]
    sev = summary["by_severity"]
    score = min(100, (sev.get("critical", 0) * 25 + sev.get("high", 0) * 15 + sev.get("medium", 0) * 5 + sev.get("low", 0) * 1) / max(total, 1) * 10)
    return {"score": round(score, 1), "level": "critical" if score > 75 else "high" if score > 50 else "medium" if score > 25 else "low"}


# ── Supply Chain ───────────────────────────────────────────────────────────

@router.get("/provenance/{chain_id}")
async def get_provenance(chain_id: str, tenant: str = Query("default"), db: AsyncSession = Depends(get_db)):
    from app.security.supply_chain_service import supply_chain_service
    chain = await supply_chain_service.get_provenance_chain(db, tenant, chain_id)
    return {"chain_id": chain_id, "records": [{"id": str(r.id), "source_type": r.source_type, "target_type": r.target_type, "relationship": r.relationship, "signed": r.signed} for r in chain]}


@router.post("/provenance/record")
async def record_provenance(req: dict, db: AsyncSession = Depends(get_db)):
    from app.security.supply_chain_service import supply_chain_service
    rec = await supply_chain_service.record_provenance(db, **req)
    await db.commit()
    return {"id": str(rec.id), "chain_id": rec.chain_id}


@router.post("/provenance/verify-slsa")
async def verify_slsa(chain_id: str, tenant: str = Query("default"), db: AsyncSession = Depends(get_db)):
    from app.security.supply_chain_service import supply_chain_service
    return await supply_chain_service.verify_slsa(db, tenant, chain_id)


# ── Remediation ────────────────────────────────────────────────────────────

@router.post("/remediate")
async def trigger_remediation(req: RemediateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.incident_service import incident_service
    import uuid
    remediation = await incident_service.create_remediation(db, tenant=req.tenant, finding_id=uuid.UUID(req.finding_id), approach=req.approach)
    await db.commit()
    return {"id": str(remediation.id), "status": remediation.status}


@router.get("/remediation/{remediation_id}")
async def get_remediation(remediation_id: str, db: AsyncSession = Depends(get_db)):
    from app.security.incident_service import incident_service
    import uuid
    rem = await incident_service.get_remediation(db, uuid.UUID(remediation_id))
    if not rem:
        raise HTTPException(status_code=404, detail="Remediation not found")
    return {"id": str(rem.id), "status": rem.status, "remediation_type": rem.remediation_type, "approach": rem.approach, "verified": rem.verified}


@router.get("/remediation")
async def list_remediations(tenant: str = Query("default"), status: Optional[str] = Query(None), limit: int = Query(20), db: AsyncSession = Depends(get_db)):
    from app.security.incident_service import incident_service
    rems = await incident_service.list_remediations(db, tenant=tenant, status=status, limit=limit)
    return [{"id": str(r.id), "status": r.status, "remediation_type": r.remediation_type, "finding_id": str(r.finding_id) if r.finding_id else None} for r in rems]


# ── CI/CD Security ─────────────────────────────────────────────────────────

@router.post("/cicd/scan")
async def scan_cicd(req: PipelineScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.ci_cd_security import ci_security_service
    findings = await ci_security_service.scan_pipeline_definitions(db, tenant=req.tenant, files=req.files, repository=req.repository, branch=req.branch, commit_sha=req.commit_sha)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message} for f in findings]}


# ── AI Security ────────────────────────────────────────────────────────────

@router.post("/ai/monitor")
async def monitor_agent(req: AgentMonitorRequest, db: AsyncSession = Depends(get_db)):
    from app.security.ai_security import ai_security_service
    findings = await ai_security_service.monitor_agent_action(db, tenant=req.tenant, agent_id=req.agent_id, action_type=req.action_type, action_data=req.action_data)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message} for f in findings]}


@router.post("/ai/prompt-injection/scan")
async def scan_prompt_injection(req: ContentScanRequest, db: AsyncSession = Depends(get_db)):
    from app.security.ai_security import ai_security_service
    findings = await ai_security_service.scan_for_prompt_injection(db, tenant=req.tenant, content=req.content, source_type="content", source_id=req.file_path)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity, "message": f.message} for f in findings]}


@router.post("/ai/command/classify")
async def classify_command(req: dict, db: AsyncSession = Depends(get_db)):
    from app.security.ai_security import ai_security_service
    return ai_security_service.classify_command(req.get("command", ""))


# ── Plugin Security ────────────────────────────────────────────────────────

@router.post("/plugin/validate")
async def validate_plugin(req: PluginValidateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.plugin_security import plugin_security_service
    findings = await plugin_security_service.validate_plugin_permissions(db, tenant=req.tenant, plugin_name=req.plugin_name, requested_permissions=req.requested_permissions)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity} for f in findings]}


@router.post("/plugin/mcp/validate")
async def validate_mcp(req: MCPValidateRequest, db: AsyncSession = Depends(get_db)):
    from app.security.plugin_security import plugin_security_service
    findings = await plugin_security_service.validate_mcp_server(db, tenant=req.tenant, server_name=req.server_name, config=req.config)
    await db.commit()
    return {"findings_count": len(findings), "findings": [{"id": str(f.id), "rule": f.rule, "severity": f.severity} for f in findings]}


# ── Reports ────────────────────────────────────────────────────────────────

@router.get("/reports/{report_type}")
async def get_report(report_type: str, tenant: str = Query("default"), repository: str = Query(""), days: int = Query(30), db: AsyncSession = Depends(get_db)):
    from app.security.report_service import report_service
    return await report_service.generate_report(db, tenant, report_type, repository=repository, days=days)


# ── Dashboard ──────────────────────────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(tenant: str = Query("default"), days: int = Query(30), db: AsyncSession = Depends(get_db)):
    from app.security.dashboard_service import dashboard_service
    return await dashboard_service.get_dashboard(db, tenant, days)


# ── Search ─────────────────────────────────────────────────────────────────

@router.get("/search")
async def security_search(
    tenant: str = Query("default"),
    q: str = Query(""),
    limit: int = Query(20),
    db: AsyncSession = Depends(get_db),
):
    from app.security.findings_service import findings_service
    from sqlalchemy import select, or_
    from app.security.models import SecurityFinding

    stmt = select(SecurityFinding).where(
        SecurityFinding.tenant == tenant,
        or_(
            SecurityFinding.message.ilike(f"%{q}%"),
            SecurityFinding.rule.ilike(f"%{q}%"),
            SecurityFinding.file_path.ilike(f"%{q}%"),
            SecurityFinding.cve_id.ilike(f"%{q}%"),
            SecurityFinding.dependency_name.ilike(f"%{q}%"),
        ),
    ).limit(limit)
    result = await db.execute(stmt)
    findings = list(result.scalars().all())
    return {"query": q, "count": len(findings), "results": [{"id": str(f.id), "severity": f.severity, "rule": f.rule, "message": f.message, "file_path": f.file_path} for f in findings]}
