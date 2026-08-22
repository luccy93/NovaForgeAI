"""Knowledge service tests (Volume 54)."""
import pytest
from app.support.knowledge_service import KnowledgeService
from app.support.constants import ArticleStatus

@pytest.fixture()
def svc(): return KnowledgeService()

class TestArticleCRUD:
    def test_create_article(self, svc):
        a = svc.create_article("org1", title="How to deploy", content="Step by step", category="faq")
        assert a["id"] and a["title"] == "How to deploy" and a["status"] == ArticleStatus.DRAFT.value
    def test_get_article(self, svc):
        a = svc.create_article("org1", title="Test")
        assert svc.get_article(a["id"]) is not None
    def test_get_article_not_found(self, svc):
        assert svc.get_article("nonexistent") is None
    def test_update_article(self, svc):
        a = svc.create_article("org1", title="Old")
        svc.update_article(a["id"], title="New")
        assert svc.get_article(a["id"])["title"] == "New"
    def test_list_articles(self, svc):
        svc.create_article("org1", title="A1", category="faq")
        svc.create_article("org1", title="A2", category="runbook")
        assert len(svc.list_articles(tenant_id="org1")) == 2
    def test_list_articles_by_category(self, svc):
        svc.create_article("org1", title="A1", category="faq")
        svc.create_article("org1", title="A2", category="runbook")
        assert len(svc.list_articles(tenant_id="org1", category="faq")) == 1

class TestArticleStateMachine:
    def test_draft_to_review(self, svc):
        a = svc.create_article("org1", title="T")
        svc.transition_article(a["id"], "review")
        assert svc.get_article(a["id"])["status"] == "review"
    def test_review_to_published(self, svc):
        a = svc.create_article("org1", title="T")
        svc.transition_article(a["id"], "review")
        svc.transition_article(a["id"], "published")
        assert svc.get_article(a["id"])["status"] == "published"
    def test_published_to_archived(self, svc):
        a = svc.create_article("org1", title="T")
        svc.transition_article(a["id"], "review")
        svc.transition_article(a["id"], "published")
        svc.transition_article(a["id"], "archived")
        assert svc.get_article(a["id"])["status"] == "archived"
    def test_invalid_transition(self, svc):
        a = svc.create_article("org1", title="T")
        with pytest.raises(ValueError):
            svc.transition_article(a["id"], "published")

class TestKnowledgeSearch:
    def test_search_articles(self, svc):
        svc.create_article("org1", title="API deployment guide", content="How to deploy API", category="faq")
        results = svc.search_articles("deploy API", tenant_id="org1", status=None)
        assert len(results) >= 1
        assert results[0]["relevance_score"] > 0
    def test_search_published_only(self, svc):
        a = svc.create_article("org1", title="Draft article", category="faq")
        results = svc.search_articles("Draft article", tenant_id="org1", status="published")
        assert len(results) == 0

class TestKnowledgeGaps:
    def test_detect_gaps(self, svc):
        gaps = svc.detect_knowledge_gaps("org1")
        assert len(gaps) > 0
        assert any(g["type"] == "low_coverage" for g in gaps)

class TestArticleFeedback:
    def test_record_view(self, svc):
        a = svc.create_article("org1", title="T")
        svc.record_view(a["id"])
        assert svc.get_article(a["id"])["view_count"] == 1
    def test_record_feedback(self, svc):
        a = svc.create_article("org1", title="T")
        svc.record_feedback(a["id"], helpful=True)
        assert svc.get_article(a["id"])["helpful_count"] == 1

class TestArticleStats:
    def test_stats(self, svc):
        svc.create_article("org1", title="A1", category="faq")
        svc.create_article("org1", title="A2", category="faq")
        stats = svc.get_article_stats("org1")
        assert stats["total"] == 2
        assert stats["by_category"]["faq"] == 2

class TestKnowledgeTelemetry:
    def test_telemetry(self, svc):
        svc.create_article("org1", title="T")
        svc.search_articles("test", tenant_id="org1")
        t = svc.get_telemetry()
        assert t["created"] >= 1 and t["searches"] >= 1
