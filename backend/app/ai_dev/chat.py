"""Code chat — grounded answers with citations — Volume 67 Commit 1."""

import logging
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai_dev.common import emit_event, resolve_repository
from app.ai_dev.context import build_context
from app.ai_dev.usage import record_usage

logger = logging.getLogger(__name__)


def _gateway_route(tenant: str, model_hint: Optional[str] = None) -> tuple[Optional[str], dict]:
    """Best-effort model routing. Returns (model_id, metadata) or (None, {})."""
    try:
        from app.aiml.gateway import route

        result = route(
            tenant=tenant,
            model_hint=model_hint or "code-assistant",
            task="code_assistance",
            context={},
        )
        model_id = result.get("model_id") or result.get("model")
        return model_id, result or {}
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("gateway route unavailable: %s", exc)
        return None, {}


async def _gateway_invoke(db, tenant, user_id: str, model_id: Optional[str], prompt: str) -> dict:
    try:
        from app.aiml.gateway import invoke

        result = await invoke(
            db,
            tenant=tenant,
            actor=user_id,
            model_id=model_id or "nova-dev",
            prompt=prompt,
            session_id=None,
        )
        if isinstance(result, dict):
            return result
        return {"text": str(result)}
    except Exception as exc:  # pragma: no cover - environment dependent
        logger.debug("gateway invoke unavailable: %s", exc)
        return {}


def _fallback_answer(context: dict) -> str:
    top = context.get("items", [])[:3]
    lines = []
    for item in top:
        cit = item.get("citation") or {}
        lines.append(f"- {item.get('text', '')[:400]} ({cit.get('file')})")
    if not lines:
        return "No repository context matched the question."
    return (
        "Model generation is unavailable; retrieval-only summary of the closest matches:\n"
        + "\n".join(lines)
    )


async def code_chat(
    db: AsyncSession,
    tenant: str,
    user_id: str,
    *,
    repository_id,
    question: str,
    model_hint: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> dict:
    repo = await resolve_repository(db, tenant, repository_id)
    context = await build_context(db, tenant, repo.id, question)
    model_id, meta = _gateway_route(tenant, model_hint)
    logger.info("chat route for %s -> %s", tenant, model_id)
    if model_id:
        prompt = f"Question: {question}\n\nContext:\n{context}"
        resp = await _gateway_invoke(db, tenant, user_id, model_id, prompt)
        answer = (
            resp.get("text")
            or resp.get("answer")
            or resp.get("content")
            or _fallback_answer(context)
        )
        uncertainty = False
        model = meta.get("model_name") or resp.get("model") or model_id
    else:
        answer = _fallback_answer(context)
        uncertainty = True
        model = None

    request_id = str(uuid.uuid4())
    if model:
        await record_usage(
            db,
            tenant,
            user_id,
            action="chat",
            model=model,
            provider=meta.get("provider"),
            prompt_tokens=context.get("tokens_used", 0),
            completion_tokens=0,
            total_tokens=context.get("tokens_used", 0),
            repository_id=repo.id,
            request_id=request_id,
        )
    await emit_event(
        "CodeChatStarted",
        {
            "request_id": request_id,
            "repository_id": str(repo.id),
            "workspace_id": workspace_id,
            "model": model,
            "uncertainty": uncertainty,
            "tokens_used": context.get("tokens_used", 0),
        },
        tenant,
    )
    return {
        "request_id": request_id,
        "answer": answer,
        "citations": [i.get("citation") for i in context.get("items", []) if i.get("citation")],
        "uncertainty": uncertainty,
        "model": model,
        "tokens_used": context.get("tokens_used", 0),
    }