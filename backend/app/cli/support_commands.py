"""Support CLI commands — Customer Support & Service Management (Volume 54)."""

from __future__ import annotations

import json as json_mod


def handle_support_command(args):
    if not args or args[0] == "help":
        _print_help(); return
    json_out = "--json" in args
    args = [a for a in args if a != "--json"]
    dispatch = {
        "ticket": _ticket, "tickets": _tickets, "create": _create,
        "reply": _reply, "assign": _assign, "escalate": _escalate,
        "knowledge": _knowledge, "status": _status, "search": _search,
        "analytics": _analytics, "feedback": _feedback, "sla": _sla,
    }
    h = dispatch.get(args[0])
    if h:
        h(args[1:], json_out)
    else:
        print(f"Unknown support command: {args[0]}")
        _print_help()


def _out(data, js, hdr=""):
    if js:
        print(json_mod.dumps(data, indent=2, default=str))
    else:
        if hdr:
            print(f"\n{hdr}")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    print(f"  - {item.get('id', item.get('subject', item.get('title', 'item')))}")
                else:
                    print(f"  - {item}")
        elif isinstance(data, dict):
            for k, v in data.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {data}")


def _print_help():
    print("""Usage: nova support <command> [subcommand] [--json]

Commands:
  ticket list [--status X] [--priority X] [--json]
  ticket get <id> [--json]
  tickets [--status X] [--json]
  create <subject> <description> [--category X] [--priority X] [--json]
  reply <ticket_id> <message> [--internal] [--json]
  assign <ticket_id> <agent_id> [--json]
  escalate <ticket_id> [--reason X] [--to-level X] [--json]
  knowledge search <query> [--json]
  knowledge create <title> <content> [--category X] [--json]
  status [--json]
  search <query> [--json]
  analytics [--json]
  feedback <ticket_id> <rating> [--comment X] [--json]
  sla summary [--json]""")


def _ticket(a, js):
    if not a:
        print("Usage: nova support ticket <list|get>"); return
    sub = a[0]
    if sub == "list":
        from app.support.ticket_service import ticket_service
        _out(ticket_service.list_tickets(tenant_id="default"), js, "Tickets:")
    elif sub == "get":
        if len(a) < 2:
            print("Usage: nova support ticket get <id>"); return
        from app.support.ticket_service import ticket_service
        t = ticket_service.get_ticket(a[1])
        _out(t or {"error": "not found"}, js)
    else:
        print(f"Unknown ticket sub-command: {sub}")


def _tickets(a, js):
    from app.support.ticket_service import ticket_service
    _out(ticket_service.list_tickets(tenant_id="default"), js, "Tickets:")


def _create(a, js):
    if len(a) < 2:
        print("Usage: nova support create <subject> <description>"); return
    from app.support.ticket_service import ticket_service
    ticket = ticket_service.create_ticket(
        tenant_id="default", customer_id="cli-user", subject=a[0], description=a[1],
    )
    _out(ticket, js, "Created:")


def _reply(a, js):
    if len(a) < 2:
        print("Usage: nova support reply <ticket_id> <message>"); return
    from app.support.message_service import message_service
    msg = message_service.create_message(
        ticket_id=a[0], sender_id="cli-agent", message_text=a[1], sender_type="agent",
    )
    _out(msg, js, "Reply sent:")


def _assign(a, js):
    if len(a) < 2:
        print("Usage: nova support assign <ticket_id> <agent_id>"); return
    from app.support.ticket_service import ticket_service
    ticket = ticket_service.assign_ticket(a[0], a[1], assigned_by="cli")
    _out(ticket or {"error": "not found"}, js)


def _escalate(a, js):
    if not a:
        print("Usage: nova support escalate <ticket_id>"); return
    from app.support.escalation_service import escalation_service
    esc = escalation_service.create_escalation(
        a[0], escalation_type="customer_requested", to_level="tier2",
        reason=a[1] if len(a) > 1 else "CLI escalation",
    )
    _out(esc, js, "Escalated:")


def _knowledge(a, js):
    if not a:
        print("Usage: nova support knowledge <search|create>"); return
    sub = a[0]
    if sub == "search":
        if len(a) < 2:
            print("Usage: nova support knowledge search <query>"); return
        from app.support.knowledge_service import knowledge_service
        results = knowledge_service.search_articles(a[1], tenant_id="default")
        _out(results, js, "Results:")
    elif sub == "create":
        if len(a) < 2:
            print("Usage: nova support knowledge create <title> [content]"); return
        from app.support.knowledge_service import knowledge_service
        article = knowledge_service.create_article(
            tenant_id="default", title=a[1], content=a[2] if len(a) > 2 else "",
        )
        _out(article, js, "Created:")
    else:
        print(f"Unknown knowledge sub-command: {sub}")


def _status(a, js):
    _out({"services": [
        {"name": "API", "status": "operational"},
        {"name": "AI Engine", "status": "operational"},
    ], "overall_status": "operational"}, js, "Service Status:")


def _search(a, js):
    if not a:
        print("Usage: nova support search <query>"); return
    from app.support.ticket_service import ticket_service
    results = ticket_service.search_tickets(a[0], tenant_id="default")
    _out(results, js, "Results:")


def _analytics(a, js):
    from app.support.ticket_service import ticket_service
    from app.support.message_service import message_service
    from app.support.classification_service import classification_service
    from app.support.sla_service import sla_service
    from app.support.knowledge_service import knowledge_service
    from app.support.escalation_service import escalation_service
    data = {
        "tickets": ticket_service.get_telemetry(),
        "messages": message_service.get_telemetry(),
        "classification": classification_service.get_telemetry(),
        "sla": sla_service.get_telemetry(),
        "knowledge": knowledge_service.get_telemetry(),
        "escalations": escalation_service.get_telemetry(),
    }
    _out(data, js, "Analytics:")


def _feedback(a, js):
    if len(a) < 2:
        print("Usage: nova support feedback <ticket_id> <rating>"); return
    _out({"ticket_id": a[0], "rating": int(a[1]),
           "comment": a[2] if len(a) > 2 else None,
           "status": "submitted"}, js, "Feedback:")


def _sla(a, js):
    if not a or a[0] == "summary":
        from app.support.sla_service import sla_service
        _out(sla_service.get_sla_summary("default"), js, "SLA Summary:")
    else:
        print(f"Unknown sla sub-command: {a[0]}")
