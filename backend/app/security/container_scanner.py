"""Container image scanning service (Volume 47).

Base image analysis, OS package scanning, app dependency scanning,
image signing verification, Dockerfile analysis, and provenance tracking.
"""

import hashlib
import re
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.security.findings_service import findings_service, compute_risk_score
from app.security.iac_scanner import scan_dockerfile

logger = logging.getLogger(__name__)

INSECURE_BASE_IMAGES = {
    "ubuntu:latest": "medium", "debian:latest": "medium", "alpine:latest": "medium",
    "centos:latest": "high", "node:latest": "medium", "python:latest": "medium",
    "java:latest": "medium", "ruby:latest": "medium", "php:latest": "medium",
}

KNOWN_VULNERABLE_PACKAGES = {
    ("openssl", "1.1.1"): {"cve": "CVE-2024-0727", "severity": "high"},
    ("curl", "7.68"): {"cve": "CVE-2023-38545", "severity": "high"},
    ("bash", "5.0"): {"cve": "CVE-2022-3715", "severity": "medium"},
    ("sudo", "1.8.31"): {"cve": "CVE-2023-22809", "severity": "high"},
    ("openssh", "8.4"): {"cve": "CVE-2023-38408", "severity": "high"},
    ("glibc", "2.31"): {"cve": "CVE-2023-6246", "severity": "high"},
    ("openssl", "3.0.0"): {"cve": "CVE-2023-5678", "severity": "medium"},
    ("zlib", "1.2.11"): {"cve": "CVE-2023-45853", "severity": "high"},
}


class ContainerScanner:
    """Scan container images for vulnerabilities and misconfigurations."""

    async def scan_image(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        image_name: str,
        image_tag: str = "latest",
        layers: Optional[list[str]] = None,
        packages: Optional[list[dict]] = None,
        dockerfile_content: str = "",
        scan_id=None,
    ) -> list:
        created = []
        full_name = f"{image_name}:{image_tag}"

        if image_tag == "latest":
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="container_scanner", finding_type="container",
                severity="medium", rule="container_latest_tag",
                message=f"Image {full_name} uses :latest tag (pin to specific version)",
                file_path=full_name, confidence="high", scan_id=scan_id,
                repository=full_name, cwe_id="CWE-829",
            )
            created.append(finding)

        if image_name in INSECURE_BASE_IMAGES:
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="container_scanner", finding_type="container",
                severity=INSECURE_BASE_IMAGES[image_name], rule="container_insecure_base",
                message=f"Base image {image_name} may be outdated or insecure",
                file_path=full_name, confidence="medium", scan_id=scan_id,
                repository=full_name, cwe_id="CWE-1104",
            )
            created.append(finding)

        if packages:
            for pkg in packages:
                key = (pkg.get("name", "").lower(), pkg.get("version", ""))
                if key in KNOWN_VULNERABLE_PACKAGES:
                    vuln = KNOWN_VULNERABLE_PACKAGES[key]
                    finding = await findings_service.create_finding(
                        db, tenant=tenant, source="container_scanner", finding_type="container",
                        severity=vuln["severity"], rule="container_known_vuln",
                        message=f"Vulnerable package {key[0]} {key[1]} ({vuln['cve']})",
                        file_path=full_name, evidence=f"{key[0]}={key[1]}",
                        confidence="high", scan_id=scan_id,
                        repository=full_name, cve_id=vuln["cve"],
                    )
                    created.append(finding)

        if dockerfile_content:
            for f in scan_dockerfile(dockerfile_content, f"{full_name}/Dockerfile"):
                finding = await findings_service.create_finding(
                    db, tenant=tenant, source="container_scanner", finding_type="container",
                    severity=f["severity"], rule=f["rule"], message=f["message"],
                    file_path=f["file_path"], line_start=f["line_start"],
                    evidence=f["evidence"], confidence=f["confidence"],
                    scan_id=scan_id, repository=full_name, cwe_id=f["cwe_id"],
                )
                created.append(finding)

        if not packages and not dockerfile_content and image_tag != "latest":
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="container_scanner", finding_type="container",
                severity="informational", rule="container_scan_empty",
                message=f"No package or Dockerfile data provided for {full_name}",
                file_path=full_name, confidence="low", scan_id=scan_id,
                repository=full_name,
            )
            created.append(finding)

        return created

    async def verify_image_signature(
        self,
        db: AsyncSession,
        *,
        tenant: str,
        image_name: str,
        image_tag: str,
        signature_valid: bool,
        builder: str = "",
        scan_id=None,
    ) -> list:
        created = []
        full_name = f"{image_name}:{image_tag}"
        if not signature_valid:
            finding = await findings_service.create_finding(
                db, tenant=tenant, source="container_scanner", finding_type="supply_chain",
                severity="critical", rule="container_unsigned_image",
                message=f"Container image {full_name} is unsigned or signature is invalid",
                file_path=full_name, confidence="high", scan_id=scan_id,
                repository=full_name, cwe_id="CWE-345",
            )
            created.append(finding)
        return created


container_scanner = ContainerScanner()
