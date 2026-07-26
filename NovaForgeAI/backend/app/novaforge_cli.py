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
            print("Commands: health, telemetry, status")
            return
        cmd = args[0]
        rest = args[1:] if len(args) > 1 else []
        if cmd == "health":
            self.health(rest[0] if rest else None)
        elif cmd == "telemetry":
            self.telemetry()
        elif cmd == "status":
            self.status()
        else:
            print(f"Unknown command: {cmd}")


async def main():
    cli = NovaForgeCLI()
    await cli.run_cmd(sys.argv[1:] if len(sys.argv) > 1 else [])


if __name__ == "__main__":
    asyncio.run(main())
