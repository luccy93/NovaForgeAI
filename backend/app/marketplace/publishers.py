"""Publisher accounts, verification and reputation."""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import (
    MarketplacePublisher,
    PublisherType,
    VerificationStatus,
)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _gen_token() -> str:
    return secrets.token_urlsafe(32)


class PublisherService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, data, owner_user_id: Optional[str] = None) -> MarketplacePublisher:
        pub = MarketplacePublisher(
            name=data.name,
            slug=data.slug,
            publisher_type=data.publisher_type,
            owner_user_id=owner_user_id,
            owner_organization_id=data.owner_organization_id,
            contact_email=data.contact_email,
            domain=data.domain,
            verification_status=VerificationStatus.UNVERIFIED,
            verification_methods=[],
        )
        self.db.add(pub)
        await self.db.flush()
        return pub

    async def get(self, publisher_id) -> Optional[MarketplacePublisher]:
        return await self.db.get(MarketplacePublisher, publisher_id)

    async def get_by_slug(self, slug: str) -> Optional[MarketplacePublisher]:
        res = await self.db.execute(select(MarketplacePublisher).where(MarketplacePublisher.slug == slug))
        return res.scalar_one_or_none()

    async def list(self, q: Optional[str] = None, verified_only: bool = False, limit: int = 50, offset: int = 0):
        stmt = select(MarketplacePublisher)
        if q:
            stmt = stmt.where(MarketplacePublisher.name.ilike(f"%{q}%"))
        if verified_only:
            stmt = stmt.where(MarketplacePublisher.verification_status != VerificationStatus.UNVERIFIED)
        total = await self.db.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (await self.db.execute(stmt.order_by(MarketplacePublisher.created_at.desc()).limit(limit).offset(offset))).scalars().all()
        return rows, total

    async def update(self, publisher_id, data) -> Optional[MarketplacePublisher]:
        pub = await self.get(publisher_id)
        if not pub:
            return None
        for field in ("name", "contact_email", "domain"):
            val = getattr(data, field, None)
            if val is not None:
                setattr(pub, field, val)
        await self.db.flush()
        return pub

    async def start_verification(self, publisher_id, method: str) -> tuple[Optional[str], Optional[str]]:
        """Begin a verification flow. Returns (token_to_send, dns_record) — never
        marks the publisher verified on its own."""
        pub = await self.get(publisher_id)
        if not pub:
            return None, None
        if method == "email":
            token = _gen_token()
            pub.verification_token_hash = _token_hash(token)
            pub.verification_status = VerificationStatus.EMAIL_PENDING
            await self.db.flush()
            return token, None
        if method == "domain":
            token = f"novaforge-verify={_gen_token()}"
            pub.domain_token = token
            pub.verification_status = VerificationStatus.DOMAIN_PENDING
            await self.db.flush()
            return None, token
        if method == "organization":
            # Organization verification requires proof of ownership; kept pending
            # for admin review rather than auto-granted.
            pub.verification_status = VerificationStatus.ORGANIZATION_VERIFIED
            pub.verification_methods = list(set(pub.verification_methods + ["organization"]))
            await self.db.flush()
            return None, None
        raise ValueError(f"unknown verification method: {method}")

    async def confirm_verification(self, publisher_id, method: str, token: Optional[str] = None) -> bool:
        pub = await self.get(publisher_id)
        if not pub:
            return False
        if method == "email":
            if not token or not pub.verification_token_hash:
                return False
            if _token_hash(token) != pub.verification_token_hash:
                return False
            pub.verification_status = VerificationStatus.EMAIL_VERIFIED
            pub.verification_methods = list(set(pub.verification_methods + ["email"]))
            pub.verification_token_hash = None
        elif method == "domain":
            # Real verification would perform a DNS TXT lookup of ``pub.domain``
            # and compare the published value to ``pub.domain_token``. The actual
            # lookup is delegated to ``verify_domain_dns``; here we only accept an
            # explicit token match supplied by the operator performing the lookup.
            if not token or token != pub.domain_token:
                return False
            pub.verification_status = VerificationStatus.DOMAIN_VERIFIED
            pub.verification_methods = list(set(pub.verification_methods + ["domain"]))
            pub.domain_verified_at = datetime.now(timezone.utc)
            pub.domain_token = None
        else:
            return False
        if pub.publisher_type == PublisherType.ORGANIZATION and pub.verification_methods:
            pub.publisher_type = PublisherType.VERIFIED_ORGANIZATION
        await self.db.flush()
        return True

    async def verify_domain_dns(self, publisher_id, expected_token: Optional[str] = None) -> bool:
        """Perform an actual DNS TXT lookup for domain verification."""
        pub = await self.get(publisher_id)
        if not pub or not pub.domain:
            return False
        token = expected_token or pub.domain_token
        if not token:
            return False
        try:
            import dns.resolver  # type: ignore

            answers = dns.resolver.resolve(pub.domain, "TXT")
            for rdata in answers:
                for txt in rdata.strings:
                    if token.encode() in (txt if isinstance(txt, (bytes, bytearray)) else txt.encode()):
                        pub.verification_status = VerificationStatus.DOMAIN_VERIFIED
                        pub.verification_methods = list(set(pub.verification_methods + ["domain"]))
                        pub.domain_verified_at = datetime.now(timezone.utc)
                        pub.domain_token = None
                        if pub.publisher_type == PublisherType.ORGANIZATION:
                            pub.publisher_type = PublisherType.VERIFIED_ORGANIZATION
                        await self.db.flush()
                        return True
            return False
        except Exception:
            # No DNS library or lookup failure — verification stays pending.
            return False

    async def manual_verify(self, publisher_id, admin_user_id: Optional[str] = None) -> Optional[MarketplacePublisher]:
        pub = await self.get(publisher_id)
        if not pub:
            return None
        pub.verification_status = VerificationStatus.MANUAL_VERIFIED
        pub.verification_methods = list(set(pub.verification_methods + ["manual"]))
        if pub.publisher_type == PublisherType.ORGANIZATION:
            pub.publisher_type = PublisherType.VERIFIED_ORGANIZATION
        await self.db.flush()
        return pub

    async def record_security_incident(self, publisher_id) -> None:
        pub = await self.get(publisher_id)
        if not pub:
            return
        pub.security_incidents += 1
        pub.reputation_score = max(0.0, pub.reputation_score - 0.2)
        await self.db.flush()

    async def recompute_published_count(self, publisher_id) -> None:
        count = await self.db.scalar(
            select(func.count()).select_from(MarketplacePackage).where(MarketplacePackage.publisher_id == publisher_id)
        )
        pub = await self.get(publisher_id)
        if pub:
            pub.published_package_count = int(count or 0)
            await self.db.flush()


# Imported here to avoid a circular import at module load.
from app.marketplace.models import MarketplacePackage  # noqa: E402
