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
try:
    from app.evaluation import service as _
except Exception as e: logger.debug("evaluation: %s", e)
try:
    from app.quality import service as _
except Exception as e: logger.debug("quality: %s", e)
try:
    from app.knowledge_graph import entity_service as _
except Exception as e: logger.debug("knowledge_graph: %s", e)
try:
    from app.iam import organization_service as _
except Exception as e: logger.debug("iam: %s", e)
try:
    from app.billing import plan_service as _
except Exception as e: logger.debug("billing: %s", e)


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
            print("Commands: health, telemetry, status, ingest, query, analytics, multimodal, automation, marketplace, automate")
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
        elif cmd == "evaluation":
            await self.cmd_evaluation(rest)
        elif cmd == "marketplace":
            from app.cli.marketplace_commands import marketplace_cli_main

            marketplace_cli_main(rest)
        elif cmd == "automate":
            from app.cli.automation_commands import automation_cli_main
            await automation_cli_main(rest)
        elif cmd == "delivery":
            await self.cmd_delivery(rest)
        elif cmd in ("release", "flag", "flags"):
            from app.cli.release_commands import handle_release_command
            handle_release_command([cmd] + rest)
        elif cmd == "governance":
            from app.cli.datagov_commands import handle_datagov_command
            handle_datagov_command(rest)
        elif cmd == "ai":
            from app.cli.aiml_commands import handle_aiml_command
            handle_aiml_command(rest)
        elif cmd == "observe":
            from app.cli.observability_commands import handle_observability_command
            handle_observability_command(rest)
        elif cmd == "aiops":
            from app.cli.observability_commands import handle_aiops_command
            handle_aiops_command(rest)
        elif cmd == "resilience":
            from app.cli.resilience_commands import handle_resilience_command
            handle_resilience_command(rest)
        elif cmd == "perf":
            from app.cli.performance_commands import handle_performance_command
            handle_performance_command(rest)
        elif cmd == "region":
            from app.cli.regions_commands import handle_region_command
            handle_region_command(rest)
        elif cmd in ("secops", "security"):
            # Volume 63 SecOps takes precedence for its subcommands
            secops_subs = {"events", "alerts", "findings", "cases", "investigate", "indicators", "risk", "respond", "playbook", "hunt", "attack-path", "blast-radius", "posture", "coverage"}
            sub = rest[0] if rest else ""
            if sub in secops_subs or cmd == "secops":
                from app.cli.secops_commands import handle_secops_command
                handle_secops_command(rest if sub in secops_subs else [sub] + rest[1:] if sub else rest)
            else:
                from app.cli.security_commands import handle_security_command
                subcmd = rest[0] if rest else "findings"
                handle_security_command(subcmd, rest[1:])
        elif cmd == "quality":
            from app.cli.quality_commands import handle_quality_command
            handle_quality_command(rest)
        elif cmd == "incident":
            from app.cli.incident_commands import handle_incident_command
            handle_incident_command(rest)
        elif cmd == "analytics":
            from app.cli.analytics_commands import handle_analytics_command
            handle_analytics_command(rest)
        elif cmd == "knowledge_graph":
            from app.cli.knowledge_graph_commands import handle_knowledge_graph_command
            handle_knowledge_graph_command(rest)
        elif cmd == "iam":
            # Zero Trust subcommands take precedence for Volume 64
            zt_subs = {"authorize", "sessions", "credentials", "access-request", "privileged", "reviews", "risk", "posture", "access-graph", "simulate", "blast-radius", "anomalies", "campaigns"}
            sub = rest[0] if rest else ""
            # map aliases to handle dashes
            if sub in zt_subs:
                from app.cli.zero_trust_commands import handle_zero_trust_command
                handle_zero_trust_command(rest)
            else:
                from app.cli.iam_commands import handle_iam_command
                handle_iam_command(rest)
        elif cmd == "data":
            from app.cli.data_platform_commands import handle_data_platform_command
            handle_data_platform_command(rest)
        elif cmd == "workflow":
            from app.cli.workflow_commands import handle_workflow_command
            handle_workflow_command(rest)
        elif cmd == "ai-dev":
            from app.cli.ai_dev_commands import handle_ai_dev_command
            handle_ai_dev_command(rest)
        elif cmd == "knowledge":
            from app.knowledge.cli import handle_knowledge_command
            handle_knowledge_command(rest)
        elif cmd == "billing":
            from app.cli.billing_commands import handle_billing_command
            handle_billing_command(rest)
        elif cmd == "finops":
            from app.cli.finops_commands import handle_finops_command
            handle_finops_command(rest)
        elif cmd == "support":
            from app.cli.support_commands import handle_support_command
            handle_support_command(rest)
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

    async def cmd_evaluation(self, args: list[str]):
        svc = registry.get("evaluation")
        if not svc: print("evaluation volume not loaded"); return
        if not args:
            print("Usage: evaluation <sub> ...")
            print("  subs: health, datasets, dataset, version, publish, clone, diff, lineage,")
            print("        run, runs, gate, pair, judge, kappa, rag, code, review")
            return
        sub = args[0]
        rest = args[1:]
        gw = svc.gateway
        if sub == "health":
            self._print("Evaluation Health", gw.health())
        elif sub == "datasets":
            self._print("Datasets", {"count": len(gw.list_datasets(rest[0] if rest else "")),
                                     "datasets": gw.list_datasets(rest[0] if rest else "")})
        elif sub == "dataset":
            if len(rest) < 2:
                print("Usage: evaluation dataset <name> <task_type> [org_id]")
                return
            self._print("Dataset Created", gw.create_dataset(
                rest[0], rest[1], organization_id=rest[2] if len(rest) > 2 else ""))
        elif sub == "version":
            if len(rest) < 2:
                print("Usage: evaluation version <dataset_id> <examples.json>")
                return
            with open(rest[1], "r", encoding="utf-8") as fh:
                data = json.load(fh)
            self._print("Version Added", gw.add_version(
                rest[0], data.get("examples", data)))
        elif sub == "publish":
            if len(rest) < 2:
                print("Usage: evaluation publish <dataset_id> <version>")
                return
            self._print("Published", gw.publish_version(rest[0], int(rest[1])))
        elif sub == "clone":
            if len(rest) < 2:
                print("Usage: evaluation clone <dataset_id> <new_name>")
                return
            self._print("Cloned", gw.clone_dataset(rest[0], rest[1]))
        elif sub == "diff":
            if len(rest) < 3:
                print("Usage: evaluation diff <dataset_id> <version_a> <version_b>")
                return
            self._print("Diff", gw.diff_versions(rest[0], int(rest[1]), int(rest[2])))
        elif sub == "lineage":
            if len(rest) < 1:
                print("Usage: evaluation lineage <dataset_id>")
                return
            self._print("Lineage", gw.dataset_lineage(rest[0]))
        elif sub == "run":
            if len(rest) < 2:
                print("Usage: evaluation run <dataset_id> <model> [org_id]")
                return
            self._print("Benchmark Run", gw.run_benchmark(
                rest[0], model=rest[1],
                organization_id=rest[2] if len(rest) > 2 else ""))
        elif sub == "runs":
            self._print("Runs", {"count": len(gw.list_runs(rest[0] if rest else "")),
                                 "runs": gw.list_runs(rest[0] if rest else "", 10)})
        elif sub == "pair":
            if len(rest) < 2:
                print("Usage: evaluation pair <label_a> <label_b> [examples.json]")
                return
            examples = []
            if len(rest) > 2:
                with open(rest[2], "r", encoding="utf-8") as fh:
                    examples = json.load(fh).get("examples", [])
            self._print("Pairwise", gw.compare_pairwise(rest[0], rest[1], examples))
        elif sub == "judge":
            if len(rest) < 2:
                print("Usage: evaluation judge <prompt> <output> [reference]")
                return
            ref = rest[2] if len(rest) > 2 else ""
            self._print("Judge", gw.judge(rest[0], rest[1], ref))
        elif sub == "gate":
            if len(rest) < 2:
                print("Usage: evaluation gate <baseline_run_id> <candidate_run_id>")
                return
            self._print("Quality Gate", gw.gate(rest[0], rest[1]))
        elif sub == "rag":
            if len(rest) < 2:
                print("Usage: evaluation rag <relevant.json> <retrieved.json> [k]")
                return
            with open(rest[0], "r", encoding="utf-8") as fh:
                relevant = json.load(fh)
            with open(rest[1], "r", encoding="utf-8") as fh:
                retrieved = json.load(fh)
            k = int(rest[2]) if len(rest) > 2 else 5
            self._print("RAG Metrics", gw.rag_metrics(relevant, retrieved, k))
        elif sub == "code":
            if len(rest) < 2:
                print("Usage: evaluation code <expected_code> <actual_code>")
                return
            with open(rest[0], "r", encoding="utf-8") as fh:
                expected = fh.read()
            with open(rest[1], "r", encoding="utf-8") as fh:
                actual = fh.read()
            self._print("Code Eval", gw.code_generation(expected, actual))
        elif sub == "review":
            if len(rest) < 1:
                print("Usage: evaluation review <run_id>")
                return
            self._print("Review Report", gw.review_report(rest[0]))
        else:
            print(f"Unknown evaluation sub-command: {sub}")


    async def cmd_delivery(self, args: list[str]):
        from app.core.database import async_session
        from app.delivery.pipeline_service import PipelineService
        from app.delivery.runner_service import RunnerService
        from app.delivery.artifact_service import ArtifactService
        from app.delivery.environment_service import EnvironmentService
        from app.delivery.deployment_service import DeploymentService
        from app.delivery.release_service import ReleaseService
        from app.delivery.preview_service import PreviewService
        from app.delivery.approval_service import ApprovalService

        if not args:
            print("Usage: delivery <sub> ...")
            print("  subs: pipeline-create, pipeline-list, run, runners, artifacts,")
            print("        env-create, env-list, deploy, deploy-complete, release,")
            print("        preview, approvals")
            return

        sub = args[0]
        rest = args[1:]
        async with async_session() as db:
            if sub == "pipeline-create":
                if len(rest) < 4:
                    print("Usage: delivery pipeline-create <tenant> <project> <repo> <name> [branch]")
                    return
                svc = PipelineService(db)
                pipe = await svc.create(tenant=rest[0], project=rest[1], repository=rest[2],
                                        name=rest[3], branch=rest[4] if len(rest) > 4 else "main")
                await db.commit()
                self._print("Pipeline Created", {"id": str(pipe.id), "name": pipe.name, "repo": pipe.repository})
            elif sub == "pipeline-list":
                svc = PipelineService(db)
                rows, total = await svc.list_pipelines(tenant=rest[0] if rest else None)
                self._print("Pipelines", {"count": len(rows), "total": total,
                                          "pipelines": [{"id": str(p.id), "name": p.name, "repo": p.repository} for p in rows]})
            elif sub == "run":
                if len(rest) < 1:
                    print("Usage: delivery run <pipeline_id> [commit_sha]")
                    return
                svc = PipelineService(db)
                run = await svc.trigger_run(UUID(rest[0]), commit_sha=rest[1] if len(rest) > 1 else "")
                await db.commit()
                self._print("Run Triggered", {"id": str(run.id), "status": run.status})
            elif sub == "runners":
                svc = RunnerService(db)
                rows, total = await svc.list_runners()
                self._print("Runners", {"count": len(rows), "total": total,
                                        "runners": [{"id": str(r.id), "name": r.name, "status": r.status} for r in rows]})
            elif sub == "artifacts":
                svc = ArtifactService(db)
                rows, total = await svc.list_artifacts()
                self._print("Artifacts", {"count": len(rows), "total": total,
                                          "artifacts": [{"id": str(a.id), "name": a.name, "version": a.version} for a in rows]})
            elif sub == "env-create":
                if len(rest) < 3:
                    print("Usage: delivery env-create <tenant> <name> <type> [region]")
                    return
                svc = EnvironmentService(db)
                env = await svc.create(tenant=rest[0], name=rest[1], env_type=rest[2],
                                       region=rest[3] if len(rest) > 3 else "default")
                await db.commit()
                self._print("Environment Created", {"id": str(env.id), "name": env.name, "type": env.env_type})
            elif sub == "env-list":
                svc = EnvironmentService(db)
                rows = await svc.list_environments(tenant=rest[0] if rest else None)
                self._print("Environments", {"count": len(rows),
                                             "environments": [{"id": str(e.id), "name": e.name, "type": e.env_type} for e in rows]})
            elif sub == "deploy":
                if len(rest) < 1:
                    print("Usage: delivery deploy <environment_id> [version]")
                    return
                svc = DeploymentService(db)
                dep = await svc.create(tenant="cli", environment_id=UUID(rest[0]),
                                       version=rest[1] if len(rest) > 1 else "0.0.1")
                await db.commit()
                self._print("Deployment Created", {"id": str(dep.id), "status": dep.status})
            elif sub == "deploy-complete":
                if len(rest) < 1:
                    print("Usage: delivery deploy-complete <deployment_id>")
                    return
                svc = DeploymentService(db)
                dep = await svc.complete(UUID(rest[0]))
                await db.commit()
                self._print("Deployment Completed", {"id": str(dep.id), "status": dep.status})
            elif sub == "release":
                if len(rest) < 4:
                    print("Usage: delivery release <tenant> <project> <repo> <version>")
                    return
                svc = ReleaseService(db)
                rel = await svc.create(tenant=rest[0], project=rest[1], repository=rest[2], version=rest[3])
                await db.commit()
                self._print("Release Created", {"id": str(rel.id), "version": rel.version, "status": rel.status})
            elif sub == "preview":
                if len(rest) < 3:
                    print("Usage: delivery preview <tenant> <name> <repo> <branch>")
                    return
                svc = PreviewService(db)
                prev = await svc.create(tenant=rest[0], name=rest[1], repository=rest[2],
                                        branch=rest[3] if len(rest) > 3 else "main")
                await db.commit()
                self._print("Preview Created", {"id": str(prev.id), "url": prev.url, "status": prev.status})
            elif sub == "approvals":
                svc = ApprovalService(db)
                rows = await svc.list_approvals()
                self._print("Approvals", {"count": len(rows),
                                          "approvals": [{"id": str(a.id), "decision": a.decision, "requested_by": a.requested_by} for a in rows]})
            else:
                print(f"Unknown delivery sub-command: {sub}")


async def main():
    cli = NovaForgeCLI()
    await cli.run_cmd(sys.argv[1:] if len(sys.argv) > 1 else [])


if __name__ == "__main__":
    asyncio.run(main())
