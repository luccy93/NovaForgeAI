"""Domain verification service — verify organization domains via DNS."""
from __future__ import annotations
import uuid
import secrets
from datetime import datetime, timezone
from typing import Optional


class DomainVerificationService:
    def __init__(self):
        self._verifications: dict[str, dict] = {}

    def create_verification(self, org_id: str, domain: str, method: str = "dns") -> dict:
        existing = [v for v in self._verifications.values() if v["domain"] == domain and v["is_verified"]]
        if existing:
            return {"error": f"Domain '{domain}' is already verified by another organization"}
        ver_id = str(uuid.uuid4())
        token = f"novaforge-verify-{secrets.token_hex(16)}"
        verification = {"id": ver_id, "organization_id": org_id, "domain": domain, "verification_token": token, "method": method, "is_verified": False, "created_at": datetime.now(timezone.utc).isoformat(), "verified_at": None}
        self._verifications[ver_id] = verification
        return verification

    def get_verification(self, verification_id: str) -> Optional[dict]:
        return self._verifications.get(verification_id)

    def verify(self, verification_id: str, proof: str = "") -> dict:
        verification = self._verifications.get(verification_id)
        if not verification:
            return {"verified": False, "error": "Verification not found"}
        if verification["is_verified"]:
            return {"verified": True, "message": "Domain already verified"}
        if verification["method"] == "dns":
            if proof and verification["verification_token"] in proof:
                verification["is_verified"] = True
                verification["verified_at"] = datetime.now(timezone.utc).isoformat()
                return {"verified": True, "domain": verification["domain"]}
            return {"verified": False, "error": "DNS verification token not found in proof"}
        verification["is_verified"] = True
        verification["verified_at"] = datetime.now(timezone.utc).isoformat()
        return {"verified": True, "domain": verification["domain"]}

    def list_for_org(self, org_id: str) -> list[dict]:
        return [v for v in self._verifications.values() if v["organization_id"] == org_id]

    def get_verified_domain(self, domain: str) -> Optional[dict]:
        for v in self._verifications.values():
            if v["domain"] == domain and v["is_verified"]:
                return v
        return None

    def is_domain_verified(self, domain: str) -> bool:
        return self.get_verified_domain(domain) is not None

    def revoke(self, verification_id: str) -> bool:
        v = self._verifications.get(verification_id)
        if not v:
            return False
        v["is_verified"] = False
        v["revoked_at"] = datetime.now(timezone.utc).isoformat()
        return True

    def get_organization_domains(self, org_id: str) -> list[dict]:
        return [v for v in self._verifications.values() if v["organization_id"] == org_id]

    def get_stats(self, org_id: Optional[str] = None) -> dict:
        verifs = list(self._verifications.values())
        if org_id:
            verifs = [v for v in verifs if v["organization_id"] == org_id]
        return {"total": len(verifs), "verified": sum(1 for v in verifs if v["is_verified"]), "pending": sum(1 for v in verifs if not v["is_verified"])}


domain_verification_service = DomainVerificationService()
