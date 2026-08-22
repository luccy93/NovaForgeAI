"""Classification service tests (Volume 54)."""

import pytest
from app.support.classification_service import ClassificationService


@pytest.fixture()
def svc():
    return ClassificationService()


class TestTicketClassification:
    def test_classify_bug(self, svc):
        result = svc.classify_ticket(subject="Application crashes on login",
                                     description="Error 500 when clicking submit")
        assert result["category"] == "bug"
        assert result["confidence"] > 0.3

    def test_classify_billing(self, svc):
        result = svc.classify_ticket(subject="Invoice question",
                                     description="I was charged twice for my subscription")
        assert result["category"] == "billing"
        assert result["confidence"] > 0.3

    def test_classify_security(self, svc):
        result = svc.classify_ticket(subject="Security vulnerability",
                                     description="Found a CVE in our dependency")
        assert result["category"] == "security"

    def test_classify_account(self, svc):
        result = svc.classify_ticket(subject="Cannot login",
                                     description="My password is not working and I am locked out")
        assert result["category"] == "account"

    def test_classify_feature_request(self, svc):
        result = svc.classify_ticket(subject="Please add dark mode",
                                     description="Feature request: would be nice to have dark theme")
        assert result["category"] == "feature_request"

    def test_classify_performance(self, svc):
        result = svc.classify_ticket(subject="App is very slow",
                                     description="Response time is terrible, latency issues")
        assert result["category"] == "performance"

    def test_classify_question(self, svc):
        result = svc.classify_ticket(subject="How do I export data?",
                                     description="Question: how can I export my data to CSV?")
        assert result["category"] == "question"

    def test_classify_low_confidence(self, svc):
        result = svc.classify_ticket(subject="Something", description="thing")
        assert result["confidence"] < 0.6
        assert result["needs_human_review"] is True

    def test_classify_returns_all_scores(self, svc):
        result = svc.classify_ticket(subject="Bug in billing integration",
                                     description="Error when processing payment")
        assert "all_scores" in result
        assert len(result["all_scores"]) > 0

    def test_classify_from_text(self, svc):
        result = svc.classify_from_text("Critical security incident detected")
        assert result["category"] in ("security", "incident")

    def test_classify_returns_reasoning(self, svc):
        result = svc.classify_ticket(subject="API bug", description="The API returns 500 error")
        assert "reasoning" in result


class TestSentiment:
    def test_positive_sentiment(self, svc):
        result = svc.classify_ticket(subject="Thanks for the great help",
                                     description="Thank you, this was excellent support")
        assert result["sentiment"]["level"] in ("positive", "very_positive")

    def test_negative_sentiment(self, svc):
        result = svc.classify_ticket(subject="Terrible experience",
                                     description="I am angry and frustrated with this awful product")
        assert result["sentiment"]["level"] in ("negative", "very_negative")

    def test_neutral_sentiment(self, svc):
        result = svc.classify_ticket(subject="API documentation",
                                     description="Where can I find the docs?")
        assert result["sentiment"]["level"] == "neutral"

    def test_urgency_detection(self, svc):
        result = svc.classify_ticket(subject="URGENT production down",
                                     description="Emergency - production is down, losing money")
        assert result["sentiment"]["urgency_signals"] >= 1


class TestDuplicateDetection:
    def test_detect_similar_tickets(self, svc):
        existing = [
            {"id": "t1", "tenant_id": "org-1", "subject": "API timeout",
             "description": "API is timing out", "customer_id": "c1",
             "service_affected": "api", "status": "open"},
        ]
        dupes = svc.detect_duplicates("org-1", "API timeout",
                                      "API is timing out on all calls",
                                      existing_tickets=existing)
        assert len(dupes) >= 1
        assert dupes[0]["similarity"] > 0.3

    def test_no_duplicates_different_text(self, svc):
        existing = [
            {"id": "t1", "tenant_id": "org-1", "subject": "Billing question",
             "description": "About my invoice", "customer_id": "c1", "status": "open"},
        ]
        dupes = svc.detect_duplicates("org-1", "Security vulnerability found",
                                      "CVE in production dependency",
                                      existing_tickets=existing)
        assert len(dupes) == 0

    def test_customer_match_boosts_score(self, svc):
        existing = [
            {"id": "t1", "tenant_id": "org-1", "subject": "API error",
             "description": "Error on login", "customer_id": "c1", "status": "open"},
        ]
        dupes = svc.detect_duplicates("org-1", "API error",
                                      "Error on login attempt",
                                      customer_id="c1",
                                      existing_tickets=existing)
        assert len(dupes) >= 1


class TestClassificationTelemetry:
    def test_telemetry(self, svc):
        svc.classify_ticket(subject="Test1", description="test")
        svc.classify_ticket(subject="Test2", description="test")
        t = svc.get_telemetry()
        assert t["classified"] == 2
