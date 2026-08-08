import json
import uuid
import os
import re
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class SecurityPolicyType(Enum):
    MFA = "mfa"
    PASSWORD = "password"
    SESSION = "session"
    DEVICE_TRUST = "device_trust"
    SECRET_ROTATION = "secret_rotation"
    ENCRYPTION = "encryption"
    BACKUP = "backup"
    INCIDENT_ESCALATION = "incident_escalation"
    NETWORK_SECURITY = "network_security"
    ACCESS_CONTROL = "access_control"


class MfaMethod(Enum):
    TOTP = "totp"
    SMS = "sms"
    EMAIL = "email"
    HARDWARE_KEY = "hardware_key"
    PUSH_NOTIFICATION = "push_notification"
    BIOMETRIC = "biometric"


class PasswordComplexity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class EncryptionStandard(Enum):
    AES_256 = "aes_256"
    AES_128 = "aes_128"
    RSA_2048 = "rsa_2048"
    RSA_4096 = "rsa_4096"
    ECC = "ecc"
    CHACHA20 = "chacha20"


class SessionPolicy(Enum):
    PER_USER = "per_user"
    PER_DEVICE = "per_device"
    SINGLE_SESSION = "single_session"
    CONCURRENT_LIMITED = "concurrent_limited"


@dataclass
class SecurityPolicy:
    id: str
    org_id: str
    name: str
    policy_type: SecurityPolicyType = SecurityPolicyType.ACCESS_CONTROL
    enabled: bool = True
    priority: int = 0
    requirements: dict = field(default_factory=dict)
    exceptions: list = field(default_factory=list)
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["policy_type"] = self.policy_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityPolicy":
        data["policy_type"] = SecurityPolicyType(data["policy_type"])
        return cls(**data)


@dataclass
class MfaPolicy:
    id: str
    org_id: str
    name: str
    required: bool = True
    methods: list[MfaMethod] = field(default_factory=lambda: [MfaMethod.TOTP])
    grace_period_days: int = 7
    enforce_for_roles: list = field(default_factory=list)
    exempt_roles: list = field(default_factory=list)
    remember_device_days: int = 30
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["methods"] = [m.value for m in self.methods]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "MfaPolicy":
        data["methods"] = [MfaMethod(m) for m in data["methods"]]
        return cls(**data)


@dataclass
class PasswordPolicy:
    id: str
    org_id: str
    name: str
    complexity: PasswordComplexity = PasswordComplexity.MEDIUM
    min_length: int = 8
    max_length: int = 128
    require_uppercase: bool = True
    require_lowercase: bool = True
    require_numbers: bool = True
    require_special: bool = False
    expiry_days: int = 90
    prevent_reuse_count: int = 5
    max_login_attempts: int = 5
    lockout_duration_minutes: int = 30
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["complexity"] = self.complexity.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "PasswordPolicy":
        data["complexity"] = PasswordComplexity(data["complexity"])
        return cls(**data)


@dataclass
class EncryptionPolicy:
    id: str
    org_id: str
    name: str
    standard: EncryptionStandard = EncryptionStandard.AES_256
    key_rotation_days: int = 365
    encrypt_at_rest: bool = True
    encrypt_in_transit: bool = True
    encrypt_backups: bool = True
    key_vault_provider: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["standard"] = self.standard.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EncryptionPolicy":
        data["standard"] = EncryptionStandard(data["standard"])
        return cls(**data)


@dataclass
class SecurityIncident:
    id: str
    org_id: str
    incident_type: str
    severity: str
    title: str
    description: str = ""
    affected_resources: list = field(default_factory=list)
    detected_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    reported_by: str = ""
    status: str = "open"
    assigned_to: str = ""
    resolution: str = ""
    resolved_at: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SecurityIncident":
        return cls(**data)


_COMPLEXITY_PATTERNS = {
    PasswordComplexity.LOW: {
        "min_length": 6,
        "require_uppercase": False,
        "require_lowercase": True,
        "require_numbers": False,
        "require_special": False,
    },
    PasswordComplexity.MEDIUM: {
        "min_length": 8,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_numbers": True,
        "require_special": False,
    },
    PasswordComplexity.HIGH: {
        "min_length": 12,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_numbers": True,
        "require_special": True,
    },
    PasswordComplexity.VERY_HIGH: {
        "min_length": 16,
        "require_uppercase": True,
        "require_lowercase": True,
        "require_numbers": True,
        "require_special": True,
    },
}


class SecurityGovernanceManager:
    def __init__(self, storage_dir: str = "security_governance_data"):
        self.storage_dir = storage_dir
        self._policies: dict[str, SecurityPolicy] = {}
        self._mfa_policies: dict[str, MfaPolicy] = {}
        self._password_policies: dict[str, PasswordPolicy] = {}
        self._encryption_policies: dict[str, EncryptionPolicy] = {}
        self._incidents: dict[str, SecurityIncident] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _policies_path(self) -> str:
        return os.path.join(self.storage_dir, "policies.json")

    def _mfa_policies_path(self) -> str:
        return os.path.join(self.storage_dir, "mfa_policies.json")

    def _password_policies_path(self) -> str:
        return os.path.join(self.storage_dir, "password_policies.json")

    def _encryption_policies_path(self) -> str:
        return os.path.join(self.storage_dir, "encryption_policies.json")

    def _incidents_path(self) -> str:
        return os.path.join(self.storage_dir, "incidents.json")

    def _save(self) -> None:
        try:
            policies_data = {pid: p.to_dict() for pid, p in self._policies.items()}
            with open(self._policies_path(), "w", encoding="utf-8") as f:
                json.dump(policies_data, f, indent=2, default=str)

            mfa_data = {mid: m.to_dict() for mid, m in self._mfa_policies.items()}
            with open(self._mfa_policies_path(), "w", encoding="utf-8") as f:
                json.dump(mfa_data, f, indent=2, default=str)

            password_data = {pid: p.to_dict() for pid, p in self._password_policies.items()}
            with open(self._password_policies_path(), "w", encoding="utf-8") as f:
                json.dump(password_data, f, indent=2, default=str)

            encryption_data = {eid: e.to_dict() for eid, e in self._encryption_policies.items()}
            with open(self._encryption_policies_path(), "w", encoding="utf-8") as f:
                json.dump(encryption_data, f, indent=2, default=str)

            incidents_data = {iid: i.to_dict() for iid, i in self._incidents.items()}
            with open(self._incidents_path(), "w", encoding="utf-8") as f:
                json.dump(incidents_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save security governance data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._policies_path()):
                with open(self._policies_path(), "r", encoding="utf-8") as f:
                    policies_data = json.load(f)
                for pid, data in policies_data.items():
                    try:
                        self._policies[pid] = SecurityPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed security policy %s: %s", pid, e)

            if os.path.exists(self._mfa_policies_path()):
                with open(self._mfa_policies_path(), "r", encoding="utf-8") as f:
                    mfa_data = json.load(f)
                for mid, data in mfa_data.items():
                    try:
                        self._mfa_policies[mid] = MfaPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed MFA policy %s: %s", mid, e)

            if os.path.exists(self._password_policies_path()):
                with open(self._password_policies_path(), "r", encoding="utf-8") as f:
                    password_data = json.load(f)
                for pid, data in password_data.items():
                    try:
                        self._password_policies[pid] = PasswordPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed password policy %s: %s", pid, e)

            if os.path.exists(self._encryption_policies_path()):
                with open(self._encryption_policies_path(), "r", encoding="utf-8") as f:
                    encryption_data = json.load(f)
                for eid, data in encryption_data.items():
                    try:
                        self._encryption_policies[eid] = EncryptionPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed encryption policy %s: %s", eid, e)

            if os.path.exists(self._incidents_path()):
                with open(self._incidents_path(), "r", encoding="utf-8") as f:
                    incidents_data = json.load(f)
                for iid, data in incidents_data.items():
                    try:
                        self._incidents[iid] = SecurityIncident.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed security incident %s: %s", iid, e)
        except Exception as e:
            logger.error("Failed to load security governance data: %s", e, exc_info=True)

    def create_security_policy(self, policy: SecurityPolicy) -> SecurityPolicy:
        self._telemetry["create_security_policy_calls"] += 1
        if policy.id in self._policies:
            raise ValueError(f"Security policy with id '{policy.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._policies[policy.id] = policy
        self._save()
        logger.info("Created security policy: %s (%s)", policy.name, policy.id)
        return policy

    def list_security_policies(self, org_id: str, policy_type: Optional[SecurityPolicyType] = None) -> list[SecurityPolicy]:
        self._telemetry["list_security_policies_calls"] += 1
        results = [p for p in self._policies.values() if p.org_id == org_id]
        if policy_type:
            results = [p for p in results if p.policy_type == policy_type]
        return results

    def set_mfa_policy(self, policy: MfaPolicy) -> MfaPolicy:
        self._telemetry["set_mfa_policy_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._mfa_policies[policy.org_id] = policy
        self._save()
        logger.info("Set MFA policy for org %s: %s", policy.org_id, policy.name)
        return policy

    def get_mfa_policy(self, org_id: str) -> Optional[MfaPolicy]:
        self._telemetry["get_mfa_policy_calls"] += 1
        return self._mfa_policies.get(org_id)

    def set_password_policy(self, policy: PasswordPolicy) -> PasswordPolicy:
        self._telemetry["set_password_policy_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._password_policies[policy.org_id] = policy
        self._save()
        logger.info("Set password policy for org %s: %s", policy.org_id, policy.name)
        return policy

    def get_password_policy(self, org_id: str) -> Optional[PasswordPolicy]:
        self._telemetry["get_password_policy_calls"] += 1
        return self._password_policies.get(org_id)

    def validate_password(self, org_id: str, password: str) -> dict:
        self._telemetry["validate_password_calls"] += 1
        policy = self.get_password_policy(org_id)
        if not policy:
            return {
                "valid": True,
                "errors": [],
                "warnings": ["No password policy configured for this organization."],
                "score": 0,
            }

        errors = []
        warnings = []
        score = 0

        if len(password) < policy.min_length:
            errors.append(f"Password must be at least {policy.min_length} characters long.")
        else:
            score += 1

        if policy.max_length > 0 and len(password) > policy.max_length:
            errors.append(f"Password must not exceed {policy.max_length} characters.")

        if policy.require_uppercase and not re.search(r"[A-Z]", password):
            errors.append("Password must contain at least one uppercase letter.")
        else:
            score += 1

        if policy.require_lowercase and not re.search(r"[a-z]", password):
            errors.append("Password must contain at least one lowercase letter.")
        else:
            score += 1

        if policy.require_numbers and not re.search(r"[0-9]", password):
            errors.append("Password must contain at least one number.")
        else:
            score += 1

        if policy.require_special and not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>\/?`~]", password):
            errors.append("Password must contain at least one special character.")
        else:
            score += 1

        complexity_defaults = _COMPLEXITY_PATTERNS.get(policy.complexity, _COMPLEXITY_PATTERNS[PasswordComplexity.MEDIUM])
        if policy.min_length < complexity_defaults["min_length"]:
            warnings.append(
                f"Consider increasing minimum password length to {complexity_defaults['min_length']} "
                f"for '{policy.complexity.value}' complexity level."
            )
        if policy.require_special and not complexity_defaults["require_special"]:
            warnings.append(f"Special characters are not required by '{policy.complexity.value}' complexity level.")

        max_score = 5
        score = min(score, max_score)

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "score": score,
            "max_score": max_score,
            "strength": "very_strong" if score >= 5 else "strong" if score >= 4 else "moderate" if score >= 3 else "weak",
        }

    def set_encryption_policy(self, policy: EncryptionPolicy) -> EncryptionPolicy:
        self._telemetry["set_encryption_policy_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._encryption_policies[policy.org_id] = policy
        self._save()
        logger.info("Set encryption policy for org %s: %s", policy.org_id, policy.name)
        return policy

    def get_encryption_policy(self, org_id: str) -> Optional[EncryptionPolicy]:
        self._telemetry["get_encryption_policy_calls"] += 1
        return self._encryption_policies.get(org_id)

    def report_incident(self, incident: SecurityIncident) -> SecurityIncident:
        self._telemetry["report_incident_calls"] += 1
        if incident.id in self._incidents:
            raise ValueError(f"Security incident with id '{incident.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        incident.created_at = now
        if not incident.detected_at:
            incident.detected_at = now
        self._incidents[incident.id] = incident
        self._save()
        logger.info("Reported security incident: %s (%s) - %s", incident.id, incident.severity, incident.title)
        return incident

    def get_incident(self, incident_id: str) -> Optional[SecurityIncident]:
        self._telemetry["get_incident_calls"] += 1
        return self._incidents.get(incident_id)

    def list_incidents(self, org_id: str, status: Optional[str] = None, severity: Optional[str] = None) -> list[SecurityIncident]:
        self._telemetry["list_incidents_calls"] += 1
        results = [i for i in self._incidents.values() if i.org_id == org_id]
        if status:
            results = [i for i in results if i.status == status]
        if severity:
            results = [i for i in results if i.severity == severity]
        return sorted(results, key=lambda i: i.detected_at, reverse=True)

    def get_security_score(self, org_id: str) -> float:
        self._telemetry["get_security_score_calls"] += 1
        score = 0.0
        max_score = 0.0
        weights = {
            "mfa": 25.0,
            "password": 20.0,
            "encryption": 20.0,
            "policies": 15.0,
            "incidents": 20.0,
        }

        max_score = sum(weights.values())

        mfa = self.get_mfa_policy(org_id)
        if mfa and mfa.required:
            score += weights["mfa"]
        elif mfa:
            score += weights["mfa"] * 0.5

        password = self.get_password_policy(org_id)
        if password:
            complexity_scores = {
                PasswordComplexity.LOW: 0.25,
                PasswordComplexity.MEDIUM: 0.5,
                PasswordComplexity.HIGH: 0.75,
                PasswordComplexity.VERY_HIGH: 1.0,
            }
            score += weights["password"] * complexity_scores.get(password.complexity, 0.5)

        encryption = self.get_encryption_policy(org_id)
        if encryption:
            enc_score = 0.0
            if encryption.encrypt_at_rest:
                enc_score += 0.4
            if encryption.encrypt_in_transit:
                enc_score += 0.4
            if encryption.encrypt_backups:
                enc_score += 0.2
            score += weights["encryption"] * enc_score

        org_policies = [p for p in self._policies.values() if p.org_id == org_id]
        if org_policies:
            enabled_count = sum(1 for p in org_policies if p.enabled)
            score += weights["policies"] * (enabled_count / len(org_policies))

        org_incidents = [i for i in self._incidents.values() if i.org_id == org_id]
        open_count = sum(1 for i in org_incidents if i.status == "open")
        unresolved_weight = 1.0 - (open_count / max(len(org_incidents), 1)) * 0.5
        score += weights["incidents"] * max(unresolved_weight, 0.0)

        final_score = round((score / max_score) * 100, 2) if max_score > 0 else 0.0
        return min(final_score, 100.0)

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
