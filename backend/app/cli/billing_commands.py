"""Billing CLI commands — Production-Grade Billing Platform (Volume 53)."""
from __future__ import annotations
import json as json_mod


def handle_billing_command(args):
    if not args or args[0] == "help":
        _print_help()
        return
    json_out = "--json" in args
    args = [a for a in args if a != "--json"]
    dispatch = {
        "plan": _plan,
        "sub": _sub,
        "usage": _usage,
        "invoice": _invoice,
        "payment": _payment,
        "credit": _credit,
        "coupon": _coupon,
        "budget": _budget,
        "marketplace": _marketplace,
        "dunning": _dunning,
        "reconciliation": _recon,
        "telemetry": _telemetry,
    }
    h = dispatch.get(args[0])
    if h:
        h(args[1:], json_out)
    else:
        print(f"Unknown: {args[0]}")
        _print_help()


def _out(data, js, hdr=""):
    if js:
        print(json_mod.dumps(data, indent=2, default=str))
    elif hdr:
        print(f"\n{hdr}")
        if isinstance(data, list):
            for item in data:
                print(f"  - {item.get('name', item.get('id', item.get('invoice_number', item)))}")
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
    else:
        print(json_mod.dumps(data, indent=2, default=str) if js else data)


def _print_help():
    print("nova billing: plan|sub|usage|invoice|payment|credit|coupon|budget|marketplace|dunning|reconciliation|telemetry|help")


def _plan(a, js):
    from app.billing.plan_service import plan_service
    if not a:
        print("Usage: nova billing plan <list|get|create>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(plan_service.list_plans(), js, "Plans:")
    elif c == "get":
        _out(plan_service.get_plan(r[0]) or {}, js)
    elif c == "create":
        if len(r) < 3:
            print("Usage: nova billing plan create <tier> <name> <slug>")
            return
        _out(plan_service.create_plan(r[0], r[1], r[2], r[3] if len(r) > 3 else ""), js, "Created:")
    else:
        print(f"Unknown plan sub-command: {c}")


def _sub(a, js):
    from app.billing.subscription_service import subscription_service
    if not a:
        print("Usage: nova billing sub <list|get|create|cancel|reactivate|advance|analytics>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(subscription_service.list_subscriptions(r[0] if r else None), js, "Subscriptions:")
    elif c == "get":
        _out(subscription_service.get_subscription(r[0]) or {}, js)
    elif c == "create":
        if len(r) < 2:
            print("Usage: nova billing sub create <org_id> <plan_id> [billing_cycle]")
            return
        _out(subscription_service.create_subscription(r[0], r[1], r[2] if len(r) > 2 else "monthly"), js, "Created:")
    elif c == "cancel":
        _out(subscription_service.cancel_subscription(r[0], len(r) > 1 and r[1] == "true") or {}, js)
    elif c == "reactivate":
        _out(subscription_service.reactivate_subscription(r[0]) or {}, js)
    elif c == "advance":
        _out(subscription_service.advance_period(r[0]) or {}, js)
    elif c == "analytics":
        _out(subscription_service.get_subscription_analytics(r[0]) if r else {}, js)
    else:
        print(f"Unknown sub sub-command: {c}")


def _usage(a, js):
    from app.billing.meter_service import meter_service
    if not a:
        print("Usage: nova billing usage <record|summary|check>")
        return
    c, r = a[0], a[1:]
    if c == "record":
        if len(r) < 4:
            print("Usage: nova billing usage record <org_id> <metric> <quantity> <unit>")
            return
        _out(meter_service.record_usage(r[0], r[1], float(r[2]), r[3]), js, "Recorded:")
    elif c == "summary":
        _out(meter_service.get_usage_summary(r[0]) if r else {}, js)
    elif c == "check":
        if len(r) < 3:
            print("Usage: nova billing usage check <org_id> <metric> <limit>")
            return
        _out(meter_service.check_usage_limit(r[0], r[1], float(r[2])), js)
    else:
        print(f"Unknown usage sub-command: {c}")


def _invoice(a, js):
    from app.billing.invoice_service import invoice_service
    if not a:
        print("Usage: nova billing invoice <list|get|finalize|void|pay>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(invoice_service.list_invoices(r[0] if r else None), js, "Invoices:")
    elif c == "get":
        _out(invoice_service.get_invoice(r[0]) or {}, js)
    elif c == "finalize":
        _out(invoice_service.finalize_invoice(r[0]) or {}, js)
    elif c == "void":
        _out(invoice_service.void_invoice(r[0]) or {}, js)
    elif c == "pay":
        amount = int(r[1]) if len(r) > 1 else 0
        _out(invoice_service.mark_paid(r[0], amount or None) or {}, js)
    else:
        print(f"Unknown invoice sub-command: {c}")


def _payment(a, js):
    from app.billing.payment_service import payment_service
    if not a:
        print("Usage: nova billing payment <list|get|refund|summary>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(payment_service.list_payments(r[0] if r else None), js, "Payments:")
    elif c == "get":
        _out(payment_service.get_payment(r[0]) or {}, js)
    elif c == "refund":
        amount = int(r[1]) if len(r) > 1 else None
        _out(payment_service.refund_payment(r[0], amount) or {}, js)
    elif c == "summary":
        _out(payment_service.get_payment_summary(r[0]) if r else {}, js)
    else:
        print(f"Unknown payment sub-command: {c}")


def _credit(a, js):
    from app.billing.credit_service import credit_service
    if not a:
        print("Usage: nova billing credit <balance|grant|deduct|transactions>")
        return
    c, r = a[0], a[1:]
    if c == "balance":
        _out(credit_service.get_balance(r[0]) if r else {}, js)
    elif c == "grant":
        if len(r) < 2:
            print("Usage: nova billing credit grant <org_id> <amount_cents>")
            return
        _out(credit_service.grant_credits(r[0], int(r[1]), r[2] if len(r) > 2 else "granted"), js, "Granted:")
    elif c == "deduct":
        if len(r) < 2:
            print("Usage: nova billing credit deduct <org_id> <amount_cents>")
            return
        _out(credit_service.deduct_credits(r[0], int(r[1])), js, "Deducted:")
    elif c == "transactions":
        _out(credit_service.get_transactions(r[0]) if r else [], js, "Transactions:")
    else:
        print(f"Unknown credit sub-command: {c}")


def _coupon(a, js):
    from app.billing.coupon_service import coupon_service
    if not a:
        print("Usage: nova billing coupon <list|get|create|validate|deactivate>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(coupon_service.list_coupons(), js, "Coupons:")
    elif c == "get":
        _out(coupon_service.get_coupon(r[0]) or {}, js)
    elif c == "create":
        if len(r) < 3:
            print("Usage: nova billing coupon create <code> <type> <value_cents>")
            return
        _out(coupon_service.create_coupon(r[0], r[1], int(r[2])), js, "Created:")
    elif c == "validate":
        _out(coupon_service.validate_coupon(r[0]) if r else {}, js)
    elif c == "deactivate":
        _out(coupon_service.deactivate_coupon(r[0]) or {}, js)
    else:
        print(f"Unknown coupon sub-command: {c}")


def _budget(a, js):
    from app.billing.budget_service import budget_service
    if not a:
        print("Usage: nova billing budget <list|get|create|check|delete>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(budget_service.list_budgets(r[0] if r else None), js, "Budgets:")
    elif c == "get":
        _out(budget_service.get_budget(r[0]) or {}, js)
    elif c == "create":
        if len(r) < 3:
            print("Usage: nova billing budget create <org_id> <name> <limit_cents>")
            return
        _out(budget_service.create_budget(r[0], r[1], int(r[2])), js, "Created:")
    elif c == "check":
        _out(budget_service.check_budget(r[0]) if r else {}, js)
    elif c == "delete":
        _out({"deleted": budget_service.delete_budget(r[0])}, js)
    else:
        print(f"Unknown budget sub-command: {c}")


def _marketplace(a, js):
    from app.billing.marketplace_billing import marketplace_billing_service
    if not a:
        print("Usage: nova billing marketplace <summary|publisher|package>")
        return
    c, r = a[0], a[1:]
    if c == "summary":
        _out(marketplace_billing_service.get_marketplace_summary(), js)
    elif c == "publisher":
        _out(marketplace_billing_service.get_publisher_revenue(r[0]) if r else {}, js)
    elif c == "package":
        _out(marketplace_billing_service.get_package_revenue(r[0]) if r else {}, js)
    else:
        print(f"Unknown marketplace sub-command: {c}")


def _dunning(a, js):
    from app.billing.dunning_service import dunning_service
    if not a:
        print("Usage: nova billing dunning <list|check>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(dunning_service.list_dunning_records(r[0] if r else None), js, "Dunning Records:")
    elif c == "check":
        _out({"should_suspend": dunning_service.should_suspend(r[0])}, js)
    else:
        print(f"Unknown dunning sub-command: {c}")


def _recon(a, js):
    from app.billing.reconciliation_service import reconciliation_service
    if not a:
        print("Usage: nova billing reconciliation <list|summary>")
        return
    c, r = a[0], a[1:]
    if c == "list":
        _out(reconciliation_service.list_reconciliations(r[0] if r else None), js, "Reconciliations:")
    elif c == "summary":
        _out(reconciliation_service.get_reconciliation_summary(r[0]) if r else {}, js)
    else:
        print(f"Unknown reconciliation sub-command: {c}")


def _telemetry(a, js):
    from app.billing.plan_service import plan_service
    from app.billing.subscription_service import subscription_service
    from app.billing.meter_service import meter_service
    from app.billing.invoice_service import invoice_service
    from app.billing.payment_service import payment_service
    from app.billing.credit_service import credit_service
    from app.billing.coupon_service import coupon_service
    from app.billing.budget_service import budget_service
    from app.billing.marketplace_billing import marketplace_billing_service
    from app.billing.dunning_service import dunning_service
    from app.billing.reconciliation_service import reconciliation_service
    _out({
        "plans": plan_service.get_telemetry(),
        "subscriptions": subscription_service.get_telemetry(),
        "metering": meter_service.get_telemetry(),
        "invoices": invoice_service.get_telemetry(),
        "payments": payment_service.get_telemetry(),
        "credits": credit_service.get_telemetry(),
        "coupons": coupon_service.get_telemetry(),
        "budgets": budget_service.get_telemetry(),
        "marketplace": marketplace_billing_service.get_telemetry(),
        "dunning": dunning_service.get_telemetry(),
        "reconciliation": reconciliation_service.get_telemetry(),
    }, js, "Billing Telemetry:")
