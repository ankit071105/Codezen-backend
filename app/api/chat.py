from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional
import json

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.redis import redis_save_chat, redis_get_chat_history
from app.models.user import User
from app.models.room import RoomMember
from app.agents.graph import run_agent

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    room_id: str
    query: str
    code: Optional[str] = None
    language: Optional[str] = None


@router.post("/")
async def chat(
    payload: ChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RoomMember).where(
            and_(
                RoomMember.room_id == payload.room_id,
                RoomMember.user_id == current_user.id,
                RoomMember.is_revoked == False,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this room")

    await redis_save_chat(payload.room_id, current_user.id, "user", payload.query)

    agent_result = await run_agent(
        query=payload.query,
        code=payload.code,
        language=payload.language,
        room_id=payload.room_id,
        user_id=current_user.id,
    )

    await redis_save_chat(payload.room_id, "system", "assistant", agent_result["response"])

    return {
        "allowed": agent_result["allowed"],
        "intent": agent_result["intent"],
        "response": agent_result["response"],
        "cache_hit": agent_result["cache_hit"],
        "sources": agent_result["sources"],
    }


@router.get("/history/{room_id}")
async def get_history(
    room_id: str,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RoomMember).where(
            and_(
                RoomMember.room_id == room_id,
                RoomMember.user_id == current_user.id,
                RoomMember.is_revoked == False,
            )
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=403, detail="Not a member of this room")

    history = await redis_get_chat_history(room_id, limit)
    return {"messages": history}
