"""Compliance Intelligence — regulatory compliance scanning for GDPR, SOC2, HIPAA, PCI-DSS, CCPA."""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ComplianceFinding:
    file: str
    line: int
    regulation: str  # GDPR, SOC2, HIPAA, PCI-DSS, CCPA
    category: str
    severity: str  # critical, high, medium, low, info
    description: str
    recommendation: str
    code_snippet: str = ""


@dataclass
class ComplianceReport:
    repo_id: str
    repo_name: str
    timestamp: str
    findings: list[ComplianceFinding] = field(default_factory=list)
    regulation_summary: dict[str, dict] = field(default_factory=dict)
    risk_score: float = 0.0
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0
    critical_risk_count: int = 0
    regulations_checked: list[str] = field(default_factory=list)
    overall_compliance_pct: float = 0.0


class ComplianceIntelligence:
    """Scans codebases for regulatory compliance risks across major frameworks."""

    REGULATIONS = ["GDPR", "SOC2", "HIPAA", "PCI-DSS", "CCPA"]

    # (pattern, category, severity, recommendation)
    RULES: dict[str, list[tuple[str, str, str, str]]] = {
        "GDPR": [
            (r"log\.\w+\(.*(?:email|ssn|address|phone|credit_card|passport)", "PII_LOGGING",
             "critical", "Do not log personal data. Use anonymization or masking."),
            (r"(?:cookie|tracking|analytics).*consent|cookie.*banner|gdpr.*banner",
             "CONSENT", "info", "Verify cookie consent mechanism covers all tracking."),
            (r"(?:right.to.be.forgotten|data.deletion|delete.*user.*data)",
             "DATA_DELETION", "info", "Ensure right-to-erasure endpoint exists."),
            (r"(?:data.*portability|export.*user.*data|download.*my.*data)",
             "DATA_PORTABILITY", "info", "Ensure data portability endpoint exists."),
            (r"(?:privacy.*policy|privacy.*notice|data.*protection)",
             "PRIVACY_POLICY", "info", "Verify privacy policy is linked and up-to-date."),
            (r"processing.*(?:personal|sensitive).*data|data.*processing.*(?:lawful|basis)",
             "PROCESSING_BASIS", "medium", "Document lawful basis for data processing."),
            (r"(?:encrypt|hash).*(?:password|pii|personal|sensitive)",
             "ENCRYPTION", "medium", "Data at rest should be encrypted."),
            (r"(?:data.*breach|breach.*notification|notify.*authority)",
             "BREACH_NOTIFICATION", "high", "Ensure breach notification procedure exists."),
            (r"(?:dpo|data.protection.officer)",
             "DPO", "medium", "Verify Data Protection Officer contact is published."),
            (r"consent.*(?:opt.?in|opt.?out|withdraw|revoke)",
             "CONSENT_MGMT", "medium", "Ensure consent withdrawal mechanism exists."),
        ],
        "SOC2": [
            (r"log\.\w+\(.*(?:password|secret|token|key|credential)",
             "CREDENTIAL_LOGGING", "critical", "Never log credentials. Implement secret scanning."),
            (r"(?:access.*control|auth|authorization|permission|role|rbac)",
             "ACCESS_CONTROL", "high", "Verify access control is implemented and tested."),
            (r"(?:audit.*log|audit.*trail|audit_log|change.*log)",
             "AUDIT_TRAIL", "medium", "Ensure audit logging tracks all access to sensitive data."),
            (r"(?:monitor|alert|detect|anomaly|intrusion)",
             "MONITORING", "medium", "Verify monitoring and alerting for security events."),
            (r"(?:backup|recovery|disaster.*recovery|redundancy)",
             "AVAILABILITY", "medium", "Ensure backup and disaster recovery procedures exist."),
            (r"(?:encryption|tls|ssl|https|cipher)",
             "ENCRYPTION", "high", "Verify encryption in transit and at rest."),
            (r"(?:vendor|third.?party|supplier|subprocessor)",
             "VENDOR_MGMT", "low", "Document third-party vendor risk assessments."),
            (r"(?:incident.*response|security.*incident|incident.*plan)",
             "INCIDENT_RESPONSE", "high", "Ensure incident response plan is documented and tested."),
            (r"(?:change.*management|change.*control|change.*review)",
             "CHANGE_MGMT", "medium", "Verify change management process covers system changes."),
            (r"(?:risk.*assessment|risk.*register|risk.*review)",
             "RISK_MGMT", "medium", "Document risk assessment and treatment process."),
        ],
        "HIPAA": [
            (r"log\.\w+\(.*(?:phi|ehi|health|medical|diagnosis|treatment|patient)",
             "PHI_LOGGING", "critical", "Never log Protected Health Information."),
            (r"(?:breech|breech.*notification|hiva|hitech)",
             "BREACH_NOTIFICATION", "critical", "HIPAA requires breach notification within 60 days."),
            (r"(?:baa|business.*associate.*agreement)",
             "BAA", "high", "Verify Business Associate Agreements are in place."),
            (r"(?:access.*control|unique.*user.*id|emergency.*access)",
             "ACCESS_CONTROL", "high", "Implement unique user IDs and emergency access procedures."),
            (r"(?:audit.*control|audit.*log|access.*log|activity.*log)",
             "AUDIT_CONTROLS", "high", "Audit logs must record all PHI access."),
            (r"(?:integrity.*control|data.*integrity|hash|checksum)",
             "INTEGRITY_CONTROLS", "medium", "Implement integrity controls to prevent PHI alteration."),
            (r"(?:transmission.*security|encrypt|tls|https|cipher)",
             "TRANSMISSION_SECURITY", "critical", "All PHI in transit must be encrypted."),
            (r"(?:authentication|multi.?factor|mfa|2fa)",
             "AUTHENTICATION", "high", "Implement strong authentication for PHI access."),
            (r"(?:sanction.*policy|sanction|disciplinary)",
             "SANCTION_POLICY", "medium", "Document sanction policy for policy violations."),
            (r"(?:contingency.*plan|disaster.*recovery|emergency.*mode)",
             "CONTINGENCY_PLAN", "high", "Implement contingency plan for emergencies."),
        ],
        "PCI-DSS": [
            (r"(?:credit_card|cc_number|card_number|pan|cardholder)",
             "CARDHOLDER_DATA", "critical", "NEVER store full PAN, CVV, or track data unless tokenized."),
            (r"(?:tokenization|tokenize|detokenize|vault)",
             "TOKENIZATION", "medium", "Verify tokenization solution is in place."),
            (r"(?:encrypt.*(?:card|pan|cc)|card.*encrypt)",
             "ENCRYPTION", "critical", "Cardholder data must be encrypted at rest."),
            (r"(?:cvv|cvc|cvv2|cid|card.*code)",
             "CVV_STORAGE", "critical", "Never store CVV/CVC after authorization."),
            (r"(?:firewall|network.*segment|vlan|dmz)",
             "FIREWALL", "high", "Verify firewall and network segmentation."),
            (r"(?:access.*control|auth|role.*based|least.*privilege)",
             "ACCESS_CONTROL", "high", "Implement least privilege for cardholder data access."),
            (r"(?:logging|log.*review|log.*monitor)",
             "LOGGING", "medium", "Ensure logging covers all access to cardholder data."),
            (r"(?:scan|vulnerability.*scan|pen.?test|penetration)",
             "SCANNING", "high", "Quarterly ASV scans and annual penetration tests required."),
            (r"(?:patch|update|version.*security|vulnerability.*management)",
             "PATCH_MGMT", "medium", "Implement vulnerability management and patching program."),
            (r"(?:policy|security.*policy|information.*security.*policy)",
             "SECURITY_POLICY", "medium", "Document and maintain security policies."),
        ],
        "CCPA": [
            (r"log\.\w+\(.*(?:email|ssn|address|phone)",
             "PII_LOGGING_CCPA", "high", "Avoid logging consumer personal information."),
            (r"(?:right.to.know|data.*access|access.*request)",
             "RIGHT_TO_KNOW", "medium", "Ensure right-to-know endpoint exists for consumers."),
            (r"(?:right.to.delete|delete.*request|opt.?out.*sale)",
             "RIGHT_TO_DELETE", "medium", "CCPA requires data deletion and opt-out of sale."),
            (r"(?:opt.?out|do.not.sell|donot.sell)",
             "OPT_OUT", "high", "Verify 'Do Not Sell My Personal Information' mechanism exists."),
            (r"(?:non.?discrimination|equal.*service|price.*difference)",
             "NON_DISCRIMINATION", "medium", "Ensure no discrimination against exercising CCPA rights."),
            (r"(?:privacy.*notice|privacy.*policy|collection.*notice)",
             "PRIVACY_NOTICE", "medium", "Verify privacy notice meets CCPA disclosure requirements."),
            (r"(?:service.*provider|third.?party|contractor)",
             "SERVICE_PROVIDER", "low", "Document all service providers with access to PI."),
            (r"(?:data.*portability|portable.*format)",
             "DATA_PORTABILITY", "medium", "CCPA requires data portability in readily usable format."),
            (r"(?:consent|notice.*at.*collection|collection.*notice)",
             "CONSENT", "medium", "Verify notice at collection is implemented."),
            (r"(?:minor|under.*16|child.*data|children.*data)",
             "MINOR_CONSENT", "high", "CCPA has special rules for consumers under 16."),
        ],
    }

    @staticmethod
    def scan_repository(repo_path: str) -> ComplianceReport:
        path = Path(repo_path)
        report = ComplianceReport(
            repo_id=str(hash(str(path))),
            repo_name=path.name,
            timestamp=datetime.now(timezone.utc).isoformat(),
            regulations_checked=ComplianceIntelligence.REGULATIONS.copy(),
        )

        for file_path in sorted(path.rglob("*")):
            if not file_path.is_file() or any(
                p.startswith(".") or p in ("node_modules", "__pycache__", ".git", "venv", ".venv")
                for p in file_path.parts
            ):
                continue

            ext = file_path.suffix.lower()
            if ext not in (".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java",
                           ".rb", ".php", ".yaml", ".yml", ".json", ".tf", ".vue"):
                continue

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            rel_path = str(file_path.relative_to(path))

            for regulation, rules in ComplianceIntelligence.RULES.items():
                for pattern, category, severity, recommendation in rules:
                    for match in re.finditer(pattern, content, re.IGNORECASE):
                        line_num = content[: match.start()].count("\n") + 1
                        start = max(0, match.start() - 40)
                        end = min(len(content), match.end() + 40)
                        snippet = content[start:end].replace("\n", " ")
                        report.findings.append(ComplianceFinding(
                            file=rel_path,
                            line=line_num,
                            regulation=regulation,
                            category=category,
                            severity=severity,
                            description=f"[{regulation}] {category.replace('_', ' ').title()}",
                            recommendation=recommendation,
                            code_snippet=snippet.strip(),
                        ))

        # Deduplicate findings at file+line+category level
        seen = set()
        unique_findings = []
        for f in report.findings:
            key = (f.file, f.line, f.regulation, f.category)
            if key not in seen:
                seen.add(key)
                unique_findings.append(f)
        report.findings = unique_findings

        # Build regulation summary
        for reg in ComplianceIntelligence.REGULATIONS:
            reg_findings = [f for f in report.findings if f.regulation == reg]
            categories = defaultdict(list)
            for f in reg_findings:
                categories[f.category].append(f.severity)
            report.regulation_summary[reg] = {
                "total_findings": len(reg_findings),
                "categories": dict(categories),
                "severity_counts": {
                    "critical": sum(1 for f in reg_findings if f.severity == "critical"),
                    "high": sum(1 for f in reg_findings if f.severity == "high"),
                    "medium": sum(1 for f in reg_findings if f.severity == "medium"),
                    "low": sum(1 for f in reg_findings if f.severity == "low"),
                    "info": sum(1 for f in reg_findings if f.severity == "info"),
                },
            }

        report.critical_risk_count = sum(1 for f in report.findings if f.severity == "critical")
        report.high_risk_count = sum(1 for f in report.findings if f.severity == "high")
        report.medium_risk_count = sum(1 for f in report.findings if f.severity == "medium")
        report.low_risk_count = sum(1 for f in report.findings if f.severity == "low")

        total_findings = len(report.findings)
        if total_findings > 0:
            weighted = (
                report.critical_risk_count * 10 +
                report.high_risk_count * 5 +
                report.medium_risk_count * 2 +
                report.low_risk_count * 1
            )
            report.risk_score = min(100, weighted / max(total_findings, 1) * 10)
            report.overall_compliance_pct = max(0, 100 - report.risk_score)
        else:
            report.risk_score = 0.0
            report.overall_compliance_pct = 100.0

        return report


compliance_intelligence = ComplianceIntelligence()
