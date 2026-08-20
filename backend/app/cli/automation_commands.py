"""CLI commands for the Autonomous Software-Engineering layer (Volume 45).

Usage:
    python -m app.novaforge_cli automate create --tenant t1 --repo r1 --request "fix bug"
    python -m app.novaforge_cli automate list --tenant t1
    python -m app.novaforge_cli automate run <task_id>
    python -m app.novaforge_cli automate plan <task_id>
    python -m app.novaforge_cli automate approve <approval_id> --decision approved --by admin
    python -m app.novaforge_cli automate deploy <task_id> --env staging
    python -m app.novaforge_cli automate rollback <deployment_id>
    python -m app.novaforge_cli automate status <task_id>
    python -m app.novaforge_cli automate budget <tenant>
"""

import argparse
import asyncio
import json
import logging
import sys

logger = logging.getLogger(__name__)

BASE_URL = "http://localhost:8000"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="automate", description="NovaForge Autonomous Engineering")
    sub = parser.add_subparsers(dest="command")

    p_create = sub.add_parser("create", help="Create a new engineering task")
    p_create.add_argument("--tenant", required=True)
    p_create.add_argument("--project", default="default")
    p_create.add_argument("--repo", required=True)
    p_create.add_argument("--branch", default="main")
    p_create.add_argument("--request", required=True)
    p_create.add_argument("--actor", default="cli-user")
    p_create.add_argument("--type", default="feature", choices=["bug", "feature", "refactor", "security", "performance", "documentation", "testing", "dependency", "architecture", "incident_remediation"])
    p_create.add_argument("--autonomy", type=int, default=2, choices=range(6))

    p_list = sub.add_parser("list", help="List tasks")
    p_list.add_argument("--tenant")
    p_list.add_argument("--status")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument("--offset", type=int, default=0)
    p_list.add_argument("--json", dest="as_json", action="store_true")

    sub.add_parser("run", help="Execute the core loop for a task").add_argument("task_id")
    sub.add_parser("cancel", help="Cancel a task").add_argument("task_id")
    sub.add_parser("status", help="Get task status").add_argument("task_id")

    p_plan = sub.add_parser("plan", help="Create/view plan for a task")
    p_plan.add_argument("task_id")
    p_plan.add_argument("--objective")
    p_plan.add_argument("--approve", action="store_true")

    p_approve = sub.add_parser("approve", help="Decide on an approval request")
    p_approve.add_argument("approval_id")
    p_approve.add_argument("--decision", required=True, choices=["approved", "rejected"])
    p_approve.add_argument("--by", required=True)
    p_approve.add_argument("--reason", default="")

    p_deploy = sub.add_parser("deploy", help="Deploy a task's patch")
    p_deploy.add_argument("task_id")
    p_deploy.add_argument("--env", default="staging")
    p_deploy.add_argument("--by", default="cli-user")

    p_rollback = sub.add_parser("rollback", help="Rollback a deployment")
    p_rollback.add_argument("deployment_id")

    p_budget = sub.add_parser("budget", help="View budget for a tenant")
    p_budget.add_argument("tenant")

    p_scan = sub.add_parser("scan", help="Security scan a diff")
    p_scan.add_argument("--diff-file")

    sub.add_parser("templates", help="List workflow templates")

    return parser


async def _dispatch(args):
    import httpx

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=60) as client:

        if args.command == "create":
            r = await client.post("/api/v1/automation/tasks", json={
                "tenant": args.tenant, "project": args.project, "repository": args.repo,
                "branch": args.branch, "request": args.request, "actor": args.actor,
                "task_type": args.type, "autonomy_level": args.autonomy,
            })
            print(json.dumps(r.json(), indent=2))

        elif args.command == "list":
            params = {"limit": args.limit, "offset": args.offset}
            if args.tenant:
                params["tenant"] = args.tenant
            if args.status:
                params["status"] = args.status
            r = await client.get("/api/v1/automation/tasks", params=params)
            data = r.json()
            if getattr(args, "as_json", False):
                print(json.dumps(data, indent=2))
            else:
                for t in data.get("tasks", []):
                    print(f"  {t['id'][:8]}  {t['status']:20s}  {t['task_type']:15s}  {t['request'][:60]}")
                print(f"\nTotal: {data.get('total', 0)}")

        elif args.command == "run":
            r = await client.post(f"/api/v1/automation/tasks/{args.task_id}/run")
            print(json.dumps(r.json(), indent=2))

        elif args.command == "cancel":
            r = await client.post(f"/api/v1/automation/tasks/{args.task_id}/cancel")
            print(json.dumps(r.json(), indent=2))

        elif args.command == "status":
            r = await client.get(f"/api/v1/automation/tasks/{args.task_id}")
            t = r.json()
            print(f"Task:   {t['id']}")
            print(f"Status: {t['status']}")
            print(f"Type:   {t['task_type']}")
            print(f"Risk:   {t['risk_level']}")
            print(f"Actor:  {t['actor']}")
            if t.get("error"):
                print(f"Error:  {t['error']}")

        elif args.command == "plan":
            if args.objective:
                r = await client.post(f"/api/v1/automation/tasks/{args.task_id}/plans", json={
                    "objective": args.objective,
                })
                plan = r.json()
                print(f"Created plan: {plan['id']}")
                if args.approve:
                    r2 = await client.post(f"/api/v1/automation/plans/{plan['id']}/approve")
                    print(f"Plan approved: {r2.json()['status']}")
            else:
                r = await client.get(f"/api/v1/automation/tasks/{args.task_id}/plans/latest")
                plan = r.json()
                print(json.dumps(plan, indent=2))

        elif args.command == "approve":
            r = await client.post(f"/api/v1/automation/approvals/{args.approval_id}/decide", json={
                "decision": args.decision, "decided_by": args.by, "reason": args.reason,
            })
            print(json.dumps(r.json(), indent=2))

        elif args.command == "deploy":
            r = await client.post(f"/api/v1/automation/tasks/{args.task_id}/deploy", json={
                "environment": args.env, "deployed_by": args.by,
            })
            print(json.dumps(r.json(), indent=2))

        elif args.command == "rollback":
            r = await client.post(f"/api/v1/automation/deployments/{args.deployment_id}/rollback")
            print(json.dumps(r.json(), indent=2))

        elif args.command == "budget":
            r = await client.get(f"/api/v1/automation/budgets/{args.tenant}/summary")
            data = r.json()
            print(f"Tenant: {data['tenant']}")
            for k in ("tokens", "tool_calls", "cost_usd", "runtime_s"):
                v = data[k]
                print(f"  {k:12s}: {v['used']:>10} / {v['limit']:<10} ({v['pct']}%)")
            print(f"  {'active_tasks':>12s}: {data['active_tasks']}")

        elif args.command == "scan":
            diff = ""
            if args.diff_file:
                with open(args.diff_file) as f:
                    diff = f.read()
            r = await client.post("/api/v1/automation/security/scan", json={"diff": diff})
            result = r.json()
            status = "CLEAN" if result["clean"] else "FINDINGS"
            print(f"Security scan: {status}")
            for f in result.get("findings", []):
                print(f"  [{f['severity']}] {f['type']}: {f['message']}")

        elif args.command == "templates":
            r = await client.get("/api/v1/automation/templates")
            for t in r.json():
                print(f"  {t['name']:30s}  type={t['task_type']:15s}  autonomy=L{t['autonomy_level']}")


async def automation_cli_main(args_list: list[str] | None = None):
    parser = _build_parser()
    ns = parser.parse_args(args_list or sys.argv[1:])
    if not ns.command:
        parser.print_help()
        return
    await _dispatch(ns)


if __name__ == "__main__":
    asyncio.run(automation_cli_main())
