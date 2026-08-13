#!/usr/bin/env python3
"""NovaForge CLI — Orchestrate all 30 volumes from a single command line."""
import asyncio, json, sys, os, logging
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("novaforge")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.common.services import registry
from app.common.base import HealthRegistry

# Import service modules to register them
try:
    from app.release_engineering import service as _
except Exception as e: logger.debug("release_engineering: %s", e)
try:
    from app.rtc import service as _
except Exception as e: logger.debug("rtc: %s", e)
try:
    from app.aiops import service as _
except Exception as e: logger.debug("aiops: %s", e)
try:
    from app.security_compliance import service as _
except Exception as e: logger.debug("security_compliance: %s", e)
try:
    from app.observability import service as _
except Exception as e: logger.debug("observability: %s", e)
try:
    from app.ai_data_platform import service as _
except Exception as e: logger.debug("ai_data_platform: %s", e)
try:
    from app.enterprise_platform import service as _
except Exception as e: logger.debug("enterprise_platform: %s", e)
try:
    from app.lakehouse import service as _
except Exception as e: logger.debug("lakehouse: %s", e)
try:
    from app.multimodal import service as _
except Exception as e: logger.debug("multimodal: %s", e)
try:
    from app.automation import service as _
except Exception as e: logger.debug("automation: %s", e)


class NovaForgeCLI:
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)

    def _print(self, title: str, data: dict, color: str = ""):
        print(f"\n{'='*60}")
        print(f"  {title}")
        print(f"{'='*60}")
        print(json.dumps(data, indent=2, default=str))

    def health(self, volume: Optional[str] = None):
        all_health = registry.health_check()
        if volume:
            if volume in all_health:
                self._print(f"Health — {volume}", all_health[volume])
            else:
                print(f"Volume '{volume}' not found. Available: {', '.join(sorted(all_health.keys()))}")
        else:
            self._print("NovaForge — System Health", {
                "volumes": len(all_health),
                "status": "all_healthy" if all(v.get("status") == "healthy" for v in all_health.values()) else "degraded",
                "timestamp": self.start_time.isoformat(),
            })
            for vname, vhealth in sorted(all_health.items()):
                print(f"  {vname}: {vhealth.get('status', 'unknown')} (ops={vhealth.get('operations', 0)})")

    def telemetry(self):
        snap = registry.telemetry_snapshot()
        total = sum(sum(v.values()) for v in snap.values())
        self._print("NovaForge — Telemetry Snapshot", {"total_operations": total, "per_volume": snap})

    def status(self):
        services = registry._services
        self._print("NovaForge — Volume Status", {
            "total_volumes": len(services),
            "volumes": sorted(services.keys()),
            "uptime": (datetime.now(timezone.utc) - self.start_time).total_seconds(),
        })

    async def run_cmd(self, args: list[str]):
        if not args:
            print("Usage: novafoge <command> [args...]")
            print("Commands: health, telemetry, status, ingest, query, analytics, multimodal, automation")
            return
        cmd = args[0]
        rest = args[1:] if len(args) > 1 else []
        if cmd == "health":
            self.health(rest[0] if rest else None)
        elif cmd == "telemetry":
            self.telemetry()
        elif cmd == "status":
            self.status()
        elif cmd == "ingest":
            await self.cmd_ingest(rest)
        elif cmd == "query":
            await self.cmd_query(rest)
        elif cmd == "analytics":
            await self.cmd_analytics(rest)
        elif cmd == "multimodal":
            await self.cmd_multimodal(rest)
        elif cmd == "automation":
            await self.cmd_automation(rest)
        else:
            print(f"Unknown command: {cmd}")

    async def cmd_ingest(self, args: list[str]):
        svc = registry.get("lakehouse")
        if not svc: print("lakehouse volume not loaded"); return
        if len(args) < 2:
            print("Usage: ingest <organization_id> <event_type> [payload_json]")
            return
        org, event_type = args[0], args[1]
        payload = json.loads(args[2]) if len(args) > 2 else None
        result = await svc.ingest_event(org, event_type, payload)
        self._print("Ingest", result)

    async def cmd_query(self, args: list[str]):
        svc = registry.get("lakehouse")
        if not svc: print("lakehouse volume not loaded"); return
        if len(args) < 2:
            print("Usage: query <organization_id> <table> [group_by] [agg]")
            return
        org, table = args[0], args[1]
        group_by = args[2] if len(args) > 2 else ""
        agg = args[3] if len(args) > 3 else "count"
        result = await svc.query(org, table, group_by, agg)
        self._print("Query", result)

    async def cmd_analytics(self, args: list[str]):
        svc = registry.get("lakehouse")
        if not svc: print("lakehouse volume not loaded"); return
        if len(args) < 2:
            print("Usage: analytics <organization_id> <kind>  (kinds: ecommerce, ai, rag, agents, finops)")
            return
        handlers = {
            "ecommerce": svc.ecommerce,
            "ai": svc.ai_usage,
            "rag": svc.rag_metrics,
            "agents": svc.agent_performance,
            "finops": svc.finops_overview,
        }
        handler = handlers.get(args[1])
        if not handler:
            print(f"Unknown analytics kind: {args[1]}"); return
        self._print("Analytics", await handler(args[0]))

    async def cmd_multimodal(self, args: list[str]):
        svc = registry.get("multimodal")
        if not svc: print("multimodal volume not loaded"); return
        if not args:
            print("Usage: multimodal <sub> ...  (subs: ingest, search, answer, assets, jobs, usage, vision, screenshot, compare, ledger)")
            return
        sub = args[0]
        rest = args[1:]
        if sub == "ingest":
            if len(rest) < 2:
                print("Usage: multimodal ingest <organization_id> <file_path>")
                return
            org, path = rest[0], rest[1]
            with open(path, "rb") as fh:
                data = fh.read()
            result = await svc.ingest(org, path.split("\\")[-1].split("/")[-1], data)
            self._print("Multimodal Ingest", result)
        elif sub == "search":
            if len(rest) < 2:
                print("Usage: multimodal search <organization_id> <query> [modalities]")
                return
            self._print("Multimodal Search",
                        await svc.search(rest[0], rest[1],
                                         modalities=rest[2] if len(rest) > 2 else ""))
        elif sub == "answer":
            if len(rest) < 2:
                print("Usage: multimodal answer <organization_id> <query> [modalities]")
                return
            self._print("Multimodal Answer",
                        await svc.answer(rest[0], rest[1],
                                         modalities=rest[2] if len(rest) > 2 else ""))
        elif sub == "assets":
            if not rest:
                print("Usage: multimodal assets <organization_id>")
                return
            self._print("Multimodal Assets", await svc.list_assets(rest[0]))
        elif sub == "jobs":
            if not rest:
                print("Usage: multimodal jobs <organization_id>")
                return
            self._print("Multimodal Jobs", await svc.list_jobs(rest[0]))
        elif sub == "usage":
            if not rest:
                print("Usage: multimodal usage <organization_id>")
                return
            self._print("Multimodal Usage", await svc.usage(rest[0]))
        elif sub == "vision":
            if len(rest) < 3:
                print("Usage: multimodal vision <organization_id> <image_path> <prompt>")
                return
            org, img, prompt = rest[0], rest[1], " ".join(rest[2:])
            with open(img, "rb") as fh:
                data = fh.read()
            self._print("Vision",
                        await svc.vision(org, prompt, data))
        elif sub == "screenshot":
            if len(rest) < 2:
                print("Usage: multimodal screenshot <organization_id> <url> [viewport WxH]")
                return
            self._print("Screenshot",
                        await svc.capture_screenshot(
                            rest[0], rest[1],
                            viewport=rest[2] if len(rest) > 2 else ""))
        elif sub == "compare":
            if len(rest) < 3:
                print("Usage: multimodal compare <organization_id> <baseline_id> <candidate_id>")
                return
            self._print("Visual Compare",
                        await svc.compare_screenshots(rest[0], rest[1], rest[2]))
        elif sub == "ledger":
            self._print("Cost Ledger",
                        await svc.ledger(rest[0] if rest else "", 100))
        else:
            print(f"Unknown multimodal sub-command: {sub}")

    async def cmd_automation(self, args: list[str]):
        svc = registry.get("automation")
        if not svc: print("automation volume not loaded"); return
        if not args:
            print("Usage: automation <sub> ...")
            print("  subs: define, list, dryrun, publish, run, execs, approve, tick, templates, ai")
            return
        sub = args[0]
        rest = args[1:]
        gw = svc.gateway
        if sub == "define":
            if len(rest) < 2:
                print("Usage: automation define <organization_id> <definition.json>")
                return
            with open(rest[1], "r", encoding="utf-8") as fh:
                definition = json.load(fh)
            result = gw.define(definition, organization_id=rest[0])
            self._print("Workflow Defined", {"workflow_id": result.workflow_id,
                                             "status": result.status,
                                             "version": result.version})
        elif sub == "list":
            self._print("Workflows", gw.list_workflows(rest[0] if rest else ""))
        elif sub == "dryrun":
            if len(rest) < 2:
                print("Usage: automation dryrun <organization_id> <workflow_id>")
                return
            self._print("Dry Run", gw.dry_run(rest[1], rest[0]))
        elif sub == "publish":
            if len(rest) < 2:
                print("Usage: automation publish <organization_id> <workflow_id>")
                return
            self._print("Publish", gw.publish(rest[1], rest[0]))
        elif sub == "run":
            if len(rest) < 2:
                print("Usage: automation run <organization_id> <workflow_id> [inputs_json]")
                return
            inputs = json.loads(rest[2]) if len(rest) > 2 else None
            self._print("Execution",
                        gw.run(rest[1], rest[0], inputs=inputs))
        elif sub == "execs":
            self._print("Executions", gw.executions(rest[0] if rest else ""))
        elif sub == "approve":
            if len(rest) < 4:
                print("Usage: automation approve <organization_id> <workflow_id> <step_id> <approve|reject> [actor]")
                return
            decision = "approved" if rest[3] == "approve" else "rejected"
            req = gw.engine.approvals.decide(
                rest[1], rest[2], decision,
                actor=rest[4] if len(rest) > 4 else "cli_operator",
                organization_id=rest[0])
            self._print("Approval", req.to_dict() if req else {"error": "not found"})
        elif sub == "tick":
            self._print("Schedule Tick", gw.tick())
        elif sub == "templates":
            self._print("Templates", {
                "count": len(gw.templates.list()),
                "templates": gw.templates.list()})
        elif sub == "ai":
            if len(rest) < 1:
                print("Usage: automation ai <prompt...>")
                return
            self._print("AI Workflow", gw.run_ai_generated(" ".join(rest), ""))
        else:
            print(f"Unknown automation sub-command: {sub}")


async def main():
    cli = NovaForgeCLI()
    await cli.run_cmd(sys.argv[1:] if len(sys.argv) > 1 else [])


if __name__ == "__main__":
    asyncio.run(main())
