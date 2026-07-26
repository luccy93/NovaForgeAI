import json
import uuid
import os
import logging
from datetime import datetime, timezone
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)


class ControlType(Enum):
    REPOSITORY_OWNERSHIP = "repository_ownership"
    WORKSPACE_ISOLATION = "workspace_isolation"
    DEPARTMENT_POLICY = "department_policy"
    BU_POLICY = "bu_policy"
    ENVIRONMENT_RESTRICTION = "environment_restriction"
    TIME_BASED_ACCESS = "time_based_access"
    LOCATION_RESTRICTION = "location_restriction"
    IP_RESTRICTION = "ip_restriction"
    DEVICE_TRUST = "device_trust"
    NETWORK_ZONE = "network_zone"


class EnvironmentType(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    SANDBOX = "sandbox"
    TESTING = "testing"
    DR = "dr"


class AccessLevel(Enum):
    NONE = "none"
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    OWNER = "owner"
    CUSTOM = "custom"


class ConstraintType(Enum):
    ALLOW_LIST = "allow_list"
    DENY_LIST = "deny_list"
    TIME_WINDOW = "time_window"
    GEO_REGION = "geo_region"
    IP_CIDR = "ip_cidr"
    DEVICE_COMPLIANCE = "device_compliance"
    NETWORK_SEGMENT = "network_segment"
    ROLE_BASED = "role_based"


@dataclass
class OrgControl:
    id: str
    org_id: str
    name: str
    description: str = ""
    control_type: ControlType = ControlType.REPOSITORY_OWNERSHIP
    enabled: bool = True
    priority: int = 0
    constraints: list = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    created_by: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["control_type"] = self.control_type.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "OrgControl":
        data["control_type"] = ControlType(data["control_type"])
        return cls(**data)


@dataclass
class WorkspaceIsolationPolicy:
    id: str
    org_id: str
    workspace_id: str
    isolated: bool = True
    allowed_cross_workspace_access: list[str] = field(default_factory=list)
    data_isolation_level: str = "strict"
    network_isolation: bool = True
    share_settings: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkspaceIsolationPolicy":
        return cls(**data)


@dataclass
class EnvironmentAccessRule:
    id: str
    org_id: str
    environment: EnvironmentType = EnvironmentType.DEVELOPMENT
    allowed_roles: list[str] = field(default_factory=list)
    allowed_users: list[str] = field(default_factory=list)
    require_approval: bool = False
    approval_roles: list[str] = field(default_factory=list)
    allowed_days: list[str] = field(default_factory=list)
    allowed_hours_start: Optional[str] = None
    allowed_hours_end: Optional[str] = None
    ip_restrictions: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        d = asdict(self)
        d["environment"] = self.environment.value
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "EnvironmentAccessRule":
        data["environment"] = EnvironmentType(data["environment"])
        return cls(**data)


@dataclass
class LocationRestriction:
    id: str
    org_id: str
    name: str
    allowed_countries: list[str] = field(default_factory=list)
    blocked_countries: list[str] = field(default_factory=list)
    allowed_regions: list[str] = field(default_factory=list)
    allowed_ip_ranges: list[str] = field(default_factory=list)
    block_proxy: bool = True
    action_on_violation: str = "deny"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "LocationRestriction":
        return cls(**data)


@dataclass
class TimeBasedAccess:
    id: str
    org_id: str
    name: str
    user_id: str
    allowed_days: list[str] = field(default_factory=list)
    allowed_start_time: Optional[str] = None
    allowed_end_time: Optional[str] = None
    timezone: str = "UTC"
    max_session_hours: float = 0.0
    expires_at: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TimeBasedAccess":
        return cls(**data)


class OrganizationControls:
    def __init__(self, storage_dir: str = "organization_controls_data"):
        self.storage_dir = storage_dir
        self._controls: dict[str, OrgControl] = {}
        self._workspace_policies: dict[str, WorkspaceIsolationPolicy] = {}
        self._environment_rules: dict[str, EnvironmentAccessRule] = {}
        self._location_restrictions: dict[str, LocationRestriction] = {}
        self._time_based_access: dict[str, TimeBasedAccess] = {}
        self._telemetry: dict[str, int] = defaultdict(int)
        os.makedirs(self.storage_dir, exist_ok=True)
        self._load()

    def _controls_path(self) -> str:
        return os.path.join(self.storage_dir, "controls.json")

    def _workspace_path(self) -> str:
        return os.path.join(self.storage_dir, "workspace_isolation.json")

    def _environment_path(self) -> str:
        return os.path.join(self.storage_dir, "environment_rules.json")

    def _location_path(self) -> str:
        return os.path.join(self.storage_dir, "location_restrictions.json")

    def _time_path(self) -> str:
        return os.path.join(self.storage_dir, "time_based_access.json")

    def _save(self) -> None:
        try:
            controls_data = {cid: c.to_dict() for cid, c in self._controls.items()}
            with open(self._controls_path(), "w", encoding="utf-8") as f:
                json.dump(controls_data, f, indent=2, default=str)

            workspace_data = {wid: p.to_dict() for wid, p in self._workspace_policies.items()}
            with open(self._workspace_path(), "w", encoding="utf-8") as f:
                json.dump(workspace_data, f, indent=2, default=str)

            env_data = {eid: r.to_dict() for eid, r in self._environment_rules.items()}
            with open(self._environment_path(), "w", encoding="utf-8") as f:
                json.dump(env_data, f, indent=2, default=str)

            location_data = {lid: r.to_dict() for lid, r in self._location_restrictions.items()}
            with open(self._location_path(), "w", encoding="utf-8") as f:
                json.dump(location_data, f, indent=2, default=str)

            time_data = {tid: a.to_dict() for tid, a in self._time_based_access.items()}
            with open(self._time_path(), "w", encoding="utf-8") as f:
                json.dump(time_data, f, indent=2, default=str)
        except Exception as e:
            logger.error("Failed to save organization controls data: %s", e, exc_info=True)

    def _load(self) -> None:
        try:
            if os.path.exists(self._controls_path()):
                with open(self._controls_path(), "r", encoding="utf-8") as f:
                    controls_data = json.load(f)
                for cid, data in controls_data.items():
                    try:
                        self._controls[cid] = OrgControl.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed control %s: %s", cid, e)

            if os.path.exists(self._workspace_path()):
                with open(self._workspace_path(), "r", encoding="utf-8") as f:
                    workspace_data = json.load(f)
                for wid, data in workspace_data.items():
                    try:
                        self._workspace_policies[wid] = WorkspaceIsolationPolicy.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed workspace isolation policy %s: %s", wid, e)

            if os.path.exists(self._environment_path()):
                with open(self._environment_path(), "r", encoding="utf-8") as f:
                    env_data = json.load(f)
                for eid, data in env_data.items():
                    try:
                        self._environment_rules[eid] = EnvironmentAccessRule.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed environment rule %s: %s", eid, e)

            if os.path.exists(self._location_path()):
                with open(self._location_path(), "r", encoding="utf-8") as f:
                    location_data = json.load(f)
                for lid, data in location_data.items():
                    try:
                        self._location_restrictions[lid] = LocationRestriction.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed location restriction %s: %s", lid, e)

            if os.path.exists(self._time_path()):
                with open(self._time_path(), "r", encoding="utf-8") as f:
                    time_data = json.load(f)
                for tid, data in time_data.items():
                    try:
                        self._time_based_access[tid] = TimeBasedAccess.from_dict(data)
                    except Exception as e:
                        logger.warning("Skipping malformed time based access %s: %s", tid, e)
        except Exception as e:
            logger.error("Failed to load organization controls data: %s", e, exc_info=True)

    def create_control(self, control: OrgControl) -> OrgControl:
        self._telemetry["create_control_calls"] += 1
        if control.id in self._controls:
            raise ValueError(f"Control with id '{control.id}' already exists.")
        now = datetime.now(timezone.utc).isoformat()
        control.created_at = now
        control.updated_at = now
        self._controls[control.id] = control
        self._save()
        logger.info("Created organization control: %s (%s)", control.name, control.id)
        return control

    def update_control(self, control_id: str, updates: dict) -> Optional[OrgControl]:
        self._telemetry["update_control_calls"] += 1
        control = self._controls.get(control_id)
        if not control:
            logger.warning("Attempted to update unknown control: %s", control_id)
            return None
        for key, value in updates.items():
            if hasattr(control, key) and key not in ("id", "org_id", "created_at"):
                if key == "control_type":
                    setattr(control, key, ControlType(value) if isinstance(value, str) else value)
                else:
                    setattr(control, key, value)
        control.updated_at = datetime.now(timezone.utc).isoformat()
        self._save()
        logger.info("Updated control: %s", control_id)
        return control

    def list_controls(self, org_id: str, control_type: Optional[ControlType] = None) -> list[OrgControl]:
        self._telemetry["list_controls_calls"] += 1
        results = [c for c in self._controls.values() if c.org_id == org_id]
        if control_type:
            results = [c for c in results if c.control_type == control_type]
        return results

    def set_workspace_isolation(self, policy: WorkspaceIsolationPolicy) -> WorkspaceIsolationPolicy:
        self._telemetry["set_workspace_isolation_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        policy.created_at = now
        policy.updated_at = now
        self._workspace_policies[policy.workspace_id] = policy
        self._save()
        logger.info("Set workspace isolation policy for workspace: %s", policy.workspace_id)
        return policy

    def get_workspace_isolation(self, workspace_id: str) -> Optional[WorkspaceIsolationPolicy]:
        self._telemetry["get_workspace_isolation_calls"] += 1
        return self._workspace_policies.get(workspace_id)

    def set_environment_rule(self, rule: EnvironmentAccessRule) -> EnvironmentAccessRule:
        self._telemetry["set_environment_rule_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        rule.created_at = now
        rule.updated_at = now
        self._environment_rules[rule.id] = rule
        self._save()
        logger.info("Set environment access rule: %s", rule.id)
        return rule

    def check_environment_access(self, environment: EnvironmentType, user: str, role: str) -> dict:
        self._telemetry["check_environment_access_calls"] += 1
        matching_rules = [r for r in self._environment_rules.values() if r.environment == environment]

        if not matching_rules:
            return {
                "allowed": True,
                "reason": "No restrictions defined for this environment",
                "environment": environment.value,
                "user": user,
                "role": role,
                "requires_approval": False,
            }

        for rule in matching_rules:
            if rule.allowed_roles and role not in rule.allowed_roles:
                continue
            if rule.allowed_users and user not in rule.allowed_users:
                continue

            return {
                "allowed": True,
                "reason": "Access granted by matching rule",
                "environment": environment.value,
                "user": user,
                "role": role,
                "rule_id": rule.id,
                "requires_approval": rule.require_approval,
            }

        return {
            "allowed": False,
            "reason": "No matching rule found for this user/role combination",
            "environment": environment.value,
            "user": user,
            "role": role,
            "requires_approval": False,
        }

    def create_location_restriction(self, restriction: LocationRestriction) -> LocationRestriction:
        self._telemetry["create_location_restriction_calls"] += 1
        now = datetime.now(timezone.utc).isoformat()
        restriction.created_at = now
        restriction.updated_at = now
        self._location_restrictions[restriction.id] = restriction
        self._save()
        logger.info("Created location restriction: %s (%s)", restriction.name, restriction.id)
        return restriction

    def check_location_access(self, ip_address: str, country: Optional[str] = None) -> bool:
        self._telemetry["check_location_access_calls"] += 1
        import ipaddress

        for restriction in self._location_restrictions.values():
            if country:
                if restriction.blocked_countries and country in restriction.blocked_countries:
                    return False
                if restriction.allowed_countries and country not in restriction.allowed_countries:
                    return False

            if restriction.allowed_ip_ranges:
                try:
                    addr = ipaddress.ip_address(ip_address)
                    allowed = any(addr in ipaddress.ip_network(cidr) for cidr in restriction.allowed_ip_ranges if cidr)
                    if not allowed:
                        return False
                except ValueError:
                    logger.warning("Invalid IP address: %s", ip_address)
                    return False

        return True

    def set_time_based_access(self, access: TimeBasedAccess) -> TimeBasedAccess:
        self._telemetry["set_time_based_access_calls"] += 1
        access.created_at = datetime.now(timezone.utc).isoformat()
        self._time_based_access[access.id] = access
        self._save()
        logger.info("Set time based access: %s", access.id)
        return access

    def check_time_based_access(self, user_id: str) -> dict:
        self._telemetry["check_time_based_access_calls"] += 1
        from datetime import datetime as dt

        now_utc = dt.now(timezone.utc)
        current_day = now_utc.strftime("%A")
        current_time = now_utc.strftime("%H:%M")

        access_records = [a for a in self._time_based_access.values() if a.user_id == user_id]

        if not access_records:
            return {
                "allowed": True,
                "reason": "No time-based restrictions for this user",
                "user_id": user_id,
                "active": True,
            }

        violations = []
        for record in access_records:
            if record.allowed_days and current_day not in record.allowed_days:
                violations.append(f"Day '{current_day}' not in allowed days for rule '{record.name}'")
                continue

            if record.allowed_start_time and current_time < record.allowed_start_time:
                violations.append(f"Current time {current_time} is before allowed start {record.allowed_start_time}")
                continue

            if record.allowed_end_time and current_time > record.allowed_end_time:
                violations.append(f"Current time {current_time} is after allowed end {record.allowed_end_time}")
                continue

            if record.expires_at:
                try:
                    if now_utc > dt.fromisoformat(record.expires_at):
                        violations.append(f"Access expired at {record.expires_at}")
                        continue
                except (ValueError, TypeError):
                    pass

            return {
                "allowed": True,
                "reason": "Time window is active",
                "user_id": user_id,
                "rule_id": record.id,
                "rule_name": record.name,
                "active": True,
            }

        return {
            "allowed": False,
            "reason": "; ".join(violations) if violations else "No matching time window",
            "user_id": user_id,
            "active": False,
        }

    def get_effective_permissions(self, org_id: str, user_id: str, resource_type: str) -> dict:
        self._telemetry["get_effective_permissions_calls"] += 1
        org_controls = self.list_controls(org_id)

        applicable_controls = [c for c in org_controls if c.enabled and (
            resource_type in c.tags or c.control_type in (
                ControlType.REPOSITORY_OWNERSHIP,
                ControlType.DEPARTMENT_POLICY,
                ControlType.BU_POLICY,
                ControlType.ENVIRONMENT_RESTRICTION,
            )
        )]

        effective_level = AccessLevel.NONE
        reasons = []

        for control in sorted(applicable_controls, key=lambda c: c.priority, reverse=True):
            for constraint in control.constraints:
                if isinstance(constraint, dict):
                    if constraint.get("type") == ConstraintType.ROLE_BASED.value:
                        if user_id in constraint.get("users", []):
                            level = AccessLevel(constraint.get("access_level", AccessLevel.READ.value))
                            if level.value != AccessLevel.NONE.value:
                                effective_level = level
                                reasons.append(f"Control '{control.name}' grants {level.value}")

        return {
            "org_id": org_id,
            "user_id": user_id,
            "resource_type": resource_type,
            "effective_access_level": effective_level.value,
            "reasons": reasons,
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)
