"""Data Governance module for NovaForge Data Platform & Knowledge Fabric (Volume 19)."""

import json, uuid, os, logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class DataGovernanceClassification(Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    REGULATED = "regulated"
    MASKED = "masked"


class DataGovernanceAction(Enum):
    MASK = "mask"
    ENCRYPT = "encrypt"
    REDACT = "redact"
    ANONYMIZE = "anonymize"
    PSEUDONYMIZE = "pseudonymize"
    LOG_ACCESS = "log_access"
    BLOCK_ACCESS = "block_access"
    ALLOW = "allow"


class DataGovernanceRuleType(Enum):
    CLASSIFICATION = "classification"
    OWNERSHIP = "ownership"
    RETENTION = "retention"
    PRIVACY = "privacy"
    MASKING = "masking"
    ENCRYPTION = "encryption"
    ACCESS_POLICY = "access_policy"
    AUDIT = "audit"


class DataGovernanceStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVIEW = "review"
    EXEMPTED = "exempted"
    VIOLATED = "violated"


@dataclass
class DataGovernanceRule:
    id: str
    org_id: str
    name: str
    rule_type: DataGovernanceRuleType = DataGovernanceRuleType.CLASSIFICATION
    classification: DataGovernanceClassification = DataGovernanceClassification.INTERNAL
    target_entity: str = ""
    target_field: str = ""
    action: DataGovernanceAction = DataGovernanceAction.LOG_ACCESS
    params: dict = field(default_factory=dict)
    priority: int = 0
    enabled: bool = True
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["rule_type"] = self.rule_type.value
        d["classification"] = self.classification.value
        d["action"] = self.action.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataGovernanceRule":
        data = data.copy()
        data["rule_type"] = DataGovernanceRuleType(data.get("rule_type", "classification"))
        data["classification"] = DataGovernanceClassification(data.get("classification", "internal"))
        data["action"] = DataGovernanceAction(data.get("action", "log_access"))
        return cls(**data)


@dataclass
class DataGovernancePolicy:
    id: str
    org_id: str
    name: str
    description: str = ""
    rules: list[str] = field(default_factory=list)
    scope: str = ""
    status: DataGovernanceStatus = DataGovernanceStatus.ACTIVE
    version: int = 1
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataGovernancePolicy":
        data = data.copy()
        data["status"] = DataGovernanceStatus(data.get("status", "active"))
        return cls(**data)


@dataclass
class DataAccessAudit:
    id: str
    org_id: str
    data_asset_id: str
    user_id: str
    action: str = ""
    classification: DataGovernanceClassification = DataGovernanceClassification.INTERNAL
    granted: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reason: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["classification"] = self.classification.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "DataAccessAudit":
        data = data.copy()
        data["classification"] = DataGovernanceClassification(data.get("classification", "internal"))
        return cls(**data)


@dataclass
class GovernanceComplianceReport:
    id: str
    org_id: str
    period_start: str = ""
    period_end: str = ""
    total_rules: int = 0
    rules_enforced: int = 0
    violations_detected: int = 0
    compliance_score: float = 1.0
    findings: list = field(default_factory=list)
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "GovernanceComplianceReport":
        return cls(**data)


class DataGovernance:
    def __init__(self, storage_dir: str = "governance_data"):
        self.storage_dir = storage_dir
        self._rules: dict[str, DataGovernanceRule] = {}
        self._policies: dict[str, DataGovernancePolicy] = {}
        self._audits: dict[str, DataAccessAudit] = {}
        self._reports: dict[str, GovernanceComplianceReport] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _rules_path(self) -> str:
        return os.path.join(self.storage_dir, "governance_rules.json")

    def _policies_path(self) -> str:
        return os.path.join(self.storage_dir, "governance_policies.json")

    def _audits_path(self) -> str:
        return os.path.join(self.storage_dir, "governance_audits.json")

    def _reports_path(self) -> str:
        return os.path.join(self.storage_dir, "governance_reports.json")

    def _save(self) -> None:
        try:
            rules_data = {rid: r.to_dict() for rid, r in self._rules.items()}
            with open(self._rules_path(), "w", encoding="utf-8") as f:
                json.dump(rules_data, f, indent=2, default=str)

            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            with open(self._policies_path(), "w", encoding="utf-8") as f:
                json.dump(policies_data, f, indent=2, default=str)

            audits_data = {aid: a.to_dict() for aid, a in self._audits.items()}
            with open(self._audits_path(), "w", encoding="utf-8") as f:
                json.dump(audits_data, f, indent=2, default=str)

            reports_data = {rid: r.to_dict() for rid, r in self._reports.items()}
            with open(self._reports_path(), "w", encoding="utf-8") as f:
                json.dump(reports_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save governance data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._rules_path()):
                with open(self._rules_path(), "r", encoding="utf-8") as f:
                    rules_data = json.load(f)
                for rid, data in rules_data.items():
                    try:
                        self._rules[rid] = DataGovernanceRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed rule %s: %s", rid, e)

            if os.path.exists(self._policies_path()):
                with open(self._policies_path(), "r", encoding="utf-8") as f:
                    policies_data = json.load(f)
                for pid, data in policies_data.items():
                    try:
                        self._policies[pid] = DataGovernancePolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed policy %s: %s", pid, e)

            if os.path.exists(self._audits_path()):
                with open(self._audits_path(), "r", encoding="utf-8") as f:
                    audits_data = json.load(f)
                for aid, data in audits_data.items():
                    try:
                        self._audits[aid] = DataAccessAudit.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed audit %s: %s", aid, e)

            if os.path.exists(self._reports_path()):
                with open(self._reports_path(), "r", encoding="utf-8") as f:
                    reports_data = json.load(f)
                for rid, data in reports_data.items():
                    try:
                        self._reports[rid] = GovernanceComplianceReport.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed report %s: %s", rid, e)
        except Exception as e:
            logger.error("Failed to load governance data: %s", e, exc_info=True)

    def create_rule(self, rule: DataGovernanceRule) -> DataGovernanceRule:
        self._telemetry["create_rule_calls"] += 1
        if not rule.id:
            rule.id = str(uuid.uuid4())
        if not rule.created_at:
            rule.created_at = datetime.now(timezone.utc).isoformat()
        if not rule.updated_at:
            rule.updated_at = rule.created_at
        self._rules[rule.id] = rule
        self._save()
        logger.info("Created governance rule %s: %s (type=%s, classification=%s)", rule.id, rule.name, rule.rule_type.value, rule.classification.value)
        return rule

    def list_rules(self, org_id: str, rule_type: Optional[DataGovernanceRuleType] = None) -> list[DataGovernanceRule]:
        self._telemetry["list_rules_calls"] += 1
        results = [r for r in self._rules.values() if r.org_id == org_id]
        if rule_type:
            results = [r for r in results if r.rule_type == rule_type]
        return results

    def evaluate_rule(self, rule: DataGovernanceRule, data: dict) -> dict:
        self._telemetry["evaluate_rule_calls"] += 1
        data_classification = data.get("classification", "internal")
        try:
            record_class = DataGovernanceClassification(data_classification)
        except ValueError:
            record_class = DataGovernanceClassification.INTERNAL

        matches = record_class == rule.classification
        field_value = data.get(rule.target_field) if rule.target_field else None

        result = {
            "rule_id": rule.id,
            "rule_name": rule.name,
            "rule_type": rule.rule_type.value,
            "classification_match": matches,
            "target_field": rule.target_field,
            "field_value_present": field_value is not None,
            "action": rule.action.value,
            "action_applied": False,
            "details": [],
        }

        if not matches:
            result["action"] = DataGovernanceAction.ALLOW.value
            result["details"].append(f"Data classification '{data_classification}' does not match rule classification '{rule.classification.value}'; no action taken")
            return result

        if rule.rule_type == DataGovernanceRuleType.CLASSIFICATION:
            result["details"].append(f"Data classified as {rule.classification.value}")
            result["action_applied"] = True

        elif rule.rule_type == DataGovernanceRuleType.MASKING:
            if field_value is not None:
                masked = str(field_value)
                if len(masked) > 4:
                    masked = masked[:2] + "*" * (len(masked) - 4) + masked[-2:]
                else:
                    masked = "****"
                result["masked_value"] = masked
                result["action_applied"] = True
                result["details"].append(f"Masked field '{rule.target_field}' ({rule.classification.value})")

        elif rule.rule_type == DataGovernanceRuleType.ENCRYPTION:
            if field_value is not None:
                result["encrypted"] = True
                result["action_applied"] = True
                result["details"].append(f"Encrypted field '{rule.target_field}'")

        elif rule.rule_type == DataGovernanceRuleType.ACCESS_POLICY:
            required_role = rule.params.get("required_role", "admin")
            user_role = data.get("user_role", "")
            has_access = user_role == required_role or user_role in rule.params.get("allowed_roles", [])
            if has_access:
                result["action"] = DataGovernanceAction.ALLOW.value
                result["action_applied"] = True
                result["details"].append(f"Access granted: user_role='{user_role}' matches required_role='{required_role}'")
            else:
                result["action"] = DataGovernanceAction.BLOCK_ACCESS.value
                result["action_applied"] = True
                result["details"].append(f"Access denied: user_role='{user_role}' does not match required_role='{required_role}'")

        elif rule.rule_type == DataGovernanceRuleType.AUDIT:
            result["action"] = DataGovernanceAction.LOG_ACCESS.value
            result["action_applied"] = True
            result["details"].append(f"Audit log triggered for {rule.classification.value} data")

        elif rule.rule_type == DataGovernanceRuleType.PRIVACY:
            if rule.action == DataGovernanceAction.ANONYMIZE:
                result["action_applied"] = True
                result["details"].append(f"Anonymized fields per privacy rule '{rule.name}'")
            elif rule.action == DataGovernanceAction.PSEUDONYMIZE:
                result["action_applied"] = True
                result["details"].append(f"Pseudonymized fields per privacy rule '{rule.name}'")
            elif rule.action == DataGovernanceAction.REDACT:
                result["action_applied"] = True
                result["details"].append(f"Redacted fields per privacy rule '{rule.name}'")

        else:
            result["action_applied"] = True
            result["details"].append(f"Rule '{rule.name}' ({rule.rule_type.value}) applied (default)")

        return result

    def create_policy(self, policy: DataGovernancePolicy) -> DataGovernancePolicy:
        self._telemetry["create_policy_calls"] += 1
        if not policy.id:
            policy.id = str(uuid.uuid4())
        if not policy.created_at:
            policy.created_at = datetime.now(timezone.utc).isoformat()
        if not policy.updated_at:
            policy.updated_at = policy.created_at
        self._policies[policy.id] = policy
        self._save()
        logger.info("Created governance policy %s: %s (scope=%s, rules=%d)", policy.id, policy.name, policy.scope, len(policy.rules))
        return policy

    def list_policies(self, org_id: str) -> list[DataGovernancePolicy]:
        self._telemetry["list_policies_calls"] += 1
        return [p for p in self._policies.values() if p.org_id == org_id]

    def apply_policy(self, policy_id: str, data: dict) -> dict:
        self._telemetry["apply_policy_calls"] += 1
        policy = self._policies.get(policy_id)
        if not policy:
            return {
                "policy_id": policy_id,
                "policy_name": "unknown",
                "status": "error",
                "error": "Policy not found",
                "evaluations": [],
            }

        if policy.status != DataGovernanceStatus.ACTIVE:
            return {
                "policy_id": policy_id,
                "policy_name": policy.name,
                "status": policy.status.value,
                "error": f"Policy is {policy.status.value}, not active",
                "evaluations": [],
            }

        evaluations = []
        actions_taken = set()
        for rule_id in policy.rules:
            rule = self._rules.get(rule_id)
            if not rule or not rule.enabled:
                continue
            eval_result = self.evaluate_rule(rule, data)
            evaluations.append(eval_result)
            if eval_result.get("action_applied"):
                actions_taken.add(eval_result.get("action"))

        return {
            "policy_id": policy_id,
            "policy_name": policy.name,
            "scope": policy.scope,
            "status": "applied",
            "rules_evaluated": len(evaluations),
            "actions_taken": list(actions_taken),
            "evaluations": evaluations,
        }

    def log_access(self, audit: DataAccessAudit) -> DataAccessAudit:
        self._telemetry["log_access_calls"] += 1
        if not audit.id:
            audit.id = str(uuid.uuid4())
        if not audit.timestamp:
            audit.timestamp = datetime.now(timezone.utc).isoformat()
        self._audits[audit.id] = audit
        self._save()
        logger.info("Logged data access: asset=%s user=%s action=%s granted=%s", audit.data_asset_id, audit.user_id, audit.action, audit.granted)
        return audit

    def get_access_history(self, data_asset_id: str) -> list[DataAccessAudit]:
        self._telemetry["get_access_history_calls"] += 1
        results = [a for a in self._audits.values() if a.data_asset_id == data_asset_id]
        results.sort(key=lambda a: a.timestamp, reverse=True)
        return results

    def generate_compliance_report(self, org_id: str, start_date: str, end_date: str) -> GovernanceComplianceReport:
        self._telemetry["generate_compliance_report_calls"] += 1
        rules = self.list_rules(org_id)
        policies = self.list_policies(org_id)
        audits = [a for a in self._audits.values() if a.org_id == org_id]

        total_rules = len(rules)
        rules_enforced = sum(1 for r in rules if r.enabled)
        violations = [a for a in audits if not a.granted]
        violations_detected = len(violations)

        compliance_score = round(rules_enforced / max(total_rules, 1), 4)

        findings = []
        if violations:
            for v in violations[:10]:
                findings.append(f"Access violation: user={v.user_id} asset={v.data_asset_id} reason='{v.reason}'")
        inactive_policies = [p for p in policies if p.status != DataGovernanceStatus.ACTIVE]
        if inactive_policies:
            findings.append(f"{len(inactive_policies)} policies are not active (pending review or inactive)")
        if total_rules == 0:
            findings.append("No governance rules defined for this organization")

        report = GovernanceComplianceReport(
            id=str(uuid.uuid4()),
            org_id=org_id,
            period_start=start_date,
            period_end=end_date,
            total_rules=total_rules,
            rules_enforced=rules_enforced,
            violations_detected=violations_detected,
            compliance_score=compliance_score,
            findings=findings,
        )
        self._reports[report.id] = report
        self._save()
        logger.info("Generated compliance report %s for org %s (score=%s, violations=%d)", report.id, org_id, compliance_score, violations_detected)
        return report

    def get_telemetry(self) -> dict:
        self._telemetry["get_telemetry_calls"] += 1
        return dict(self._telemetry)
