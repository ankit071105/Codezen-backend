from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.room import RoomMember
from app.models.events import ComplexityLog
from app.complexity.analyzer import analyze_complexity

router = APIRouter(prefix="/complexity", tags=["complexity"])


class ComplexityRequest(BaseModel):
    room_id: str
    code: str
    language: str


@router.post("/analyze")
async def analyze(
    payload: ComplexityRequest,
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

    complexity = analyze_complexity(payload.code, payload.language)

    log = ComplexityLog(
        room_id=payload.room_id,
        user_id=current_user.id,
        language=payload.language,
        time_complexity=complexity.time_complexity,
        space_complexity=complexity.space_complexity,
        confidence=complexity.confidence,
        snapshot_at=datetime.now(timezone.utc),
    )
    db.add(log)

    return {
        "time_complexity": complexity.time_complexity,
        "space_complexity": complexity.space_complexity,
        "confidence": complexity.confidence,
        "explanation": complexity.explanation,
        "suggestions": complexity.suggestions,
    }


@router.get("/timeline/{room_id}")
async def get_timeline(
    room_id: str,
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

    result = await db.execute(
        select(ComplexityLog)
        .where(ComplexityLog.room_id == room_id)
        .order_by(ComplexityLog.snapshot_at.asc())
        .limit(100)
    )
    logs = result.scalars().all()

    return [
        {
            "user_id": log.user_id,
            "time_complexity": log.time_complexity,
            "space_complexity": log.space_complexity,
            "confidence": log.confidence,
            "snapshot_at": log.snapshot_at,
        }
        for log in logs
    ]
