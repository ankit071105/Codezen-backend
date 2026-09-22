from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.room import RoomMember
from app.models.submission import Submission
from app.runner.sandbox import run_code, LANGUAGE_CONFIGS

router = APIRouter(prefix="/runner", tags=["runner"])


class RunRequest(BaseModel):
    room_id: str
    language: str
    code: str


@router.post("/run")
async def execute_code(
    payload: RunRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.language.lower() not in LANGUAGE_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Language '{payload.language}' not supported")

    result = await db.execute(
        select(RoomMember).where(
            and_(
                RoomMember.room_id == payload.room_id,
                RoomMember.user_id == current_user.id,
                RoomMember.is_revoked == False,
            )
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if member.role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot run code")

    run_result = await run_code(payload.language, payload.code)

    submission = Submission(
        room_id=payload.room_id,
        user_id=current_user.id,
        language=payload.language,
        code=payload.code,
        stdout=run_result.stdout,
        stderr=run_result.stderr,
        exit_code=run_result.exit_code,
        runtime_ms=run_result.runtime_ms,
        memory_kb=run_result.memory_kb,
        timed_out=run_result.timed_out,
        created_at=datetime.now(timezone.utc),
    )
    db.add(submission)

    current_user.xp += 5
    await db.flush()

    return {
        "submission_id": submission.id,
        "stdout": run_result.stdout,
        "stderr": run_result.stderr,
        "exit_code": run_result.exit_code,
        "runtime_ms": run_result.runtime_ms,
        "timed_out": run_result.timed_out,
        "xp_earned": 5,
    }


@router.get("/submissions/{room_id}")
async def get_submissions(
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

    result = await db.execute(
        select(Submission)
        .where(and_(Submission.room_id == room_id, Submission.user_id == current_user.id))
        .order_by(Submission.created_at.desc())
        .limit(limit)
    )
    subs = result.scalars().all()
    return [
        {
            "id": s.id,
            "language": s.language,
            "exit_code": s.exit_code,
            "runtime_ms": s.runtime_ms,
            "timed_out": s.timed_out,
            "created_at": s.created_at,
        }
        for s in subs
    ]


class DebugRequest(BaseModel):
    room_id: str
    language: str
    code: str


@router.post("/debug")
async def debug_code(
    payload: DebugRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import and_
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

    if payload.language.lower() != "python":
        raise HTTPException(status_code=400, detail="Debugger currently supports Python only")

    from app.runner.debugger import debug_python
    debug_result = await debug_python(payload.code)
    return debug_result