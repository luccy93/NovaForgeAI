"""10x Enhanced service layer for Volume 27 — Security & Compliance."""
import logging, asyncio
from ..common.services import AsyncService, registry
from ..common.base import Validator
from ..common.storage import JsonFileStorage
from . import security_policy, vulnerability_management, identity_management
from . import compliance_framework, audit_logging, threat_detection, encryption_engine
from . import secret_management, access_control, security_scanning, incident_response
from . import security_analytics, network_security, application_security
from . import enterprise_compliance, global_standards, auto_remediation
from . import security_orchestration, ai_threat_hunting, security_reporting
from . import observability

logger = logging.getLogger(__name__)


class SecurityService(AsyncService):
    def __init__(self):
        super().__init__("security_compliance", JsonFileStorage("data/security/service.json"))
        self.policy = security_policy.SecurityPolicy("data/security/policies")
        self.vuln = vulnerability_management.VulnerabilityManagement("data/security/vulns")
        self.identity = identity_management.IdentityManagement("data/security/identities")
        self.compliance = compliance_framework.ComplianceFramework("data/security/compliance")
        self.audit = audit_logging.AuditLogging("data/security/audit")
        self.threat = threat_detection.ThreatDetection("data/security/threats")
        self.encryption = encryption_engine.EncryptionEngine()
        self.secrets = secret_management.SecretManagement("data/security/secrets")
        self.acl = access_control.AccessControl("data/security/acl")
        self.scanner = security_scanning.SecurityScanning("data/security/scans")
        self.incident = incident_response.IncidentResponse("data/security/incidents")
        self.analytics = security_analytics.SecurityAnalytics("data/security/analytics")
        self.network = network_security.NetworkSecurity("data/security/network")
        self.appsec = application_security.ApplicationSecurity("data/security/appsec")
        self.ent_compliance = enterprise_compliance.EnterpriseCompliance("data/security/ent_compliance")
        self.standards = global_standards.GlobalStandards("data/security/standards")
        self.remediation = auto_remediation.AutoRemediation("data/security/remediation")
        self.soar = security_orchestration.SecurityOrchestration("data/security/soar")
        self.hunting = ai_threat_hunting.AIThreatHunting("data/security/hunting")
        self.reporting = security_reporting.SecurityReporting("data/security/reports")
        self.obs = observability.SecurityObservability("data/security/observability")

    async def scan_repository(self, org_id: str, repo_id: str, scan_type: str = "full"):
        scan = self.scanner.scan(repo_id, scan_type)
        findings = self.scanner.get_findings(scan.id) if hasattr(self.scanner, "get_findings") else []
        vulns_count = len([f for f in findings if f.get("severity") in ("critical", "high")])
        if vulns_count > 0:
            self.telemetry.increment("vulnerabilities_found", vulns_count)
            asyncio.create_task(self._auto_remediate(org_id, scan.id, findings))
        self.telemetry.increment("scans_run")
        return {"scan_id": scan.id, "findings": len(findings), "vulnerabilities": vulns_count}

    async def _auto_remediate(self, org_id: str, scan_id: str, findings: list):
        for finding in findings[:5]:
            if finding.get("severity") == "critical":
                self.remediation.remediate(scan_id, finding.get("id"))
                self.telemetry.increment("auto_remediated")

    async def health_check(self) -> dict:
        return self.health()


svc = SecurityService()
registry.register(svc)
