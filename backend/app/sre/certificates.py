"""TLS certificate monitoring (Volume 35).

Probes TLS certificates (real connectivity, never fabricated) and records
their state. Alerts are raised before expiration per the configurable
warning window. Automated renewal is surfaced as a supported action but
only performed by operators (or policy-approved automation).
"""

import logging
import socket
import ssl
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sre.constants import CERT_EXPIRING, CERT_EXPIRED, CERT_EXPIRY_WARNING_DAYS, CERT_FAILED, CERT_VALID
from app.sre.models import SRECertificate
from app.sre.store import new_key

logger = logging.getLogger(__name__)


def probe_certificate(hostname: str, port: int = 443, timeout: float = 5.0) -> dict:
    """Fetch the TLS certificate for a hostname (synchronous network call)."""
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=hostname) as tls:
                der = tls.getpeercert(True)
                cert = ssl.DER_cert_to_PEM_cert(der)
                parsed = ssl.load_pem_x509_certificate(cert.encode())
                not_before = datetime.fromtimestamp(ssl.cert_time_to_seconds(parsed.get_notBefore()), tz=timezone.utc)
                not_after = datetime.fromtimestamp(ssl.cert_time_to_seconds(parsed.get_notAfter()), tz=timezone.utc)
                issuer = parsed.get_issuer().rfc4514_string()
                return {"status": "ok", "hostname": hostname, "issuer": issuer, "not_before": not_before, "not_after": not_after}
    except Exception as exc:
        return {"status": "error", "hostname": hostname, "error": str(exc)}


def classify_expiry(not_after: datetime, warning_days: int = CERT_EXPIRY_WARNING_DAYS) -> str:
    remaining = (not_after - datetime.now(timezone.utc)).total_seconds()
    if remaining <= 0:
        return CERT_EXPIRED
    if remaining <= warning_days * 86400:
        return CERT_EXPIRING
    return CERT_VALID


async def ensure_certificate(
    db: AsyncSession,
    *,
    name: str,
    hostname: str,
    auto_renew: bool = False,
) -> SRECertificate:
    result = await db.execute(select(SRECertificate).where(SRECertificate.hostname == hostname))
    cert = result.scalar_one_or_none()
    if cert is not None:
        return cert
    cert = SRECertificate(
        certificate_id=new_key("cert"),
        name=name,
        hostname=hostname,
        auto_renew=auto_renew,
    )
    db.add(cert)
    await db.flush()
    return cert


async def check_certificates(db: AsyncSession, *, warning_days: int = CERT_EXPIRY_WARNING_DAYS) -> list[dict]:
    """Probe every registered certificate and update status. Returns
    records whose status is expiring/expired (candidates for alerts)."""
    result = await db.execute(select(SRECertificate))
    certificates = list(result.scalars().all())
    changed = []
    for cert in certificates:
        probe = probe_certificate(cert.hostname)
        if probe["status"] == "ok":
            cert.not_before = probe["not_before"]
            cert.not_after = probe["not_after"]
            cert.issuer = probe["issuer"]
            cert.status = classify_expiry(cert.not_after, warning_days)
        else:
            cert.status = CERT_FAILED
        cert.last_checked_at = datetime.now(timezone.utc)
        if cert.status in (CERT_EXPIRING, CERT_EXPIRED, CERT_FAILED):
            changed.append(cert.to_dict())
    await db.flush()
    return changed


def cert_alert_message(cert: dict) -> str:
    status = cert.get("status")
    not_after = cert.get("not_after")
    if status == CERT_EXPIRED:
        return f"TLS certificate {cert.get('name')} for {cert.get('hostname')} has EXPIRED (was {not_after})"
    if status == CERT_EXPIRING:
        return f"TLS certificate {cert.get('name')} for {cert.get('hostname')} expires soon ({not_after})"
    return f"TLS certificate check failed for {cert.get('hostname')}: {cert.get('metadata', {})}"