"""Credit service — manage credit balances, grant, deduct, transfer, and history."""
import uuid
from datetime import datetime, timezone
from typing import Optional
from app.billing.constants import CreditType
from app.billing.config import get_billing_config


class CreditService:
    def __init__(self):
        self._balances: dict[str, dict] = {}
        self._transactions: list[dict] = []

    def get_or_create_balance(self, organization_id: str) -> dict:
        if organization_id not in self._balances:
            self._balances[organization_id] = {
                "id": str(uuid.uuid4()),
                "organization_id": organization_id,
                "balance_cents": 0,
                "total_granted_cents": 0,
                "total_used_cents": 0,
                "currency": "usd",
                "expires_at": None,
                "metadata": {},
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        return self._balances[organization_id]

    def grant_credits(
        self,
        organization_id: str,
        amount_cents: int,
        credit_type: str = "granted",
        description: str = "",
        expires_at: Optional[datetime] = None,
        invoice_id: Optional[str] = None,
    ) -> dict:
        config = get_billing_config()
        balance = self.get_or_create_balance(organization_id)
        if balance["balance_cents"] + amount_cents > config.credit_balance_cap * 100:
            raise ValueError(f"Credit balance would exceed cap of ${config.credit_balance_cap}")
        now = datetime.now(timezone.utc)
        balance["balance_cents"] += amount_cents
        balance["total_granted_cents"] += amount_cents
        balance["updated_at"] = now.isoformat()
        if expires_at:
            balance["expires_at"] = expires_at.isoformat() if isinstance(expires_at, datetime) else expires_at
        tx = {
            "id": str(uuid.uuid4()),
            "credit_balance_id": balance["id"],
            "organization_id": organization_id,
            "type": credit_type,
            "amount_cents": amount_cents,
            "balance_after_cents": balance["balance_cents"],
            "description": description,
            "invoice_id": invoice_id,
            "metadata": {},
            "created_at": now.isoformat(),
        }
        self._transactions.append(tx)
        return tx

    def deduct_credits(
        self,
        organization_id: str,
        amount_cents: int,
        invoice_id: Optional[str] = None,
        description: str = "",
    ) -> dict:
        balance = self.get_or_create_balance(organization_id)
        if balance["balance_cents"] < amount_cents:
            raise ValueError(f"Insufficient credits: have {balance['balance_cents']} cents, need {amount_cents}")
        now = datetime.now(timezone.utc)
        balance["balance_cents"] -= amount_cents
        balance["total_used_cents"] += amount_cents
        balance["updated_at"] = now.isoformat()
        tx = {
            "id": str(uuid.uuid4()),
            "credit_balance_id": balance["id"],
            "organization_id": organization_id,
            "type": "deduction",
            "amount_cents": -amount_cents,
            "balance_after_cents": balance["balance_cents"],
            "description": description,
            "invoice_id": invoice_id,
            "metadata": {},
            "created_at": now.isoformat(),
        }
        self._transactions.append(tx)
        return tx

    def transfer_credits(
        self,
        from_org_id: str,
        to_org_id: str,
        amount_cents: int,
        description: str = "",
    ) -> dict:
        now = datetime.now(timezone.utc)
        self.deduct_credits(from_org_id, amount_cents, description=f"Transfer to {to_org_id}: {description}")
        tx_to = self.grant_credits(to_org_id, amount_cents, credit_type="granted", description=f"Transfer from {from_org_id}: {description}")
        return {"from_deducted": amount_cents, "to_granted": tx_to}

    def get_balance(self, organization_id: str) -> dict:
        return self.get_or_create_balance(organization_id)

    def get_transactions(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> list[dict]:
        return [tx for tx in self._transactions if tx["organization_id"] == organization_id][-limit:]

    def check_expired_credits(self) -> list[dict]:
        now = datetime.now(timezone.utc)
        expired = []
        for org_id, balance in self._balances.items():
            if balance.get("expires_at"):
                exp = datetime.fromisoformat(balance["expires_at"])
                if now > exp and balance["balance_cents"] > 0:
                    balance["balance_cents"] = 0
                    balance["updated_at"] = now.isoformat()
                    tx = {
                        "id": str(uuid.uuid4()),
                        "credit_balance_id": balance["id"],
                        "organization_id": org_id,
                        "type": "expired",
                        "amount_cents": 0,
                        "balance_after_cents": 0,
                        "description": "Credits expired",
                        "invoice_id": None,
                        "metadata": {},
                        "created_at": now.isoformat(),
                    }
                    self._transactions.append(tx)
                    expired.append(tx)
        return expired

    def get_telemetry(self) -> dict:
        return {
            "total_organizations": len(self._balances),
            "total_balance_cents": sum(b["balance_cents"] for b in self._balances.values()),
            "total_transactions": len(self._transactions),
        }


credit_service = CreditService()
