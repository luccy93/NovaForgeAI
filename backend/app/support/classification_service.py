"""Classification service — AI classification, sentiment, duplicate detection (Volume 54)."""

from __future__ import annotations

import logging
import re
from typing import Optional

from app.support.constants import (
    TicketCategory, SentimentLevel, AI_CONFIDENCE_HUMAN_REVIEW_THRESHOLD,
)

logger = logging.getLogger(__name__)

# ─── Keyword-based classification rules ───────────────────────────────
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    TicketCategory.BILLING.value: [
        "invoice", "charge", "payment", "refund", "subscription", "plan",
        "billing", "credit card", "receipt", "prorate", "upgrade", "downgrade",
    ],
    TicketCategory.BUG.value: [
        "bug", "error", "crash", "broken", "not working", "fails", "exception",
        "500", "404", "regression", "defect", "unexpected", "wrong", "malfunction",
    ],
    TicketCategory.SECURITY.value: [
        "security", "vulnerability", "cve", "breach", "exploit", "injection",
        "xss", "csrf", "authentication bypass", "unauthorized", "penetration",
    ],
    TicketCategory.ACCOUNT.value: [
        "account", "login", "password", "mfa", "sso", "profile", "email change",
        "sign in", "log in", "locked out", "2fa", "reset password",
    ],
    TicketCategory.ACCESS.value: [
        "access", "permission", "role", "rbac", "authorization", "denied",
        "forbidden", "403", "not authorized", "grant access", " revoke",
    ],
    TicketCategory.PERFORMANCE.value: [
        "slow", "latency", "timeout", "performance", "memory", "cpu",
        "response time", "bottleneck", "lag", "throttle", "optimization",
    ],
    TicketCategory.DEPLOYMENT.value: [
        "deploy", "deployment", "release", "rollback", "ci/cd", "pipeline",
        "build", "container", "docker", "kubernetes", "k8s", "helm",
    ],
    TicketCategory.FEATURE_REQUEST.value: [
        "feature request", "suggestion", "enhancement", "would be nice",
        "could you add", "please add", "wish list", "roadmap", "request",
    ],
    TicketCategory.INCIDENT.value: [
        "incident", "outage", "downtime", "service down", "unavailable",
        "degraded", "emergency", "sev1", "sev2", "p0", "p1",
    ],
    TicketCategory.INTEGRATION.value: [
        "integration", "api", "webhook", "connector", "plugin", "third-party",
        "external", "import", "export", "sync", "rest api", "graphql",
    ],
    TicketCategory.DOCUMENTATION.value: [
        "documentation", "docs", "example", "tutorial", "guide", "how to",
        "documentation missing", "unclear", "outdated",
    ],
    TicketCategory.QUESTION.value: [
        "how do", "how can", "what is", "where can", "is it possible",
        "can you", "question", "help", "support", "assist",
    ],
}

# ─── Sentiment keywords ───────────────────────────────────────────────
_NEGATIVE_SIGNALS = [
    "angry", "frustrated", "terrible", "awful", "horrible", "worst",
    "unacceptable", "ridiculous", "waste", "furious", "disappointed",
    "disgusted", "hate", "useless", "pathetic", "incompetent",
]
_POSITIVE_SIGNALS = [
    "thank", "thanks", "great", "excellent", "wonderful", "awesome",
    "helpful", "perfect", "love", "appreciate", "fantastic", "amazing",
]
_URGENCY_SIGNALS = [
    "urgent", "critical", "emergency", "asap", "immediately", "blocker",
    "production down", "p0", "sev1", "losing money", "data loss",
]


class ClassificationService:
    def __init__(self):
        self._classifications: dict[str, dict] = {}
        self._telemetry = {"classified": 0, "low_confidence": 0}

    def classify_ticket(
        self,
        subject: str,
        description: str = "",
        service_affected: Optional[str] = None,
        customer_context: Optional[dict] = None,
    ) -> dict:
        text = f"{subject} {description}".lower()
        words = set(re.findall(r'\b\w+\b', text))

        scores: dict[str, float] = {}
        for category, keywords in _CATEGORY_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scores[category] = score

        if not scores:
            best_category = TicketCategory.QUESTION.value
            confidence = 0.3
        else:
            best_category = max(scores, key=scores.get)
            max_score = scores[best_category]
            total_score = sum(scores.values())
            confidence = min(0.95, max_score / max(total_score, 1) * (1 + 0.1 * max_score))
            confidence = round(confidence, 2)

        sentiment = self._analyze_sentiment(text)

        result = {
            "category": best_category,
            "confidence": confidence,
            "all_scores": scores,
            "sentiment": sentiment,
            "needs_human_review": confidence < AI_CONFIDENCE_HUMAN_REVIEW_THRESHOLD,
            "reasoning": self._build_reasoning(best_category, confidence, scores, sentiment),
        }
        self._telemetry["classified"] += 1
        if confidence < AI_CONFIDENCE_HUMAN_REVIEW_THRESHOLD:
            self._telemetry["low_confidence"] += 1
        return result

    def classify_from_text(self, text: str) -> dict:
        return self.classify_ticket(subject=text)

    def detect_duplicates(
        self,
        tenant_id: str,
        subject: str,
        description: str,
        customer_id: Optional[str] = None,
        service_affected: Optional[str] = None,
        existing_tickets: Optional[list[dict]] = None,
    ) -> list[dict]:
        from app.support.constants import DUPLICATE_SIMILARITY_THRESHOLD
        query_words = set(re.findall(r'\b\w+\b', f"{subject} {description}".lower()))
        candidates = []
        for ticket in (existing_tickets or []):
            if ticket.get("tenant_id") != tenant_id:
                continue
            existing_words = set(re.findall(r'\b\w+\b',
                                f"{ticket.get('subject', '')} {ticket.get('description', '')}".lower()))
            if not query_words or not existing_words:
                continue
            intersection = query_words & existing_words
            union = query_words | existing_words
            similarity = len(intersection) / len(union) if union else 0
            if similarity >= DUPLICATE_SIMILARITY_THRESHOLD:
                if customer_id and ticket.get("customer_id") == customer_id:
                    similarity += 0.1
                if service_affected and ticket.get("service_affected") == service_affected:
                    similarity += 0.05
                candidates.append({
                    "ticket_id": ticket.get("id"),
                    "similarity": round(min(similarity, 1.0), 3),
                    "subject": ticket.get("subject"),
                    "status": ticket.get("status"),
                })
        candidates.sort(key=lambda x: x["similarity"], reverse=True)
        return candidates[:10]

    def _analyze_sentiment(self, text: str) -> dict:
        neg_count = sum(1 for s in _NEGATIVE_SIGNALS if s in text)
        pos_count = sum(1 for s in _POSITIVE_SIGNALS if s in text)
        urgency_count = sum(1 for s in _URGENCY_SIGNALS if s in text)
        raw_score = pos_count - neg_count
        if raw_score <= -2:
            level = SentimentLevel.VERY_NEGATIVE.value
            score = -0.8
        elif raw_score < 0:
            level = SentimentLevel.NEGATIVE.value
            score = -0.4
        elif raw_score == 0:
            level = SentimentLevel.NEUTRAL.value
            score = 0.0
        elif raw_score <= 2:
            level = SentimentLevel.POSITIVE.value
            score = 0.4
        else:
            level = SentimentLevel.VERY_POSITIVE.value
            score = 0.8
        return {"level": level, "score": score, "urgency_signals": urgency_count}

    def _build_reasoning(self, category: str, confidence: float, scores: dict, sentiment: dict) -> str:
        parts = [f"Classified as '{category}' with confidence {confidence:.0%}"]
        if len(scores) > 1:
            runners_up = sorted(scores.items(), key=lambda x: x[1], reverse=True)[1:3]
            parts.append(f"Runners-up: {', '.join(f'{k}({v})' for k, v in runners_up)}")
        if sentiment.get("urgency_signals", 0) > 0:
            parts.append(f"Detected {sentiment['urgency_signals']} urgency signal(s)")
        return ". ".join(parts)

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


classification_service = ClassificationService()
