"""Cross-domain bridges — Volume 70 Commit 2.

Thin, policy-checked adapters into V69 FinOps, V68 Knowledge, Workflow
Automation and AI action governance. Each bridge reuses the domain's
authoritative service; no duplicated accounting, indexing, or engines.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.common import (
    NotFoundError,
    ValidationError,
    _as_uuid,
    _utcnow,
    idempotency_key,
    sanitize_metadata,
)


async def record_integration_usage(
    db: AsyncSession, tenant: str, connection_id, operation: str, *,
    requests: int = 1, bytes_out: int = 0, estimated_cents: int = 0,
    provider: str = "", actor: str = "",
) -> dict:
    """Attribute integration usage into V69 FinOps (no duplicate ledger)."""
    from app.finops.costing import record_usage_cost
    from app.integrations.governed_models import IntegrationConnection

    from sqlalchemy import select
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == _as_uuid(connection_id),
        IntegrationConnection.tenant == tenant,
    )
    connection = (await db.execute(stmt)).scalar_one_or_none()
    if connection is None:
        raise NotFoundError("connection not found")
    usage = {
        "provider": provider or "integration",
        "model": "",
        "input_tokens": 0, "output_tokens": 0, "requests": max(int(requests or 0), 0),
        "occurred_at": _utcnow().isoformat(),
        "source_type": "integration",
        "source_id": f"{connection.id}:{operation or 'call'}",
        "estimated": True,
        "dimensions": {"workspace": connection.workspace or "", "service": "integrations",
                       "operation": operation or "", "resource": str(connection.id)},
        "metadata": {"bytes_out": bytes_out, "estimated_cents": estimated_cents},
    }
    # Optional FinOps gate for expensive operations (best-effort, fail-open).
    gate = {"decision": "ALLOW"}
    if estimated_cents and estimated_cents > 0:
        try:
            from app.finops.governance import evaluate_operation as _finops_gate
            gate = await _finops_gate(db, tenant, actor or "integration", operation or "integration.call",
                                      estimated_cents=estimated_cents)
            if gate.get("decision") == "BLOCK":
                raise ValidationError(f"blocked by FinOps policy: {gate.get('reason', '')}")
        except ValidationError:
            raise
        except Exception:
            gate = {"decision": "ALLOW"}
    record = await record_usage_cost(db, tenant, usage, actor=actor)
    return {"finops_record": record, "finops_gate": gate.get("decision", "ALLOW")}


async def link_knowledge_source(
    db: AsyncSession, tenant: str, integration_id, *,
    source_type: str = "external", name: str = "", actor: str = "",
) -> dict:
    """Register an approved integration as a V68 Knowledge source (no
    duplicate indexing — the Knowledge pipeline owns ingestion)."""
    from app.integrations.governed_models import Integration
    from app.integrations.registry import get_integration
    from sqlalchemy import select

    integration = await get_integration(db, tenant, integration_id)
    if integration["status"] != "ACTIVE":
        raise ValidationError("integration is not ACTIVE")
    from app.knowledge.models import KnowledgeSource
    candidates = (await db.execute(select(KnowledgeSource).where(
        KnowledgeSource.tenant == tenant,
    ).limit(500))).scalars().all()
    for candidate in candidates:
        config = candidate.connector_config or {}
        if isinstance(config, dict) and config.get("integration_id") == integration["id"]:
            return {"source_id": str(candidate.id), "deduplicated": True}
    import uuid as _uuid
    source = KnowledgeSource(
        id=_uuid.uuid4(), tenant=tenant, name=name or integration["name"],
        source_type=source_type, connector_config={"integration_id": integration["id"]},
        status="PENDING", classification="INTERNAL",
    )
    db.add(source)
    await db.flush()
    try:
        from app.integrations.common import emit_event
        await emit_event("knowledge_source_linked",
                         {"integration_id": integration["id"], "source_id": str(source.id)}, tenant)
    except Exception:
        pass
    return {"source_id": str(source.id), "status": source.status}


async def invoke_from_workflow(
    db: AsyncSession, tenant: str, connection_id, operation: str, *,
    method: str = "GET", path: str = "", run_id: str = "",
    requester: str = "", actor: str = "",
) -> dict:
    """Workflow-authorized invocation: policy check, execution, audit."""
    from app.integrations.policies import evaluate_transfer
    from app.integrations.workers import execute_operation

    decision = await evaluate_transfer(db, tenant, operation=f"workflow.{operation}",
                                       fields=["operation", "run_id"], actor=actor)
    if decision["decision"] == "BLOCK":
        raise ValidationError(f"blocked by integration policy: {decision['reasons']}")
    result = await execute_operation(db, tenant, connection_id, operation,
                                     method=method, path=path,
                                     idempotency_key=idempotency_key(
                                         tenant, str(connection_id), run_id or operation),
                                     actor=actor or requester)
    try:
        from app.integrations.common import emit_event
        await emit_event("workflow_integration_invoked",
                         {"connection_id": str(connection_id), "operation": operation,
                          "run_id": run_id}, tenant)
    except Exception:
        pass
    return {"execution": result, "policy_decision": decision["decision"]}


async def ai_request_action(
    db: AsyncSession, tenant: str, actor: str, *,
    operation: str = "", target_url: str = "", method: str = "GET",
    model: str = "", provider: str = "",
) -> dict:
    """Governed AI action: the target must belong to a registered ACTIVE
    connection — AI-generated URLs never execute directly."""
    from sqlalchemy import select
    from app.integrations.governed_models import IntegrationConnection
    from app.integrations.network_policy import scrub, validate_url
    from urllib.parse import urlparse

    if target_url:
        validate_url(target_url)
        host = (urlparse(target_url).hostname or "").lower()
    else:
        host = ""
    connections = (await db.execute(select(IntegrationConnection).where(
        IntegrationConnection.tenant == tenant,
        IntegrationConnection.status == "ACTIVE",
    ))).scalars().all()
    matched = None
    for connection in connections:
        ref_host = ""
        try:
            ref_host = (urlparse(connection.endpoint_ref or "").hostname or "").lower()
        except Exception:
            ref_host = ""
        if host and ref_host and (host == ref_host or host.endswith("." + ref_host)):
            matched = connection
            break
    if matched is None:
        try:
            from app.integrations.common import emit_event
            await emit_event("ai_action_rejected",
                             {"reason": "unregistered target", "target": scrub(target_url or "")}, tenant)
        except Exception:
            pass
        raise ValidationError("AI actions must use a registered integration connection")
    from app.finops.governance import evaluate_operation as _finops_gate
    try:
        gate = await _finops_gate(db, tenant, actor, operation or "ai.action",
                                  estimated_cents=0,
                                  usage={"requests": 1}, model=model, provider=provider)
        if gate.get("decision") == "BLOCK":
            raise ValidationError(f"blocked by FinOps policy: {gate.get('reason', '')}")
    except ValidationError:
        raise
    except Exception:
        pass
    from app.integrations.workers import execute_operation
    path = urlparse(target_url).path if target_url else ""
    result = await execute_operation(db, tenant, matched.id, operation or "ai.action",
                                     method=method, path=path.lstrip("/"), actor=actor)
    return {"execution": result, "connection_id": str(matched.id)}
