"""Organization Analytics Service - chargers, seats, growth, ranges and segments."""
import statistics
from typing import Optional


class OrgAnalytics:
    """Measures user growth, engagement, churn and seat utilization per organization."""

    def __init__(self):
        self.users: list[dict] = []        # {"id", "organization_id", "created_at", "last_active_at"}
        self.signups: list[dict] = []     # {"organization_id", "at", "plan"}
        self.invoices: list[dict] = []    # {"organization_id", "amount_usd", "paid_at", "plan"}

    def add_user(self, user: dict) -> None:
        self.users.append(user)

    def record_signup(self, org: str, at: str, plan: str = "free") -> None:
        self.signups.append({"organization_id": org, "at": at, "plan": plan})

    def growth(self, org: Optional[str] = None) -> dict:
        signups = [s for s in self.signups if not org or s["organization_id"] == org]
        months = {}
        for s in signups:
            key = s["at"][:7]
            months[key] = months.get(key, 0) + 1
        if len(months) < 2:
            return {"note": "need 2+ months of signups"}
        keys = sorted(months)
        total = sum(months.values())
        first, last = months[keys[0]], months[keys[-1]]
        growth_rate = (last - first) / max(1.0, first)
        return {"total_signups": total, "months": months,
                "monthly_growth_rate": round(growth_rate, 4),
                "first_month": keys[0], "last_month": keys[-1]}

    def user_activity_ratio(self, org: Optional[str] = None) -> dict:
        users = [u for u in self.users if not org or u["organization_id"] == org]
        active = sum(1 for u in users if u.get("last_active_at"))
        return {"users": len(users), "active_users": active,
                "activity_ratio": round(active / max(1, len(users)), 4)}

    def seat_utilization(self, plans: dict, seats_by_org: dict) -> dict:
        out = {}
        for org, seats in seats_by_org.items():
            users = sum(1 for u in self.users if u.get("organization_id") == org)
            out[org] = {"seats": seats, "users": users,
                        "utilization": round(users / max(1, seats), 4)}
        return out

    def organization_segments(self) -> dict:
        by_org = {}
        for s in self.signups:
            by_org[s["organization_id"]] = s.get("plan", "free")
        segments = {}
        for org, plan in by_org.items():
            segments.setdefault(plan, []).append(org)
        return {plan: {"organizations": len(orgs), "orgs": orgs[:50]}
                for plan, orgs in segments.items()}

    def revenue_recognized(self, org: Optional[str] = None) -> float:
        invs = [i for i in self.invoices if not org or i["organization_id"] == org]
        return round(sum(float(i.get("amount_usd", 0.0)) for i in invs), 2)


class OrgInsights:
    """Cross-organization aggregates for the platform operator."""

    def __init__(self, org_analytics: Optional[OrgAnalytics] = None):
        self.analytics = org_analytics or OrgAnalytics()

    def platform_overview(self) -> dict:
        signups = self.analytics.signups
        invoices = self.analytics.invoices
        users = self.analytics.users
        return {
            "organizations": len({s["organization_id"] for s in signups}),
            "total_signups": len(signups),
            "total_users": len({u["id"] for u in users}),
            "total_revenue_usd": round(sum(float(i["amount_usd"]) for i in invoices), 2),
            "avg_revenue_per_org": round(
                sum(float(i["amount_usd"]) for i in invoices) / max(1, len(signups)), 2),
        }