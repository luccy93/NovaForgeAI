"""License policy enforcement — allow/deny/review-required.

Organizations can define which licenses are permitted. Installation is blocked
if the package license violates the org policy; no legal interpretation is
provided, only policy enforcement.
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import MarketplaceLicensePolicy


class LicensePolicyService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_policy(
        self,
        organization_id: str,
        name: str,
        allowed_licenses: Optional[list] = None,
        denied_licenses: Optional[list] = None,
        review_required_licenses: Optional[list] = None,
    ) -> MarketplaceLicensePolicy:
        pol = MarketplaceLicensePolicy(
            organization_id=organization_id,
            name=name,
            allowed_licenses=allowed_licenses or [],
            denied_licenses=denied_licenses or [],
            review_required_licenses=review_required_licenses or [],
            is_active=True,
        )
        self.db.add(pol)
        await self.db.flush()
        return pol

    async def list_policies(self, organization_id: str) -> list[MarketplaceLicensePolicy]:
        res = await self.db.execute(
            select(MarketplaceLicensePolicy).where(
                MarketplaceLicensePolicy.organization_id == organization_id,
                MarketplaceLicensePolicy.is_active == True,  # noqa: E712
            )
        )
        return list(res.scalars().all())

    async def evaluate(self, organization_id: str, license_id: str) -> tuple[str, str]:
        """Returns (action, reason) where action in allow|deny|review_required."""
        policies = await self.list_policies(organization_id)
        if not policies:
            return "allow", "no license policy configured"
        lic = (license_id or "").strip()
        for pol in policies:
            if lic in (pol.denied_licenses or []):
                return "deny", f"license '{lic}' denied by policy '{pol.name}'"
            if lic in (pol.review_required_licenses or []):
                return "review_required", f"license '{lic}' requires review per '{pol.name}'"
            if pol.allowed_licenses:
                if lic not in pol.allowed_licenses:
                    return "review_required", f"license '{lic}' not in allowlist of '{pol.name}'"
        return "allow", "license permitted"

    async def is_blocked(self, organization_id: str, license_id: str) -> tuple[bool, str]:
        action, reason = await self.evaluate(organization_id, license_id)
        return (action == "deny"), reason
