"""Reconciliation service — match invoices against payments, detect discrepancies."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import ReconciliationStatus


class ReconciliationService:
    def __init__(self):
        self._records: dict[str, dict] = {}
        self._invoice_recon: dict[str, list[str]] = {}
        self._org_recon: dict[str, list[str]] = {}

    def create_reconciliation(
        self,
        invoice_id: str,
        organization_id: str,
        expected_amount_cents: int,
        actual_amount_cents: Optional[int] = None,
    ) -> dict:
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        discrepancy = 0
        status = ReconciliationStatus.UNMATCHED.value
        if actual_amount_cents is not None:
            discrepancy = abs(expected_amount_cents - actual_amount_cents)
            status = ReconciliationStatus.MATCHED.value if discrepancy == 0 else ReconciliationStatus.DISCREPANCY.value
        record = {
            "id": record_id,
            "invoice_id": invoice_id,
            "organization_id": organization_id,
            "status": status,
            "expected_amount_cents": expected_amount_cents,
            "actual_amount_cents": actual_amount_cents,
            "discrepancy_cents": discrepancy,
            "resolved_at": None,
            "resolved_by": None,
            "resolution_notes": None,
            "metadata": {},
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        self._records[record_id] = record
        self._invoice_recon.setdefault(invoice_id, []).append(record_id)
        self._org_recon.setdefault(organization_id, []).append(record_id)
        return record

    def get_reconciliation(self, record_id: str) -> Optional[dict]:
        return self._records.get(record_id)

    def list_reconciliations(
        self,
        organization_id: Optional[str] = None,
        invoice_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict]:
        if invoice_id:
            ids = self._invoice_recon.get(invoice_id, [])
            results = [self._records[rid] for rid in ids if rid in self._records]
        elif organization_id:
            ids = self._org_recon.get(organization_id, [])
            results = [self._records[rid] for rid in ids if rid in self._records]
        else:
            results = list(self._records.values())
        if status:
            results = [r for r in results if r["status"] == status]
        return results[-limit:]

    def resolve_reconciliation(
        self,
        record_id: str,
        resolution_notes: str = "",
        resolved_by: str = "",
    ) -> Optional[dict]:
        record = self._records.get(record_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record["status"] = ReconciliationStatus.RESOLVED.value
        record["resolved_at"] = now.isoformat()
        record["resolved_by"] = resolved_by
        record["resolution_notes"] = resolution_notes
        record["updated_at"] = now.isoformat()
        return record

    def update_actual_amount(self, record_id: str, actual_amount_cents: int) -> Optional[dict]:
        record = self._records.get(record_id)
        if not record:
            return None
        now = datetime.now(timezone.utc)
        record["actual_amount_cents"] = actual_amount_cents
        discrepancy = abs(record["expected_amount_cents"] - actual_amount_cents)
        record["discrepancy_cents"] = discrepancy
        record["status"] = ReconciliationStatus.MATCHED.value if discrepancy == 0 else ReconciliationStatus.DISCREPANCY.value
        record["updated_at"] = now.isoformat()
        return record

    def get_reconciliation_summary(self, organization_id: str) -> dict:
        records = self.list_reconciliations(organization_id=organization_id)
        matched = sum(1 for r in records if r["status"] == ReconciliationStatus.MATCHED.value)
        unmatched = sum(1 for r in records if r["status"] == ReconciliationStatus.UNMATCHED.value)
        discrepancy = sum(1 for r in records if r["status"] == ReconciliationStatus.DISCREPANCY.value)
        resolved = sum(1 for r in records if r["status"] == ReconciliationStatus.RESOLVED.value)
        total_discrepancy_cents = sum(r["discrepancy_cents"] for r in records)
        return {
            "organization_id": organization_id,
            "total_records": len(records),
            "matched": matched,
            "unmatched": unmatched,
            "discrepancy": discrepancy,
            "resolved": resolved,
            "total_discrepancy_cents": total_discrepancy_cents,
        }

    def get_telemetry(self) -> dict:
        statuses = {}
        for r in self._records.values():
            statuses[r["status"]] = statuses.get(r["status"], 0) + 1
        return {
            "total_records": len(self._records),
            "by_status": statuses,
        }


reconciliation_service = ReconciliationService()
