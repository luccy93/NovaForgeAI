"""Meter service tests (Volume 53)."""
import pytest
from datetime import datetime, timedelta, timezone
from app.billing.meter_service import MeterService
from app.billing.constants import MeteringUnit


@pytest.fixture()
def svc():
    return MeterService()


@pytest.fixture()
def org_id():
    return "org-test-meter-001"


class TestMeterService:
    def test_record_usage(self, svc, org_id):
        record = svc.record_usage(org_id, "tokens", 1000, "tokens")
        assert record["organization_id"] == org_id
        assert record["metric_name"] == "tokens"
        assert record["quantity"] == 1000
        assert record["cost_cents"] > 0

    def test_record_usage_api_calls(self, svc, org_id):
        record = svc.record_usage(org_id, "api_calls", 500, "api_calls")
        assert record["unit"] == "api_calls"
        assert record["cost_cents"] == 5

    def test_record_usage_compute_seconds(self, svc, org_id):
        record = svc.record_usage(org_id, "compute", 100, "compute_seconds")
        assert record["cost_cents"] == 10

    def test_record_usage_storage(self, svc, org_id):
        record = svc.record_usage(org_id, "storage", 10, "storage_gb_hours")
        assert record["cost_cents"] == 10

    def test_record_usage_unknown_unit(self, svc, org_id):
        record = svc.record_usage(org_id, "custom", 100, "unknown_unit")
        assert record["cost_cents"] == 0

    def test_record_usage_with_metadata(self, svc, org_id):
        record = svc.record_usage(org_id, "tokens", 100, "tokens", metadata={"model": "gpt-4"})
        assert record["metadata"]["model"] == "gpt-4"

    def test_record_usage_with_resource(self, svc, org_id):
        record = svc.record_usage(org_id, "api_calls", 10, "api_calls", resource_id="repo-1", resource_type="repository")
        assert record["resource_id"] == "repo-1"
        assert record["resource_type"] == "repository"

    def test_get_usage(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        svc.record_usage(org_id, "api_calls", 50, "api_calls")
        usage = svc.get_usage(org_id)
        assert len(usage) == 2

    def test_get_usage_by_metric(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        svc.record_usage(org_id, "tokens", 500, "tokens")
        usage = svc.get_usage(org_id, metric_name="tokens")
        assert len(usage) == 2
        assert all(r["metric_name"] == "tokens" for r in usage)

    def test_get_usage_empty(self, svc, org_id):
        usage = svc.get_usage(org_id)
        assert len(usage) == 0

    def test_get_usage_summary(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        svc.record_usage(org_id, "tokens", 500, "tokens")
        summary = svc.get_usage_summary(org_id, metric_name="tokens")
        assert summary["total_quantity"] == 1500
        assert summary["record_count"] == 2
        assert summary["total_cost_cents"] > 0

    def test_get_usage_summary_empty(self, svc, org_id):
        summary = svc.get_usage_summary(org_id)
        assert summary["total_quantity"] == 0
        assert summary["record_count"] == 0

    def test_get_usage_summary_by_metric(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        svc.record_usage(org_id, "api_calls", 50, "api_calls")
        summary = svc.get_usage_summary(org_id)
        assert "tokens" in summary["by_metric"]
        assert "api_calls" in summary["by_metric"]

    def test_get_aggregated_usage(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        agg = svc.get_aggregated_usage(org_id, metric_name="tokens")
        assert len(agg) >= 1
        assert agg[0]["total_quantity"] == 1000

    def test_get_usage_by_resource(self, svc, org_id):
        svc.record_usage(org_id, "api_calls", 10, "api_calls", resource_id="repo-1", resource_type="repository")
        svc.record_usage(org_id, "api_calls", 20, "api_calls", resource_id="repo-2", resource_type="repository")
        results = svc.get_usage_by_resource(org_id, "repository")
        assert len(results) == 2

    def test_check_usage_limit_ok(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 1000, "tokens")
        result = svc.check_usage_limit(org_id, "tokens", 10000)
        assert result["exceeded"] is False
        assert result["percentage_used"] == 10.0

    def test_check_usage_limit_exceeded(self, svc, org_id):
        svc.record_usage(org_id, "tokens", 10000, "tokens")
        result = svc.check_usage_limit(org_id, "tokens", 10000)
        assert result["exceeded"] is True

    def test_check_usage_limit_zero(self, svc, org_id):
        result = svc.check_usage_limit(org_id, "nonexistent", 100)
        assert result["exceeded"] is False
        assert result["percentage_used"] == 0.0

    def test_telemetry(self, svc):
        tel = svc.get_telemetry()
        assert "total_records" in tel
        assert "aggregated_keys" in tel
        assert "unique_organizations" in tel

    def test_multiple_orgs(self, svc):
        svc.record_usage("org-1", "tokens", 100, "tokens")
        svc.record_usage("org-2", "tokens", 200, "tokens")
        assert len(svc.get_usage("org-1")) == 1
        assert len(svc.get_usage("org-2")) == 1
        assert svc.get_telemetry()["unique_organizations"] == 2
