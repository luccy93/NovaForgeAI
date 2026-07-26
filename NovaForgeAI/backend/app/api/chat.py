import json
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models.conversation import Conversation
from app.models.conversation import Message, MessageRole
from app.services.rag_pipeline import RAGPipeline

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    repo_id: Optional[str] = None
    stream: bool = False


class ChatResponse(BaseModel):
    answer: str
    conversation_id: str
    confidence: float
    model_used: str
    sources: list[dict]


class ConversationSummary(BaseModel):
    id: str
    title: str
    message_count: int
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime


class ConversationDetail(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[MessageOut]


async def _resolve_conversation(
    conversation_id_str: Optional[str], message: str, db: AsyncSession
) -> uuid.UUID:
    if conversation_id_str:
        try:
            cid = uuid.UUID(conversation_id_str)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid conversation_id")
        result = await db.execute(select(Conversation).where(Conversation.id == cid))
        conv = result.scalar_one_or_none()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        return cid

    conv = Conversation(title=message[:80], session_id=str(uuid.uuid4()))
    db.add(conv)
    await db.flush()
    await db.refresh(conv)
    return conv.id


@router.post("", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def send_message(
    request: ChatRequest,
    db: AsyncSession = Depends(get_db),
) -> ChatResponse:
    conversation_id = await _resolve_conversation(request.conversation_id, request.message, db)

    user_msg = Message(role=MessageRole.user, content=request.message, conversation_id=conversation_id)
    db.add(user_msg)
    await db.flush()

    pipeline = RAGPipeline()
    result_data = await pipeline.query(question=request.message, repo_id=request.repo_id)

    assistant_msg = Message(
        role=MessageRole.assistant,
        content=result_data["answer"],
        conversation_id=conversation_id,
        tokens_used=None,
    )
    db.add(assistant_msg)
    await db.flush()

    return ChatResponse(
        answer=result_data["answer"],
        conversation_id=str(conversation_id),
        confidence=result_data.get("confidence", 0.0),
        model_used=result_data.get("model_used", ""),
        sources=result_data.get("sources", []),
    )


@router.post("/stream")
async def send_message_stream(
    request: ChatRequest,
    req: Request,
    db: AsyncSession = Depends(get_db),
):
    conversation_id = await _resolve_conversation(request.conversation_id, request.message, db)

    user_msg = Message(role=MessageRole.user, content=request.message, conversation_id=conversation_id)
    db.add(user_msg)
    await db.flush()

    from fastapi.responses import StreamingResponse

    async def event_stream() -> AsyncGenerator[str, None]:
        pipeline = RAGPipeline()
        async for chunk in pipeline.query_stream(question=request.message, repo_id=request.repo_id):
            if await req.is_disconnected():
                break
            yield f"data: {json.dumps({'type': 'chunk', 'content': chunk})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'conversation_id': str(conversation_id)} )}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"X-Conversation-ID": str(conversation_id), "Cache-Control": "no-cache"},
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def list_conversations(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> list[ConversationSummary]:
    count_sub = (
        select(Message.conversation_id, func.count().label("cnt"))
        .group_by(Message.conversation_id)
        .subquery()
    )
    stmt = (
        select(Conversation, count_sub.c.cnt)
        .outerjoin(count_sub, Conversation.id == count_sub.c.conversation_id)
        .order_by(Conversation.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        ConversationSummary(
            id=str(conv.id),
            title=conv.title,
            message_count=cnt or 0,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )
        for conv, cnt in rows
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> ConversationDetail:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation_id")

    result = await db.execute(select(Conversation).where(Conversation.id == cid))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    msg_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == cid)
        .order_by(Message.created_at)
    )
    messages = msg_result.scalars().all()

    return ConversationDetail(
        id=str(conv.id),
        title=conv.title,
        created_at=conv.created_at,
        updated_at=conv.updated_at,
        messages=[
            MessageOut(
                id=str(m.id),
                role=m.role.value,
                content=m.content,
                created_at=m.created_at,
            )
            for m in messages
        ],
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
) -> None:
    try:
        cid = uuid.UUID(conversation_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid conversation_id")

    result = await db.execute(select(Conversation).where(Conversation.id == cid))
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    await db.delete(conv)
