"""
Cloud Security — Zero Trust, Network Isolation, Encryption, IAM, Secret Management, Audit Logs, Threat Detection.
"""
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
import json
import uuid
import hashlib
import time
import os
import base64
from collections import defaultdict

logger = logging.getLogger(__name__)


class SecurityPolicyType(Enum):
    ZERO_TRUST = "zero_trust"
    NETWORK_ISOLATION = "network_isolation"
    ENCRYPTION = "encryption"
    IAM = "iam"
    SECRET_MANAGEMENT = "secret_management"
    AUDIT = "audit"
    THREAT_DETECTION = "threat_detection"
    COMPLIANCE = "compliance"


class EncryptionAlgorithm(Enum):
    AES256_GCM = "aes256_gcm"
    AES256_CBC = "aes256_cbc"
    CHACHA20_POLY1305 = "chacha20_poly1305"
    RSA_OAEP = "rsa_oaep"
    ECC = "ecc"


class AccessLevel(Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"


class ThreatSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class IAMPolicy:
    id: str
    name: str
    org_id: str
    workspace_id: Optional[str] = None
    effect: str = "allow"
    actions: list = field(default_factory=list)
    resources: list = field(default_factory=list)
    conditions: dict = field(default_factory=dict)
    priority: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "effect": self.effect,
            "actions": self.actions,
            "resources": self.resources,
            "conditions": self.conditions,
            "priority": self.priority,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IAMPolicy":
        return cls(
            id=data["id"],
            name=data["name"],
            org_id=data["org_id"],
            workspace_id=data.get("workspace_id"),
            effect=data.get("effect", "allow"),
            actions=data.get("actions", []),
            resources=data.get("resources", []),
            conditions=data.get("conditions", {}),
            priority=data.get("priority", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


@dataclass
class IAMRole:
    id: str
    name: str
    org_id: str
    policies: list = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "org_id": self.org_id,
            "policies": self.policies,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IAMRole":
        return cls(
            id=data["id"],
            name=data["name"],
            org_id=data["org_id"],
            policies=data.get("policies", []),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class IAMBinding:
    id: str
    role_id: str
    user_id: str
    resource_type: str
    resource_id: str
    access_level: AccessLevel = AccessLevel.READ
    granted_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role_id": self.role_id,
            "user_id": self.user_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "access_level": self.access_level.value,
            "granted_at": self.granted_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IAMBinding":
        return cls(
            id=data["id"],
            role_id=data["role_id"],
            user_id=data["user_id"],
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            access_level=AccessLevel(data.get("access_level", "read")),
            granted_at=datetime.fromisoformat(data["granted_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
        )


@dataclass
class Secret:
    id: str
    name: str
    key: str
    value: str
    org_id: str
    workspace_id: Optional[str] = None
    environment: str = "production"
    rotation_period_days: int = 90
    last_rotated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    encrypted: bool = True
    version: int = 1

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "key": self.key,
            "value": self.value,
            "org_id": self.org_id,
            "workspace_id": self.workspace_id,
            "environment": self.environment,
            "rotation_period_days": self.rotation_period_days,
            "last_rotated": self.last_rotated.isoformat(),
            "created_at": self.created_at.isoformat(),
            "encrypted": self.encrypted,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Secret":
        return cls(
            id=data["id"],
            name=data["name"],
            key=data["key"],
            value=data["value"],
            org_id=data["org_id"],
            workspace_id=data.get("workspace_id"),
            environment=data.get("environment", "production"),
            rotation_period_days=data.get("rotation_period_days", 90),
            last_rotated=datetime.fromisoformat(data["last_rotated"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            encrypted=data.get("encrypted", True),
            version=data.get("version", 1),
        )


@dataclass
class AuditLogEntry:
    id: str
    timestamp: datetime
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    details: dict = field(default_factory=dict)
    ip_address: str = ""
    user_agent: str = ""
    status: str = "success"
    org_id: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "actor_id": self.actor_id,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "details": self.details,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
            "status": self.status,
            "org_id": self.org_id,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AuditLogEntry":
        return cls(
            id=data["id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            actor_id=data["actor_id"],
            action=data["action"],
            resource_type=data["resource_type"],
            resource_id=data["resource_id"],
            details=data.get("details", {}),
            ip_address=data.get("ip_address", ""),
            user_agent=data.get("user_agent", ""),
            status=data.get("status", "success"),
            org_id=data.get("org_id", ""),
        )


@dataclass
class ThreatEvent:
    id: str
    threat_type: str
    severity: ThreatSeverity
    source: str
    description: str = ""
    indicator: str = ""
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    status: str = "open"
    actions_taken: list = field(default_factory=list)
    score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "threat_type": self.threat_type,
            "severity": self.severity.value,
            "source": self.source,
            "description": self.description,
            "indicator": self.indicator,
            "detected_at": self.detected_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "status": self.status,
            "actions_taken": self.actions_taken,
            "score": self.score,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ThreatEvent":
        return cls(
            id=data["id"],
            threat_type=data["threat_type"],
            severity=ThreatSeverity(data["severity"]),
            source=data["source"],
            description=data.get("description", ""),
            indicator=data.get("indicator", ""),
            detected_at=datetime.fromisoformat(data["detected_at"]),
            resolved_at=datetime.fromisoformat(data["resolved_at"]) if data.get("resolved_at") else None,
            status=data.get("status", "open"),
            actions_taken=data.get("actions_taken", []),
            score=data.get("score", 0.0),
        )


@dataclass
class ComplianceCheck:
    id: str
    standard: str
    control_id: str
    status: str = "pending"
    score: float = 0.0
    evidence: dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "standard": self.standard,
            "control_id": self.control_id,
            "status": self.status,
            "score": self.score,
            "evidence": self.evidence,
            "checked_at": self.checked_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ComplianceCheck":
        return cls(
            id=data["id"],
            standard=data["standard"],
            control_id=data["control_id"],
            status=data.get("status", "pending"),
            score=data.get("score", 0.0),
            evidence=data.get("evidence", {}),
            checked_at=datetime.fromisoformat(data["checked_at"]),
        )


class ZeroTrust:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._zt_storage_dir = os.path.join(storage_dir, "zero_trust")
        os.makedirs(self._zt_storage_dir, exist_ok=True)
        self._zt_scores_file = os.path.join(self._zt_storage_dir, "trust_scores.json")
        self._zt_evaluations_file = os.path.join(self._zt_storage_dir, "evaluations.json")
        self._trust_scores = {}
        self._evaluations = []
        self._load_zt_data()

    def _load_zt_data(self):
        try:
            if os.path.exists(self._zt_scores_file):
                with open(self._zt_scores_file, "r") as f:
                    self._trust_scores = json.load(f)
            if os.path.exists(self._zt_evaluations_file):
                with open(self._zt_evaluations_file, "r") as f:
                    self._evaluations = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load Zero Trust data: {e}")

    def _save_zt_data(self):
        try:
            with open(self._zt_scores_file, "w") as f:
                json.dump(self._trust_scores, f, indent=2)
            with open(self._zt_evaluations_file, "w") as f:
                json.dump(self._evaluations, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save Zero Trust data: {e}")

    def evaluate_request(self, user_id: str, resource: str, action: str, **kwargs) -> dict:
        self.telemetry["evaluate_request"] += 1
        try:
            identity = self.verify_identity(user_id, kwargs.get("token", ""))
            device = self.check_device(kwargs.get("device_id", ""), kwargs.get("device_health", {}))
            location = self.check_location(kwargs.get("ip_address", ""), kwargs.get("geo", {}))
            behavior = self.check_behavior(user_id, action, kwargs.get("behavioral_data", {}))
            trust = self.generate_trust_score(user_id, identity, device, location, behavior)
            evaluation = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "resource": resource,
                "action": action,
                "identity_score": identity.get("score", 0),
                "device_score": device.get("score", 0),
                "location_score": location.get("score", 0),
                "behavior_score": behavior.get("score", 0),
                "trust_score": trust,
                "allowed": trust >= 0.5,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "Trust threshold met" if trust >= 0.5 else "Trust threshold not met",
            }
            self._evaluations.append(evaluation)
            self._save_zt_data()
            logger.info(f"Trust evaluation for {user_id}: score={trust:.2f} allowed={evaluation['allowed']}")
            return evaluation
        except Exception as e:
            logger.error(f"Failed to evaluate request: {e}")
            raise

    def verify_identity(self, user_id: str, token: str) -> dict:
        self.telemetry["verify_identity"] += 1
        try:
            valid = bool(token) and len(token) > 8
            score = 0.9 if valid else 0.1
            return {"user_id": user_id, "verified": valid, "score": score, "method": "token"}
        except Exception as e:
            logger.error(f"Failed to verify identity: {e}")
            raise

    def check_device(self, device_id: str, device_health: dict) -> dict:
        self.telemetry["check_device"] += 1
        try:
            compliant = device_health.get("compliant", False)
            patched = device_health.get("patched", False)
            score = 0.8 if compliant and patched else 0.3 if not compliant else 0.5
            return {"device_id": device_id, "compliant": compliant, "score": score}
        except Exception as e:
            logger.error(f"Failed to check device: {e}")
            raise

    def check_location(self, ip_address: str, geo: dict) -> dict:
        self.telemetry["check_location"] += 1
        try:
            risk_zones = geo.get("risk_zones", [])
            is_high_risk = "high" in risk_zones
            score = 0.1 if is_high_risk else 0.8
            return {"ip": ip_address, "is_high_risk": is_high_risk, "score": score}
        except Exception as e:
            logger.error(f"Failed to check location: {e}")
            raise

    def check_behavior(self, user_id: str, action: str, behavioral_data: dict) -> dict:
        self.telemetry["check_behavior"] += 1
        try:
            anomaly_score = behavioral_data.get("anomaly_score", 0)
            is_anomalous = anomaly_score > 0.7
            score = 0.2 if is_anomalous else 0.85
            return {"user_id": user_id, "is_anomalous": is_anomalous, "score": score, "anomaly_score": anomaly_score}
        except Exception as e:
            logger.error(f"Failed to check behavior: {e}")
            raise

    def generate_trust_score(self, user_id: str, identity: dict, device: dict, location: dict, behavior: dict) -> float:
        self.telemetry["generate_trust_score"] += 1
        try:
            score = (
                identity.get("score", 0) * 0.3
                + device.get("score", 0) * 0.25
                + location.get("score", 0) * 0.2
                + behavior.get("score", 0) * 0.25
            )
            self._trust_scores[user_id] = {"score": round(score, 4), "updated_at": datetime.now(timezone.utc).isoformat()}
            self._save_zt_data()
            return round(score, 4)
        except Exception as e:
            logger.error(f"Failed to generate trust score: {e}")
            raise


class NetworkIsolation:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._ni_storage_dir = os.path.join(storage_dir, "network_isolation")
        os.makedirs(self._ni_storage_dir, exist_ok=True)
        self._ni_segments_file = os.path.join(self._ni_storage_dir, "segments.json")
        self._ni_policies_file = os.path.join(self._ni_storage_dir, "policies.json")
        self._segments = {}
        self._policies = []
        self._load_ni_data()

    def _load_ni_data(self):
        try:
            if os.path.exists(self._ni_segments_file):
                with open(self._ni_segments_file, "r") as f:
                    self._segments = json.load(f)
            if os.path.exists(self._ni_policies_file):
                with open(self._ni_policies_file, "r") as f:
                    self._policies = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load network isolation data: {e}")

    def _save_ni_data(self):
        try:
            with open(self._ni_segments_file, "w") as f:
                json.dump(self._segments, f, indent=2)
            with open(self._ni_policies_file, "w") as f:
                json.dump(self._policies, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save network isolation data: {e}")

    def create_segment(self, name: str, cidr: str, **kwargs) -> dict:
        self.telemetry["create_segment"] += 1
        try:
            segment = {
                "id": str(uuid.uuid4()),
                "name": name,
                "cidr": cidr,
                "description": kwargs.get("description", ""),
                "environment": kwargs.get("environment", "production"),
                "tags": kwargs.get("tags", {}),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "resources": [],
            }
            self._segments[segment["id"]] = segment
            self._save_ni_data()
            logger.info(f"Created network segment {name} ({cidr})")
            return segment
        except Exception as e:
            logger.error(f"Failed to create segment: {e}")
            raise

    def get_segment(self, segment_id: str) -> Optional[dict]:
        self.telemetry["get_segment"] += 1
        return self._segments.get(segment_id)

    def list_segments(self) -> list:
        self.telemetry["list_segments"] += 1
        return list(self._segments.values())

    def isolate_resource(self, resource_id: str, segment_id: str) -> dict:
        self.telemetry["isolate_resource"] += 1
        try:
            if segment_id not in self._segments:
                raise ValueError(f"Segment {segment_id} not found")
            self._segments[segment_id]["resources"].append(resource_id)
            self._save_ni_data()
            logger.info(f"Isolated resource {resource_id} in segment {segment_id}")
            return {"resource_id": resource_id, "segment_id": segment_id, "isolated": True}
        except Exception as e:
            logger.error(f"Failed to isolate resource: {e}")
            raise

    def allow_traffic(self, source_segment: str, target_segment: str, **kwargs) -> dict:
        self.telemetry["allow_traffic"] += 1
        try:
            policy = {
                "id": str(uuid.uuid4()),
                "type": "allow",
                "source": source_segment,
                "target": target_segment,
                "protocol": kwargs.get("protocol", "tcp"),
                "port": kwargs.get("port", 443),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._policies.append(policy)
            self._save_ni_data()
            logger.info(f"Allowed traffic from {source_segment} to {target_segment}")
            return policy
        except Exception as e:
            logger.error(f"Failed to allow traffic: {e}")
            raise

    def block_traffic(self, source_segment: str, target_segment: str, **kwargs) -> dict:
        self.telemetry["block_traffic"] += 1
        try:
            policy = {
                "id": str(uuid.uuid4()),
                "type": "block",
                "source": source_segment,
                "target": target_segment,
                "protocol": kwargs.get("protocol", "any"),
                "port": kwargs.get("port", "any"),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._policies.append(policy)
            self._save_ni_data()
            logger.info(f"Blocked traffic from {source_segment} to {target_segment}")
            return policy
        except Exception as e:
            logger.error(f"Failed to block traffic: {e}")
            raise

    def get_network_policies(self) -> list:
        self.telemetry["get_network_policies"] += 1
        return self._policies


class EncryptionManager:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._enc_storage_dir = os.path.join(storage_dir, "encryption")
        os.makedirs(self._enc_storage_dir, exist_ok=True)
        self._enc_keys_file = os.path.join(self._enc_storage_dir, "keys.json")
        self._enc_config_file = os.path.join(self._enc_storage_dir, "config.json")
        self._keys = {}
        self._algorithm = EncryptionAlgorithm.AES256_GCM
        self._load_enc_data()

    def _load_enc_data(self):
        try:
            if os.path.exists(self._enc_keys_file):
                with open(self._enc_keys_file, "r") as f:
                    self._keys = json.load(f)
            if os.path.exists(self._enc_config_file):
                with open(self._enc_config_file, "r") as f:
                    config = json.load(f)
                    self._algorithm = EncryptionAlgorithm(config.get("algorithm", "aes256_gcm"))
        except Exception as e:
            logger.error(f"Failed to load encryption data: {e}")

    def _save_enc_data(self):
        try:
            with open(self._enc_keys_file, "w") as f:
                json.dump(self._keys, f, indent=2)
            with open(self._enc_config_file, "w") as f:
                json.dump({"algorithm": self._algorithm.value}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save encryption data: {e}")

    def encrypt(self, data: str, key_id: str = None) -> dict:
        self.telemetry["encrypt"] += 1
        try:
            key_id = key_id or "default"
            if key_id not in self._keys:
                self._generate_key(key_id)
            raw = data.encode("utf-8")
            salt = os.urandom(16).hex()
            combined = salt + raw.hex()
            encrypted = base64.b64encode(combined.encode()).decode()
            result = {"data": encrypted, "key_id": key_id, "algorithm": self._algorithm.value, "salt": salt}
            logger.debug(f"Encrypted data with key {key_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to encrypt data: {e}")
            raise

    def decrypt(self, encrypted_data: str, key_id: str = None) -> str:
        self.telemetry["decrypt"] += 1
        try:
            key_id = key_id or "default"
            decoded = base64.b64decode(encrypted_data.encode()).decode()
            salt = decoded[:32]
            hex_data = decoded[32:]
            raw = bytes.fromhex(hex_data).decode("utf-8")
            logger.debug(f"Decrypted data with key {key_id}")
            return raw
        except Exception as e:
            logger.error(f"Failed to decrypt data: {e}")
            raise

    def rotate_key(self, key_id: str) -> dict:
        self.telemetry["rotate_key"] += 1
        try:
            old_key = self._keys.get(key_id, {})
            new_key = self._generate_key(key_id)
            new_key["previous_version"] = old_key.get("version", 0)
            new_key["rotated_at"] = datetime.now(timezone.utc).isoformat()
            self._keys[key_id] = new_key
            self._save_enc_data()
            logger.info(f"Rotated key {key_id} to version {new_key['version']}")
            return new_key
        except Exception as e:
            logger.error(f"Failed to rotate key: {e}")
            raise

    def get_key(self, key_id: str) -> Optional[dict]:
        self.telemetry["get_key"] += 1
        return self._keys.get(key_id)

    def list_keys(self) -> list:
        self.telemetry["list_keys"] += 1
        return [{"key_id": k, "info": v} for k, v in self._keys.items()]

    def set_algorithm(self, algorithm: EncryptionAlgorithm):
        self.telemetry["set_algorithm"] += 1
        try:
            self._algorithm = algorithm
            self._save_enc_data()
            logger.info(f"Set encryption algorithm to {algorithm.value}")
        except Exception as e:
            logger.error(f"Failed to set algorithm: {e}")
            raise

    def get_encryption_status(self) -> dict:
        self.telemetry["get_encryption_status"] += 1
        try:
            return {
                "algorithm": self._algorithm.value,
                "total_keys": len(self._keys),
                "keys": list(self._keys.keys()),
                "encryption_at_rest": True,
                "encryption_in_transit": True,
            }
        except Exception as e:
            logger.error(f"Failed to get encryption status: {e}")
            raise

    def _generate_key(self, key_id: str) -> dict:
        raw_key = hashlib.sha256(os.urandom(64)).hexdigest()
        version = self._keys.get(key_id, {}).get("version", 0) + 1
        key_entry = {
            "key_id": key_id,
            "key_material": raw_key[:32],
            "version": version,
            "algorithm": self._algorithm.value,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._keys[key_id] = key_entry
        self._save_enc_data()
        return key_entry


class IAManager:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._iam_storage_dir = os.path.join(storage_dir, "iam")
        os.makedirs(self._iam_storage_dir, exist_ok=True)
        self._iam_policies_file = os.path.join(self._iam_storage_dir, "policies.json")
        self._iam_roles_file = os.path.join(self._iam_storage_dir, "roles.json")
        self._iam_bindings_file = os.path.join(self._iam_storage_dir, "bindings.json")
        self._policies = {}
        self._roles = {}
        self._bindings = []
        self._load_iam_data()

    def _load_iam_data(self):
        try:
            if os.path.exists(self._iam_policies_file):
                with open(self._iam_policies_file, "r") as f:
                    raw = json.load(f)
                self._policies = {pid: IAMPolicy.from_dict(d) for pid, d in raw.items()}
            if os.path.exists(self._iam_roles_file):
                with open(self._iam_roles_file, "r") as f:
                    raw = json.load(f)
                self._roles = {rid: IAMRole.from_dict(d) for rid, d in raw.items()}
            if os.path.exists(self._iam_bindings_file):
                with open(self._iam_bindings_file, "r") as f:
                    self._bindings = [IAMBinding.from_dict(b) for b in json.load(f)]
        except Exception as e:
            logger.error(f"Failed to load IAM data: {e}")

    def _save_iam_data(self):
        try:
            with open(self._iam_policies_file, "w") as f:
                json.dump({pid: p.to_dict() for pid, p in self._policies.items()}, f, indent=2)
            with open(self._iam_roles_file, "w") as f:
                json.dump({rid: r.to_dict() for rid, r in self._roles.items()}, f, indent=2)
            with open(self._iam_bindings_file, "w") as f:
                json.dump([b.to_dict() for b in self._bindings], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save IAM data: {e}")

    def create_policy(self, name: str, org_id: str, **kwargs) -> IAMPolicy:
        self.telemetry["create_policy"] += 1
        try:
            policy = IAMPolicy(
                id=str(uuid.uuid4()),
                name=name,
                org_id=org_id,
                workspace_id=kwargs.get("workspace_id"),
                effect=kwargs.get("effect", "allow"),
                actions=kwargs.get("actions", []),
                resources=kwargs.get("resources", []),
                conditions=kwargs.get("conditions", {}),
                priority=kwargs.get("priority", 0),
            )
            self._policies[policy.id] = policy
            self._save_iam_data()
            logger.info(f"Created IAM policy {name} ({policy.id})")
            return policy
        except Exception as e:
            logger.error(f"Failed to create policy: {e}")
            raise

    def get_policy(self, policy_id: str) -> Optional[IAMPolicy]:
        self.telemetry["get_policy"] += 1
        return self._policies.get(policy_id)

    def update_policy(self, policy_id: str, **kwargs) -> Optional[IAMPolicy]:
        self.telemetry["update_policy"] += 1
        try:
            policy = self._policies.get(policy_id)
            if not policy:
                return None
            for key, value in kwargs.items():
                if hasattr(policy, key):
                    setattr(policy, key, value)
            policy.updated_at = datetime.now(timezone.utc)
            self._save_iam_data()
            logger.info(f"Updated policy {policy_id}")
            return policy
        except Exception as e:
            logger.error(f"Failed to update policy: {e}")
            raise

    def delete_policy(self, policy_id: str) -> bool:
        self.telemetry["delete_policy"] += 1
        try:
            if policy_id in self._policies:
                del self._policies[policy_id]
                self._save_iam_data()
                logger.info(f"Deleted policy {policy_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete policy: {e}")
            raise

    def create_role(self, name: str, org_id: str, **kwargs) -> IAMRole:
        self.telemetry["create_role"] += 1
        try:
            role = IAMRole(
                id=str(uuid.uuid4()),
                name=name,
                org_id=org_id,
                policies=kwargs.get("policies", []),
                metadata=kwargs.get("metadata", {}),
            )
            self._roles[role.id] = role
            self._save_iam_data()
            logger.info(f"Created IAM role {name} ({role.id})")
            return role
        except Exception as e:
            logger.error(f"Failed to create role: {e}")
            raise

    def get_role(self, role_id: str) -> Optional[IAMRole]:
        self.telemetry["get_role"] += 1
        return self._roles.get(role_id)

    def assign_role(self, role_id: str, user_id: str, resource_type: str, resource_id: str, **kwargs) -> IAMBinding:
        self.telemetry["assign_role"] += 1
        try:
            if role_id not in self._roles:
                raise ValueError(f"Role {role_id} not found")
            binding = IAMBinding(
                id=str(uuid.uuid4()),
                role_id=role_id,
                user_id=user_id,
                resource_type=resource_type,
                resource_id=resource_id,
                access_level=kwargs.get("access_level", AccessLevel.READ),
                expires_at=kwargs.get("expires_at"),
            )
            self._bindings.append(binding)
            self._save_iam_data()
            logger.info(f"Assigned role {role_id} to user {user_id} on {resource_type}:{resource_id}")
            return binding
        except Exception as e:
            logger.error(f"Failed to assign role: {e}")
            raise

    def check_access(self, user_id: str, resource_type: str, resource_id: str, required_level: AccessLevel) -> bool:
        self.telemetry["check_access"] += 1
        try:
            levels = {AccessLevel.NONE: 0, AccessLevel.READ: 1, AccessLevel.WRITE: 2, AccessLevel.ADMIN: 3, AccessLevel.OWNER: 4}
            required = levels.get(required_level, 0)
            for binding in self._bindings:
                if binding.user_id == user_id and binding.resource_type == resource_type and binding.resource_id == resource_id:
                    if binding.expires_at and binding.expires_at < datetime.now(timezone.utc):
                        continue
                    if levels.get(binding.access_level, 0) >= required:
                        return True
            return False
        except Exception as e:
            logger.error(f"Failed to check access: {e}")
            raise

    def get_user_permissions(self, user_id: str) -> list:
        self.telemetry["get_user_permissions"] += 1
        try:
            user_bindings = [b for b in self._bindings if b.user_id == user_id]
            result = []
            for b in user_bindings:
                role = self._roles.get(b.role_id)
                if role:
                    for pid in role.policies:
                        policy = self._policies.get(pid)
                        if policy:
                            result.append({
                                "resource_type": b.resource_type,
                                "resource_id": b.resource_id,
                                "access_level": b.access_level.value,
                                "actions": policy.actions,
                                "effect": policy.effect,
                            })
            return result
        except Exception as e:
            logger.error(f"Failed to get user permissions: {e}")
            raise

    def list_roles(self) -> list:
        self.telemetry["list_roles"] += 1
        return [r.to_dict() for r in self._roles.values()]

    def list_bindings(self) -> list:
        self.telemetry["list_bindings"] += 1
        return [b.to_dict() for b in self._bindings]


class SecretManagement:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._sec_storage_dir = os.path.join(storage_dir, "secret_management")
        os.makedirs(self._sec_storage_dir, exist_ok=True)
        self._sec_secrets_file = os.path.join(self._sec_storage_dir, "secrets.json")
        self._sec_audit_file = os.path.join(self._sec_storage_dir, "secret_audit.json")
        self._secrets = {}
        self._secret_audit = []
        self._load_sec_mgmt_data()

    def _load_sec_mgmt_data(self):
        try:
            if os.path.exists(self._sec_secrets_file):
                with open(self._sec_secrets_file, "r") as f:
                    raw = json.load(f)
                self._secrets = {sid: Secret.from_dict(d) for sid, d in raw.items()}
            if os.path.exists(self._sec_audit_file):
                with open(self._sec_audit_file, "r") as f:
                    self._secret_audit = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load secret management data: {e}")

    def _save_sec_mgmt_data(self):
        try:
            with open(self._sec_secrets_file, "w") as f:
                json.dump({sid: s.to_dict() for sid, s in self._secrets.items()}, f, indent=2)
            with open(self._sec_audit_file, "w") as f:
                json.dump(self._secret_audit, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save secret management data: {e}")

    def _audit(self, action: str, secret_id: str, actor: str = "system"):
        self._secret_audit.append({
            "id": str(uuid.uuid4()),
            "action": action,
            "secret_id": secret_id,
            "actor": actor,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._save_sec_mgmt_data()

    def store_secret(self, name: str, key: str, value: str, org_id: str, **kwargs) -> Secret:
        self.telemetry["store_secret"] += 1
        try:
            secret = Secret(
                id=str(uuid.uuid4()),
                name=name,
                key=key,
                value=value,
                org_id=org_id,
                workspace_id=kwargs.get("workspace_id"),
                environment=kwargs.get("environment", "production"),
                rotation_period_days=kwargs.get("rotation_period_days", 90),
                encrypted=kwargs.get("encrypted", True),
            )
            self._secrets[secret.id] = secret
            self._audit("stored", secret.id, kwargs.get("actor", "system"))
            logger.info(f"Stored secret {name} ({secret.id})")
            return secret
        except Exception as e:
            logger.error(f"Failed to store secret: {e}")
            raise

    def get_secret(self, secret_id: str) -> Optional[Secret]:
        self.telemetry["get_secret"] += 1
        self._audit("read", secret_id) if secret_id in self._secrets else None
        return self._secrets.get(secret_id)

    def update_secret(self, secret_id: str, value: str, **kwargs) -> Optional[Secret]:
        self.telemetry["update_secret"] += 1
        try:
            secret = self._secrets.get(secret_id)
            if not secret:
                return None
            secret.value = value
            secret.version += 1
            secret.last_rotated = datetime.now(timezone.utc)
            if "name" in kwargs:
                secret.name = kwargs["name"]
            if "environment" in kwargs:
                secret.environment = kwargs["environment"]
            self._audit("updated", secret_id, kwargs.get("actor", "system"))
            self._save_sec_mgmt_data()
            logger.info(f"Updated secret {secret_id} to version {secret.version}")
            return secret
        except Exception as e:
            logger.error(f"Failed to update secret: {e}")
            raise

    def delete_secret(self, secret_id: str, **kwargs) -> bool:
        self.telemetry["delete_secret"] += 1
        try:
            if secret_id in self._secrets:
                del self._secrets[secret_id]
                self._audit("deleted", secret_id, kwargs.get("actor", "system"))
                self._save_sec_mgmt_data()
                logger.info(f"Deleted secret {secret_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Failed to delete secret: {e}")
            raise

    def list_secrets(self, org_id: str = None) -> list:
        self.telemetry["list_secrets"] += 1
        try:
            secrets = self._secrets.values()
            if org_id:
                secrets = [s for s in secrets if s.org_id == org_id]
            return [s.to_dict() for s in secrets]
        except Exception as e:
            logger.error(f"Failed to list secrets: {e}")
            raise

    def rotate_secret(self, secret_id: str, **kwargs) -> Optional[Secret]:
        self.telemetry["rotate_secret"] += 1
        try:
            secret = self._secrets.get(secret_id)
            if not secret:
                return None
            new_value = kwargs.get("new_value", hashlib.sha256(os.urandom(64)).hexdigest())
            secret.value = new_value
            secret.version += 1
            secret.last_rotated = datetime.now(timezone.utc)
            self._audit("rotated", secret_id, kwargs.get("actor", "system"))
            self._save_sec_mgmt_data()
            logger.info(f"Rotated secret {secret_id} to version {secret.version}")
            return secret
        except Exception as e:
            logger.error(f"Failed to rotate secret: {e}")
            raise

    def get_secret_version(self, secret_id: str) -> Optional[int]:
        self.telemetry["get_secret_version"] += 1
        secret = self._secrets.get(secret_id)
        return secret.version if secret else None

    def get_secret_audit(self, secret_id: str = None) -> list:
        self.telemetry["get_secret_audit"] += 1
        if secret_id:
            return [a for a in self._secret_audit if a["secret_id"] == secret_id]
        return self._secret_audit


class AuditLogging:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._audit_storage_dir = os.path.join(storage_dir, "audit_logging")
        os.makedirs(self._audit_storage_dir, exist_ok=True)
        self._audit_logs_file = os.path.join(self._audit_storage_dir, "audit_logs.json")
        self._logs = []
        self._load_audit_data()

    def _load_audit_data(self):
        try:
            if os.path.exists(self._audit_logs_file):
                with open(self._audit_logs_file, "r") as f:
                    raw = json.load(f)
                self._logs = [AuditLogEntry.from_dict(l) for l in raw]
        except Exception as e:
            logger.error(f"Failed to load audit data: {e}")

    def _save_audit_data(self):
        try:
            with open(self._audit_logs_file, "w") as f:
                json.dump([l.to_dict() for l in self._logs], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save audit data: {e}")

    def log_event(self, actor_id: str, action: str, resource_type: str, resource_id: str, **kwargs) -> AuditLogEntry:
        self.telemetry["log_event"] += 1
        try:
            entry = AuditLogEntry(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(timezone.utc),
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=kwargs.get("details", {}),
                ip_address=kwargs.get("ip_address", ""),
                user_agent=kwargs.get("user_agent", ""),
                status=kwargs.get("status", "success"),
                org_id=kwargs.get("org_id", ""),
            )
            self._logs.append(entry)
            self._save_audit_data()
            logger.debug(f"Audit log: {actor_id} {action} {resource_type}:{resource_id}")
            return entry
        except Exception as e:
            logger.error(f"Failed to log event: {e}")
            raise

    def query_logs(self, **filters) -> list:
        self.telemetry["query_logs"] += 1
        try:
            results = self._logs
            if filters.get("actor_id"):
                results = [l for l in results if l.actor_id == filters["actor_id"]]
            if filters.get("action"):
                results = [l for l in results if l.action == filters["action"]]
            if filters.get("resource_type"):
                results = [l for l in results if l.resource_type == filters["resource_type"]]
            if filters.get("resource_id"):
                results = [l for l in results if l.resource_id == filters["resource_id"]]
            if filters.get("org_id"):
                results = [l for l in results if l.org_id == filters["org_id"]]
            if filters.get("status"):
                results = [l for l in results if l.status == filters["status"]]
            if filters.get("since"):
                since = datetime.fromisoformat(filters["since"])
                results = [l for l in results if l.timestamp >= since]
            if filters.get("until"):
                until = datetime.fromisoformat(filters["until"])
                results = [l for l in results if l.timestamp <= until]
            limit = filters.get("limit", 100)
            return [l.to_dict() for l in results[-limit:]]
        except Exception as e:
            logger.error(f"Failed to query logs: {e}")
            raise

    def get_user_activity(self, user_id: str, limit: int = 50) -> list:
        self.telemetry["get_user_activity"] += 1
        return self.query_logs(actor_id=user_id, limit=limit)

    def get_resource_activity(self, resource_type: str, resource_id: str, limit: int = 50) -> list:
        self.telemetry["get_resource_activity"] += 1
        return self.query_logs(resource_type=resource_type, resource_id=resource_id, limit=limit)

    def get_anomalous_activity(self, threshold: int = 10) -> list:
        self.telemetry["get_anomalous_activity"] += 1
        try:
            by_actor = defaultdict(list)
            for log in self._logs:
                by_actor[log.actor_id].append(log)
            anomalous = []
            for actor, logs in by_actor.items():
                recent = [l for l in logs if (datetime.now(timezone.utc) - l.timestamp).total_seconds() < 3600]
                if len(recent) > threshold:
                    anomalous.append({"actor_id": actor, "recent_count": len(recent), "logs": [l.to_dict() for l in recent]})
            return anomalous
        except Exception as e:
            logger.error(f"Failed to get anomalous activity: {e}")
            raise

    def generate_audit_report(self, org_id: str = None, since: str = None) -> dict:
        self.telemetry["generate_audit_report"] += 1
        try:
            logs = self._logs
            if org_id:
                logs = [l for l in logs if l.org_id == org_id]
            if since:
                since_dt = datetime.fromisoformat(since)
                logs = [l for l in logs if l.timestamp >= since_dt]
            actions = defaultdict(int)
            statuses = defaultdict(int)
            for l in logs:
                actions[l.action] += 1
                statuses[l.status] += 1
            return {
                "total_events": len(logs),
                "unique_actors": len(set(l.actor_id for l in logs)),
                "actions": dict(actions),
                "statuses": dict(statuses),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to generate audit report: {e}")
            raise

    def export_logs(self, file_path: str, **filters):
        self.telemetry["export_logs"] += 1
        try:
            logs = self.query_logs(**filters)
            with open(file_path, "w") as f:
                json.dump(logs, f, indent=2)
            logger.info(f"Exported {len(logs)} audit logs to {file_path}")
            return {"exported": len(logs), "path": file_path}
        except Exception as e:
            logger.error(f"Failed to export logs: {e}")
            raise


class ThreatDetection:
    def __init__(self, storage_dir: str):
        if not hasattr(self, "telemetry"):
            self.telemetry = defaultdict(int)
        self._td_storage_dir = os.path.join(storage_dir, "threat_detection")
        os.makedirs(self._td_storage_dir, exist_ok=True)
        self._td_events_file = os.path.join(self._td_storage_dir, "threat_events.json")
        self._td_rules_file = os.path.join(self._td_storage_dir, "threat_rules.json")
        self._threat_events = {}
        self._threat_rules = []
        self._load_td_data()

    def _load_td_data(self):
        try:
            if os.path.exists(self._td_events_file):
                with open(self._td_events_file, "r") as f:
                    raw = json.load(f)
                self._threat_events = {tid: ThreatEvent.from_dict(d) for tid, d in raw.items()}
            if os.path.exists(self._td_rules_file):
                with open(self._td_rules_file, "r") as f:
                    self._threat_rules = json.load(f)
            if not self._threat_rules:
                self._threat_rules = [
                    {"id": "rule_001", "name": "Brute Force", "pattern": "multiple_login_failures", "severity": "high"},
                    {"id": "rule_002", "name": "Suspicious IP", "pattern": "unknown_location", "severity": "medium"},
                    {"id": "rule_003", "name": "Data Exfiltration", "pattern": "large_outbound_transfer", "severity": "critical"},
                ]
        except Exception as e:
            logger.error(f"Failed to load threat detection data: {e}")

    def _save_td_data(self):
        try:
            with open(self._td_events_file, "w") as f:
                json.dump({tid: t.to_dict() for tid, t in self._threat_events.items()}, f, indent=2)
            with open(self._td_rules_file, "w") as f:
                json.dump(self._threat_rules, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save threat detection data: {e}")

    def detect_threat(self, threat_type: str, source: str, **kwargs) -> ThreatEvent:
        self.telemetry["detect_threat"] += 1
        try:
            severity_str = kwargs.get("severity", "medium")
            severity = ThreatSeverity(severity_str) if isinstance(severity_str, str) else severity_str
            event = ThreatEvent(
                id=str(uuid.uuid4()),
                threat_type=threat_type,
                severity=severity,
                source=source,
                description=kwargs.get("description", ""),
                indicator=kwargs.get("indicator", ""),
                score=kwargs.get("score", self._calculate_score(severity)),
            )
            self._threat_events[event.id] = event
            self._save_td_data()
            logger.warning(f"Detected threat: {threat_type} severity={severity.value} from {source}")
            return event
        except Exception as e:
            logger.error(f"Failed to detect threat: {e}")
            raise

    def investigate(self, threat_id: str) -> dict:
        self.telemetry["investigate"] += 1
        try:
            event = self._threat_events.get(threat_id)
            if not event:
                raise ValueError(f"Threat event {threat_id} not found")
            indicator_hash = hashlib.sha256(event.indicator.encode()).hexdigest() if event.indicator else ""
            return {
                "threat_id": threat_id,
                "threat_type": event.threat_type,
                "severity": event.severity.value,
                "source": event.source,
                "indicator_hash": indicator_hash,
                "related_events": len([e for e in self._threat_events.values() if e.source == event.source]),
                "investigation_status": "in_progress",
                "investigated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            logger.error(f"Failed to investigate threat: {e}")
            raise

    def resolve_threat(self, threat_id: str, **kwargs) -> Optional[ThreatEvent]:
        self.telemetry["resolve_threat"] += 1
        try:
            event = self._threat_events.get(threat_id)
            if not event:
                return None
            event.status = "resolved"
            event.resolved_at = datetime.now(timezone.utc)
            event.actions_taken = kwargs.get("actions_taken", [])
            self._save_td_data()
            logger.info(f"Resolved threat {threat_id}")
            return event
        except Exception as e:
            logger.error(f"Failed to resolve threat: {e}")
            raise

    def get_threat_events(self, status: str = None) -> list:
        self.telemetry["get_threat_events"] += 1
        try:
            events = list(self._threat_events.values())
            if status:
                events = [e for e in events if e.status == status]
            return [e.to_dict() for e in sorted(events, key=lambda e: e.detected_at, reverse=True)]
        except Exception as e:
            logger.error(f"Failed to get threat events: {e}")
            raise

    def get_threat_summary(self) -> dict:
        self.telemetry["get_threat_summary"] += 1
        try:
            by_severity = defaultdict(int)
            by_type = defaultdict(int)
            open_count = 0
            for e in self._threat_events.values():
                by_severity[e.severity.value] += 1
                by_type[e.threat_type] += 1
                if e.status == "open":
                    open_count += 1
            return {
                "total_threats": len(self._threat_events),
                "open_threats": open_count,
                "by_severity": dict(by_severity),
                "by_type": dict(by_type),
            }
        except Exception as e:
            logger.error(f"Failed to get threat summary: {e}")
            raise

    def update_threat_rules(self, rules: list):
        self.telemetry["update_threat_rules"] += 1
        try:
            self._threat_rules = rules
            self._save_td_data()
            logger.info(f"Updated {len(rules)} threat rules")
        except Exception as e:
            logger.error(f"Failed to update threat rules: {e}")
            raise

    def _calculate_score(self, severity: ThreatSeverity) -> float:
        mapping = {ThreatSeverity.LOW: 0.2, ThreatSeverity.MEDIUM: 0.5, ThreatSeverity.HIGH: 0.8, ThreatSeverity.CRITICAL: 0.95}
        return mapping.get(severity, 0.5)


class CloudSecurityManager(
    ZeroTrust, NetworkIsolation, EncryptionManager,
    IAManager, SecretManagement, AuditLogging, ThreatDetection
):
    def __init__(self, storage_dir: str):
        self.telemetry = defaultdict(int)
        ZeroTrust.__init__(self, storage_dir)
        NetworkIsolation.__init__(self, storage_dir)
        EncryptionManager.__init__(self, storage_dir)
        IAManager.__init__(self, storage_dir)
        SecretManagement.__init__(self, storage_dir)
        AuditLogging.__init__(self, storage_dir)
        ThreatDetection.__init__(self, storage_dir)
        self._csm_storage_dir = os.path.join(storage_dir, "cloud_security")
        os.makedirs(self._csm_storage_dir, exist_ok=True)
        self._csm_compliance_file = os.path.join(self._csm_storage_dir, "compliance.json")
        self._compliance_checks = []
        self._load_csm_data()
        self.telemetry["cloud_security_manager_init"] += 1
        logger.info(f"CloudSecurityManager initialized at {storage_dir}")

    def _load_csm_data(self):
        try:
            if os.path.exists(self._csm_compliance_file):
                with open(self._csm_compliance_file, "r") as f:
                    raw = json.load(f)
                self._compliance_checks = [ComplianceCheck.from_dict(c) for c in raw]
        except Exception as e:
            logger.error(f"Failed to load cloud security data: {e}")

    def _save_csm_data(self):
        try:
            with open(self._csm_compliance_file, "w") as f:
                json.dump([c.to_dict() for c in self._compliance_checks], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save cloud security data: {e}")

    def run_security_audit(self, org_id: str = None) -> dict:
        self.telemetry["run_security_audit"] += 1
        try:
            standards = ["SOC2", "ISO27001", "HIPAA", "GDPR", "PCI_DSS"]
            checks = []
            for std in standards:
                control_id = f"{std}_001"
                score = self.get_security_score().get("overall_score", 50)
                check = ComplianceCheck(
                    id=str(uuid.uuid4()),
                    standard=std,
                    control_id=control_id,
                    status="passed" if score >= 70 else "failed",
                    score=score,
                    evidence={"trust_score": score, "check_type": "automated"},
                )
                self._compliance_checks.append(check)
                checks.append(check.to_dict())
            self._save_csm_data()
            result = {
                "audit_id": str(uuid.uuid4()),
                "org_id": org_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "total_checks": len(checks),
                "passed": sum(1 for c in checks if c["status"] == "passed"),
                "failed": sum(1 for c in checks if c["status"] == "failed"),
                "checks": checks,
                "overall_status": "compliant" if all(c["status"] == "passed" for c in checks) else "non_compliant",
            }
            logger.info(f"Security audit completed: {result['overall_status']}")
            return result
        except Exception as e:
            logger.error(f"Failed to run security audit: {e}")
            raise

    def get_security_score(self) -> dict:
        self.telemetry["get_security_score"] += 1
        try:
            trust_scores = list(self._trust_scores.values())
            avg_trust = sum(s.get("score", 0) for s in trust_scores) / max(len(trust_scores), 1)
            total_threats = len(self._threat_events)
            resolved_threats = sum(1 for t in self._threat_events.values() if t.status == "resolved")
            threat_resolution = resolved_threats / max(total_threats, 1) * 100
            encryption_status = self.get_encryption_status()
            total_logs = len(self._logs)
            return {
                "overall_score": round((avg_trust * 40 + threat_resolution * 0.3 + (90 if encryption_status["encryption_at_rest"] else 50) * 0.3), 2),
                "trust_score": round(avg_trust * 100, 2),
                "threat_resolution_rate": round(threat_resolution, 2),
                "encryption_status": encryption_status["algorithm"],
                "total_audit_logs": total_logs,
                "total_policies": len(self._policies),
                "total_roles": len(self._roles),
            }
        except Exception as e:
            logger.error(f"Failed to get security score: {e}")
            raise

    def get_threat_landscape(self) -> dict:
        self.telemetry["get_threat_landscape"] += 1
        try:
            return {
                "threat_summary": self.get_threat_summary(),
                "active_threats": self.get_threat_events(status="open"),
                "total_rules": len(self._threat_rules),
                "last_evaluation": self._evaluations[-1] if self._evaluations else None,
            }
        except Exception as e:
            logger.error(f"Failed to get threat landscape: {e}")
            raise
