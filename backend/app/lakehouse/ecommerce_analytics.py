"""E-commerce Analytics - revenue, orders, AOV, repeat rate, LTV, products, funnel."""
import statistics


class EcommerceAnalytics:
    """Tenant-scoped e-commerce analytics over in-memory orders and events."""

    def __init__(self, store: dict = None, tenant_id: str = ""):
        self.tenant_id = tenant_id
        self.store = store or {"orders": [], "customer_events": []}
        self._funnel_cache: dict = {}

    def record_order(self, order: dict) -> None:
        if self.tenant_id and order.get("organization_id") != self.tenant_id:
            raise PermissionError("cross-tenant order rejected")
        self.store["orders"].append(order)

    def record_customer_event(self, event: dict) -> None:
        if self.tenant_id and event.get("organization_id") != self.tenant_id:
            raise PermissionError("cross-tenant event rejected")
        self.store["customer_events"].append(event)

    def revenue_by_period(self, period: str = "day") -> dict:
        out = {}
        for order in self.store["orders"]:
            created = str(order.get("created_at", ""))
            key = created[:10] if period == "day" else (created[:7] if created else "unknown")
            out[key] = out.get(key, 0.0) + float(order.get("total_amount", 0.0))
        return dict(sorted(out.items()))

    def revenue_totals(self) -> dict:
        orders = self.store["orders"]
        revenue = sum(float(o.get("total_amount", o.get("amount", 0.0))) for o in orders)
        return {"orders": len(orders),
                "revenue": round(revenue, 2),
                "aov": round(revenue / max(1, len(orders)), 2)}

    def recurring_orders(self) -> dict:
        by_customer = {}
        for o in self.store["orders"]:
            by_customer.setdefault(o.get("customer_id"), []).append(o)
        repeat = sum(1 for rows in by_customer.values() if len(rows) > 1)
        return {"customers": len(by_customer),
                "repeat_purchasers": repeat,
                "repeat_purchase_rate": round(repeat / max(1, len(by_customer)), 4)}

    def customer_ltv(self) -> dict:
        by_customer = {}
        for o in self.store["orders"]:
            by_customer.setdefault(o.get("customer_id"), []).append(
                float(o.get("total_amount", o.get("amount", 0.0))))
        ltvs = [sum(v) for v in by_customer.values()]
        return {"customer_count": len(ltvs),
                "average_ltv": round(statistics.mean(ltvs), 2) if ltvs else 0.0,
                "median_ltv": round(statistics.median(ltvs), 2) if ltvs else 0.0}

    def product_performance(self) -> dict:
        perf = {}
        for o in self.store["orders"]:
            for item in o.get("items", []):
                pid = item.get("product_id")
                if not pid:
                    continue
                entry = perf.setdefault(pid, {"quantity": 0, "revenue": 0.0, "orders": 0})
                entry["quantity"] += int(item.get("quantity", 0))
                entry["revenue"] += float(item.get("price", 0.0)) * int(item.get("quantity", 0))
                entry["orders"] += 1
        return perf

    def top_products(self, limit: int = 10) -> list[dict]:
        ranked = sorted(self.product_performance().items(),
                        key=lambda kv: kv[1]["revenue"], reverse=True)
        return [{"product_id": pid, **stats} for pid, stats in ranked[:limit]]

    def funnel(self, steps=("viewed_product", "added_to_cart", "checkout", "purchase")) -> dict:
        hits = {step: set() for step in steps}
        for ev in self.store["customer_events"]:
            step = ev.get("event")
            user = ev.get("user_id")
            if step in hits and user:
                hits[step].add(user)
        result = {}
        previous = None
        for step in steps:
            count = len(hits[step])
            result[step] = {
                "unique_users": count,
                "conversion_from_previous": round(count / previous, 4) if previous else None,
            }
            previous = count
        self._funnel_cache = result
        return result

    def retention_cohorts(self) -> dict:
        return {"cohorts": [], "note": "cohorts require event timestamps"}