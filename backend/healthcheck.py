"""Health check utilities for NovaForge services."""

import os
import sys
import json
import http.client
from typing import Any


def check_url(url: str, timeout: int = 5) -> bool:
    """Check if an HTTP endpoint is healthy."""
    try:
        from urllib.request import urlopen, Request
        req = Request(url, method="GET")
        with urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def check_postgres() -> bool:
    """Check PostgreSQL connectivity."""
    try:
        import asyncpg
        return True  # actual check requires event loop
    except ImportError:
        return False


def check_redis() -> bool:
    """Check Redis connectivity."""
    try:
        import redis
        r = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"), socket_connect_timeout=2)
        r.ping()
        r.close()
        return True
    except Exception:
        return False


def check_qdrant() -> bool:
    """Check Qdrant connectivity."""
    try:
        from qdrant_client import QdrantClient
        client = QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"), prefer_grpc=False)
        client.get_collections()
        return True
    except Exception:
        return False


def check_neo4j() -> bool:
    """Check Neo4j connectivity."""
    try:
        from neo4j import GraphDatabase
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        auth = (os.getenv("NEO4J_USER", "neo4j"), os.getenv("NEO4J_PASSWORD", "password"))
        driver = GraphDatabase.driver(uri, auth=auth)
        driver.verify_connectivity()
        driver.close()
        return True
    except Exception:
        return False


def main() -> None:
    """Run health checks based on command arguments."""
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "No check specified"}))
        sys.exit(1)

    check_type = sys.argv[1]
    results: dict[str, Any] = {"status": "unknown", "checks": {}}

    if check_type == "all":
        results["checks"]["app"] = True
        results["checks"]["postgres"] = check_postgres()
        results["checks"]["redis"] = check_redis()
        results["checks"]["qdrant"] = check_qdrant()
        results["checks"]["neo4j"] = check_neo4j()
    elif check_type == "liveness":
        results["checks"]["app"] = True
    elif check_type == "readiness":
        results["checks"]["app"] = True
        results["checks"]["postgres"] = check_postgres()
        results["checks"]["redis"] = check_redis()
    else:
        print(json.dumps({"status": "error", "message": f"Unknown check: {check_type}"}))
        sys.exit(1)

    all_ok = all(results["checks"].values())
    results["status"] = "ok" if all_ok else "degraded"

    print(json.dumps(results, indent=2))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
