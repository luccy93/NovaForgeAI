"""Knowledge service — article CRUD, state machine, search, gap detection (Volume 54)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.support.constants import ArticleStatus, ARTICLE_TRANSITIONS

logger = logging.getLogger(__name__)


class KnowledgeService:
    def __init__(self):
        self._articles: dict[str, dict] = {}
        self._telemetry = {"created": 0, "published": 0, "searches": 0, "gaps_detected": 0}

    def create_article(
        self,
        tenant_id: str,
        title: str,
        content: str = "",
        category: str = "faq",
        product: Optional[str] = None,
        version: Optional[str] = None,
        owner_id: Optional[str] = None,
        source_type: Optional[str] = None,
        source_url: Optional[str] = None,
        tags: Optional[list[str]] = None,
        ai_generated: bool = False,
        ai_confidence: Optional[float] = None,
    ) -> dict:
        article_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        article = {
            "id": article_id,
            "tenant_id": tenant_id,
            "title": title,
            "content": content,
            "category": category,
            "product": product,
            "version": version,
            "owner_id": owner_id,
            "status": ArticleStatus.DRAFT.value,
            "source_type": source_type,
            "source_url": source_url,
            "tags": tags or [],
            "ai_generated": ai_generated,
            "ai_confidence": ai_confidence,
            "view_count": 0,
            "helpful_count": 0,
            "not_helpful_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._articles[article_id] = article
        self._telemetry["created"] += 1
        return article

    def get_article(self, article_id: str) -> Optional[dict]:
        return self._articles.get(article_id)

    def update_article(self, article_id: str, **fields) -> Optional[dict]:
        article = self._articles.get(article_id)
        if not article:
            return None
        for k, v in fields.items():
            if v is not None and k in article and k not in ("id", "created_at"):
                article[k] = v
        article["updated_at"] = datetime.now(timezone.utc).isoformat()
        return article

    def transition_article(self, article_id: str, new_status: str) -> Optional[dict]:
        article = self._articles.get(article_id)
        if not article:
            return None
        current = ArticleStatus(article["status"])
        target = ArticleStatus(new_status)
        allowed = ARTICLE_TRANSITIONS.get(current, [])
        if target not in allowed:
            raise ValueError(
                f"Invalid article transition: {current.value} → {new_status}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        article["status"] = target.value
        article["updated_at"] = datetime.now(timezone.utc).isoformat()
        if target == ArticleStatus.PUBLISHED:
            self._telemetry["published"] += 1
        return article

    def list_articles(
        self,
        tenant_id: Optional[str] = None,
        category: Optional[str] = None,
        product: Optional[str] = None,
        status: Optional[str] = None,
        tag: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        results = list(self._articles.values())
        if tenant_id:
            results = [a for a in results if a["tenant_id"] == tenant_id]
        if category:
            results = [a for a in results if a["category"] == category]
        if product:
            results = [a for a in results if a.get("product") == product]
        if status:
            results = [a for a in results if a["status"] == status]
        if tag:
            results = [a for a in results if tag in (a.get("tags") or [])]
        results.sort(key=lambda a: a["updated_at"], reverse=True)
        return results[offset:offset + limit]

    def search_articles(
        self,
        query: str,
        tenant_id: Optional[str] = None,
        category: Optional[str] = None,
        product: Optional[str] = None,
        status: Optional[str] = "published",
        limit: int = 20,
    ) -> list[dict]:
        query_lower = query.lower()
        words = set(query_lower.split())
        results = []
        for article in self._articles.values():
            if tenant_id and article["tenant_id"] != tenant_id:
                continue
            if status and article["status"] != status:
                continue
            if category and article["category"] != category:
                continue
            if product and article.get("product") != product:
                continue
            text = f"{article['title']} {article['content']} {' '.join(article.get('tags') or [])}".lower()
            score = sum(1 for w in words if w in text)
            if score > 0:
                results.append((score, article))
        results.sort(key=lambda x: x[0], reverse=True)
        self._telemetry["searches"] += 1
        return [{"article": a, "relevance_score": s} for s, a in results[:limit]]

    def get_published_articles(self, tenant_id: Optional[str] = None,
                              category: Optional[str] = None) -> list[dict]:
        return self.list_articles(tenant_id=tenant_id, category=category,
                                 status=ArticleStatus.PUBLISHED.value)

    def record_view(self, article_id: str) -> Optional[dict]:
        article = self._articles.get(article_id)
        if article:
            article["view_count"] = article.get("view_count", 0) + 1
        return article

    def record_feedback(self, article_id: str, helpful: bool) -> Optional[dict]:
        article = self._articles.get(article_id)
        if not article:
            return None
        if helpful:
            article["helpful_count"] = article.get("helpful_count", 0) + 1
        else:
            article["not_helpful_count"] = article.get("not_helpful_count", 0) + 1
        return article

    def detect_knowledge_gaps(
        self,
        tenant_id: str,
        ticket_categories: Optional[list[str]] = None,
        low_confidence_tickets: Optional[list[dict]] = None,
    ) -> list[dict]:
        gaps = []
        published = self.list_articles(tenant_id=tenant_id, status=ArticleStatus.PUBLISHED.value)
        published_by_category: dict[str, list[dict]] = {}
        for a in published:
            published_by_category.setdefault(a["category"], []).append(a)

        all_categories = [
            "question", "bug", "feature_request", "billing", "security",
            "account", "deployment", "performance", "incident", "integration",
            "documentation", "access",
        ]
        for cat in all_categories:
            articles = published_by_category.get(cat, [])
            if len(articles) < 2:
                gaps.append({
                    "type": "low_coverage",
                    "category": cat,
                    "article_count": len(articles),
                    "recommendation": f"Create more knowledge articles for category '{cat}'",
                })

        if low_confidence_tickets:
            for ticket in low_confidence_tickets[:5]:
                gaps.append({
                    "type": "low_ai_confidence",
                    "ticket_id": ticket.get("id"),
                    "subject": ticket.get("subject"),
                    "ai_confidence": ticket.get("ai_confidence"),
                    "recommendation": "AI could not confidently answer — consider creating a knowledge article",
                })

        self._telemetry["gaps_detected"] += len(gaps)
        return gaps

    def get_article_stats(self, tenant_id: Optional[str] = None) -> dict:
        articles = self.list_articles(tenant_id=tenant_id, limit=10000)
        by_status = {}
        by_category = {}
        for a in articles:
            by_status[a["status"]] = by_status.get(a["status"], 0) + 1
            by_category[a["category"]] = by_category.get(a["category"], 0) + 1
        total_views = sum(a.get("view_count", 0) for a in articles)
        total_helpful = sum(a.get("helpful_count", 0) for a in articles)
        return {
            "total": len(articles),
            "by_status": by_status,
            "by_category": by_category,
            "total_views": total_views,
            "total_helpful": total_helpful,
        }

    def get_telemetry(self) -> dict:
        return dict(self._telemetry)


knowledge_service = KnowledgeService()
