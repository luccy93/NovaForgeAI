#!/usr/bin/env python3
"""NovaForge — Main entry point. Starts the FastAPI server or CLI."""
import sys, os, logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("novaforge")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.api import app as app  # noqa: E402, F401 — ASGI app for `uvicorn app.main:app`

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("health", "telemetry", "status"):
        from app.novaforge_cli import main
        import asyncio
        asyncio.run(main())
    else:
        try:
            import uvicorn
            uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
        except ImportError:
            print("No 'uvicorn' available. Running CLI mode. Use: python -m app.main health")
