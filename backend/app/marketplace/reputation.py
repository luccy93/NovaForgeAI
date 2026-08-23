"""Package reputation — transparent, evidence-backed, not a security guarantee."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.marketplace.models import MarketplacePackage, MarketplacePublisher


def compute_reputation(
    package: MarketplacePackage,
    publisher: Optional[MarketplacePublisher],
    health_score: Optional[float] = None,
) -> dict:
    """Compute reputation from security history, reliability, maintenance, verification, feedback."""
    score = 0.5
    factors: list[dict] = []

    if publisher:
        verified = publisher.verification_status.value.endswith("verified") if hasattr(publisher.verification_status, "value") else False
        if verified:
            score += 0.2
            factors.append({"factor": "verified_publisher", "delta": 0.2, "detail": "Publisher is verified"})
        if publisher.security_incidents == 0:
            score += 0.1
            factors.append({"factor": "no_incidents", "delta": 0.1, "detail": "No security incidents"})
        else:
            delta = min(0.3, publisher.security_incidents * 0.1)
            score -= delta
            factors.append({"factor": "security_incidents", "delta": -delta, "detail": f"{publisher.security_incidents} incidents"})

    # Rating
    if package.rating_count > 0:
        # 0..5 -> 0..0.2
        delta = (package.average_rating / 5.0) * 0.2
        score += delta
        factors.append({"factor": "rating", "delta": round(delta, 3), "detail": f"avg {package.average_rating} over {package.rating_count}"})

    # Installs / maintenance (log scale)
    if package.install_count > 100:
        score += 0.05
        factors.append({"factor": "popular", "delta": 0.05, "detail": f"{package.install_count} installs"})
    if health_score is not None:
        delta = (health_score - 0.5) * 0.2
        score += delta
        factors.append({"factor": "health", "delta": round(delta, 3), "detail": f"health {health_score:.2f}"})

    # Security status penalty if failed
    if str(package.security_status.value) == "failed":
        score -= 0.3
        factors.append({"factor": "security_failed", "delta": -0.3, "detail": "Security scan failed"})

    score = max(0.0, min(1.0, score))
    level = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    return {"reputation_score": round(score, 3), "level": level, "factors": factors, "note": "Reputation is not a security guarantee"}
