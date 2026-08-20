"""NovaForge CLI -- Security platform commands (Volume 47)."""

import asyncio
import json
import os
import sys
from typing import Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


def _output_json(data, output: str = "table"):
    if output == "json":
        print(json.dumps(data, indent=2, default=str))
    else:
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    parts = [f"{k}={v}" for k, v in item.items()]
                    print("  ".join(parts))
                else:
                    print(item)
        elif isinstance(data, dict):
            for k, v in data.items():
                if isinstance(v, (dict, list)):
                    print(f"{k}: {json.dumps(v, default=str)}")
                else:
                    print(f"{k}: {v}")


async def _cmd_security_scan(args, output):
    from app.core.database import async_session_factory
    from app.security.scan_service import scan_service
    scan_type = args[0] if len(args) > 0 else "full"
    target_type = args[1] if len(args) > 1 else "repository"
    target_id = args[2] if len(args) > 2 else ""
    async with async_session_factory() as db:
        scan = await scan_service.create_scan(db, tenant="default", scan_type=scan_type, target_type=target_type, target_id=target_id)
        await db.commit()
        _output_json({"id": str(scan.id), "status": scan.status, "scan_type": scan.scan_type}, output)


async def _cmd_security_findings(args, output):
    from app.core.database import async_session_factory
    from app.security.findings_service import findings_service
    severity = None
    status = None
    for i, arg in enumerate(args):
        if arg == "--severity" and i + 1 < len(args):
            severity = args[i + 1]
        elif arg == "--status" and i + 1 < len(args):
            status = args[i + 1]
    async with async_session_factory() as db:
        findings = await findings_service.list_findings(db, tenant="default", severity=severity, status=status)
        _output_json([{"id": str(f.id), "severity": f.severity, "status": f.status, "rule": f.rule, "message": f.message[:80]} for f in findings], output)


async def _cmd_security_secrets(args, output):
    from app.core.database import async_session_factory
    from app.security.secret_scanner import secret_scanner
    repository = args[0] if args else ""
    async with async_session_factory() as db:
        findings = await secret_scanner.scan_content(db, tenant="default", content="PLACEHOLDER", file_path="<cli>", repository=repository)
        _output_json({"findings_count": len(findings)}, output)


async def _cmd_security_sbom(args, output):
    from app.core.database import async_session_factory
    from app.security.sbom_generator import sbom_service
    target_type = args[0] if len(args) > 0 else "repository"
    target_id = args[1] if len(args) > 1 else ""
    async with async_session_factory() as db:
        sbom = await sbom_service.generate_sbom(db, tenant="default", target_type=target_type, target_id=target_id, components=[])
        await db.commit()
        _output_json({"id": str(sbom.id), "format": sbom.format, "component_count": sbom.component_count}, output)


async def _cmd_security_dependencies(args, output):
    from app.core.database import async_session_factory
    from app.security.dependency_scanner import dependency_scanner
    async with async_session_factory() as db:
        findings = await dependency_scanner.scan_dependencies(db, tenant="default", files={})
        _output_json({"findings_count": len(findings)}, output)


async def _cmd_security_container(args, output):
    from app.core.database import async_session_factory
    from app.security.container_scanner import container_scanner
    image_name = args[0] if args else "unknown"
    image_tag = args[1] if len(args) > 1 else "latest"
    async with async_session_factory() as db:
        findings = await container_scanner.scan_image(db, tenant="default", image_name=image_name, image_tag=image_tag)
        await db.commit()
        _output_json({"findings_count": len(findings)}, output)


async def _cmd_security_iac(args, output):
    from app.core.database import async_session_factory
    from app.security.iac_scanner import iac_scanner
    path = args[0] if args else "."
    files = {}
    if os.path.isfile(path):
        with open(path) as f:
            files[os.path.basename(path)] = f.read()
    async with async_session_factory() as db:
        findings = await iac_scanner.scan_files(db, tenant="default", files=files)
        await db.commit()
        _output_json({"findings_count": len(findings)}, output)


async def _cmd_security_report(args, output):
    from app.core.database import async_session_factory
    from app.security.report_service import report_service
    report_type = args[0] if args else "executive"
    async with async_session_factory() as db:
        report = await report_service.generate_report(db, "default", report_type)
        _output_json(report, output)


async def _cmd_security_fix(args, output):
    from app.core.database import async_session_factory
    from app.security.incident_service import incident_service
    import uuid
    finding_id = args[0] if args else ""
    async with async_session_factory() as db:
        rem = await incident_service.create_remediation(db, tenant="default", finding_id=uuid.UUID(finding_id))
        await db.commit()
        _output_json({"id": str(rem.id), "status": rem.status}, output)


async def _cmd_security_risk(args, output):
    from app.core.database import async_session_factory
    from app.security.findings_service import findings_service
    async with async_session_factory() as db:
        summary = await findings_service.get_summary(db, "default")
        _output_json(summary, output)


async def _cmd_security_policies(args, output):
    from app.core.database import async_session_factory
    from app.security.policy_service import policy_service
    async with async_session_factory() as db:
        policies = await policy_service.list_policies(db, tenant="default")
        _output_json([{"id": str(p.id), "name": p.name, "policy_type": p.policy_type, "enabled": p.enabled} for p in policies], output)


async def _cmd_security_search(args, output):
    from app.core.database import async_session_factory
    from sqlalchemy import select, or_
    from app.security.models import SecurityFinding
    query = " ".join(args) if args else ""
    async with async_session_factory() as db:
        stmt = select(SecurityFinding).where(
            SecurityFinding.tenant == "default",
            or_(
                SecurityFinding.message.ilike(f"%{query}%"),
                SecurityFinding.rule.ilike(f"%{query}%"),
                SecurityFinding.cve_id.ilike(f"%{query}%"),
            ),
        ).limit(20)
        result = await db.execute(stmt)
        findings = list(result.scalars().all())
        _output_json([{"id": str(f.id), "severity": f.severity, "rule": f.rule, "message": f.message[:80]} for f in findings], output)


async def _cmd_security_dashboard(args, output):
    from app.core.database import async_session_factory
    from app.security.dashboard_service import dashboard_service
    async with async_session_factory() as db:
        data = await dashboard_service.get_dashboard(db, "default")
        _output_json(data, output)


SECURITY_COMMANDS = {
    "scan": _cmd_security_scan,
    "findings": _cmd_security_findings,
    "secrets": _cmd_security_secrets,
    "sbom": _cmd_security_sbom,
    "dependencies": _cmd_security_dependencies,
    "container": _cmd_security_container,
    "iac": _cmd_security_iac,
    "report": _cmd_security_report,
    "fix": _cmd_security_fix,
    "risk": _cmd_security_risk,
    "policies": _cmd_security_policies,
    "search": _cmd_security_search,
    "dashboard": _cmd_security_dashboard,
}


def handle_security_command(subcommand: str, args: list, output: str = "table"):
    if subcommand not in SECURITY_COMMANDS:
        print(f"Unknown security command: {subcommand}")
        print(f"Available: {', '.join(sorted(SECURITY_COMMANDS.keys()))}")
        return
    asyncio.run(SECURITY_COMMANDS[subcommand](args, output))


if __name__ == "__main__":
    subcmd = sys.argv[1] if len(sys.argv) > 1 else "findings"
    remaining = sys.argv[2:]
    output = "json" if "--output" in remaining else "table"
    remaining = [a for a in remaining if a != "--output" and a != "json"]
    handle_security_command(subcmd, remaining, output)
