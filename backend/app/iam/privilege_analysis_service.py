"""Privilege analysis service — detect unused admin roles, overly broad permissions, expired access, orphaned service accounts."""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Optional


class PrivilegeAnalysisService:
    def __init__(self):
        self._analyses: list[dict] = []

    def analyze_unused_admin_roles(self, org_id: str, memberships: list[dict], activity_data: Optional[dict] = None) -> dict:
        findings = []
        for mem in memberships:
            if mem.get("role") in ("owner", "admin") and mem.get("is_active"):
                user_id = mem["user_id"]
                if activity_data and user_id in activity_data:
                    last_active = activity_data[user_id].get("last_active_at")
                    if not last_active:
                        findings.append({"user_id": user_id, "role": mem["role"], "finding": "no_activity_recorded", "severity": "medium"})
                else:
                    findings.append({"user_id": user_id, "role": mem["role"], "finding": "no_activity_data", "severity": "low"})
        risk_score = min(len(findings) * 0.1, 1.0)
        recommendation = "Review admin roles and verify each admin is actively using their privileges." if findings else "No unused admin roles detected."
        result = {"org_id": org_id, "analysis_type": "unused_admin_roles", "findings": findings, "risk_score": risk_score, "recommendations": [recommendation], "analyzed_at": datetime.now(timezone.utc).isoformat()}
        self._analyses.append(result)
        return result

    def analyze_overly_broad_permissions(self, org_id: str, memberships: list[dict], resource_policies: list[dict]) -> dict:
        findings = []
        for mem in memberships:
            if mem.get("role") == "owner":
                findings.append({"user_id": mem["user_id"], "role": mem["role"], "finding": "owner_role_granted", "severity": "low", "note": "Owner role has full access by design"})
        for policy in resource_policies:
            if policy.get("resource_scope") == "organization" and policy.get("effect") == "allow":
                actions = policy.get("actions", [])
                if "*" in actions or len(actions) > 10:
                    findings.append({"policy_id": policy["id"], "name": policy["name"], "finding": "overly_broad_policy", "severity": "high", "actions_count": len(actions)})
        risk_score = min(len(findings) * 0.15, 1.0)
        recommendation = "Review overly broad policies and consider scoping them to specific resources." if findings else "No overly broad permissions detected."
        result = {"org_id": org_id, "analysis_type": "overly_broad_permissions", "findings": findings, "risk_score": risk_score, "recommendations": [recommendation], "analyzed_at": datetime.now(timezone.utc).isoformat()}
        self._analyses.append(result)
        return result

    def analyze_expired_access(self, org_id: str, service_accounts: list[dict], api_keys: list[dict]) -> dict:
        findings = []
        now = datetime.now(timezone.utc)
        for sa in service_accounts:
            if sa.get("is_active") and sa.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(sa["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if now > expires:
                        findings.append({"resource_id": sa["id"], "name": sa["name"], "type": "service_account", "finding": "expired_active", "severity": "high"})
                except (ValueError, TypeError):
                    pass
        for key in api_keys:
            if key.get("is_active") and key.get("expires_at"):
                try:
                    expires = datetime.fromisoformat(key["expires_at"])
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    if now > expires:
                        findings.append({"resource_id": key["id"], "name": key["name"], "type": "api_key", "finding": "expired_active", "severity": "medium"})
                except (ValueError, TypeError):
                    pass
        risk_score = min(len(findings) * 0.2, 1.0)
        recommendation = "Disable expired service accounts and API keys." if findings else "No expired access detected."
        result = {"org_id": org_id, "analysis_type": "expired_access", "findings": findings, "risk_score": risk_score, "recommendations": [recommendation], "analyzed_at": datetime.now(timezone.utc).isoformat()}
        self._analyses.append(result)
        return result

    def analyze_orphaned_service_accounts(self, org_id: str, service_accounts: list[dict], active_users: list[str]) -> dict:
        findings = []
        for sa in service_accounts:
            if sa.get("is_active") and sa.get("created_by") and sa["created_by"] not in active_users:
                findings.append({"sa_id": sa["id"], "name": sa["name"], "created_by": sa["created_by"], "finding": "orphaned_service_account", "severity": "high"})
        risk_score = min(len(findings) * 0.25, 1.0)
        recommendation = "Review orphaned service accounts created by deactivated users." if findings else "No orphaned service accounts detected."
        result = {"org_id": org_id, "analysis_type": "orphaned_service_accounts", "findings": findings, "risk_score": risk_score, "recommendations": [recommendation], "analyzed_at": datetime.now(timezone.utc).isoformat()}
        self._analyses.append(result)
        return result

    def analyze_long_lived_api_keys(self, org_id: str, api_keys: list[dict], max_age_days: int = 90) -> dict:
        findings = []
        now = datetime.now(timezone.utc)
        for key in api_keys:
            if key.get("is_active") and key.get("created_at"):
                try:
                    created = datetime.fromisoformat(key["created_at"])
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    age_days = (now - created).days
                    if age_days > max_age_days:
                        findings.append({"key_id": key["id"], "name": key["name"], "age_days": age_days, "finding": "long_lived_api_key", "severity": "medium"})
                except (ValueError, TypeError):
                    pass
        risk_score = min(len(findings) * 0.1, 1.0)
        recommendation = f"Rotate API keys older than {max_age_days} days." if findings else "No long-lived API keys detected."
        result = {"org_id": org_id, "analysis_type": "long_lived_api_keys", "findings": findings, "risk_score": risk_score, "recommendations": [recommendation], "analyzed_at": datetime.now(timezone.utc).isoformat()}
        self._analyses.append(result)
        return result

    def run_full_analysis(self, org_id: str, memberships: list[dict], service_accounts: list[dict], api_keys: list[dict], resource_policies: list[dict], active_users: Optional[list[str]] = None, activity_data: Optional[dict] = None) -> dict:
        results = []
        results.append(self.analyze_unused_admin_roles(org_id, memberships, activity_data))
        results.append(self.analyze_overly_broad_permissions(org_id, memberships, resource_policies))
        results.append(self.analyze_expired_access(org_id, service_accounts, api_keys))
        if active_users:
            results.append(self.analyze_orphaned_service_accounts(org_id, service_accounts, active_users))
        results.append(self.analyze_long_lived_api_keys(org_id, api_keys))
        total_findings = sum(len(r["findings"]) for r in results)
        avg_risk = sum(r["risk_score"] for r in results) / len(results) if results else 0
        all_recommendations = []
        for r in results:
            all_recommendations.extend(r["recommendations"])
        return {"org_id": org_id, "total_analyses": len(results), "total_findings": total_findings, "average_risk_score": round(avg_risk, 2), "analyses": results, "recommendations": all_recommendations, "requires_human_approval": total_findings > 0, "analyzed_at": datetime.now(timezone.utc).isoformat()}

    def get_analyses(self, org_id: Optional[str] = None, limit: int = 10) -> list[dict]:
        analyses = list(self._analyses)
        if org_id:
            analyses = [a for a in analyses if a.get("org_id") == org_id]
        return analyses[-limit:]


privilege_analysis_service = PrivilegeAnalysisService()
