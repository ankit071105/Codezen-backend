"""Single entry point for all agentic features — Master Orchestrator API.
Also exposes dedicated endpoints for the stateful Mock Interview flow,
Progress dashboard, adaptive topic suggestion, and post-session diagnostics."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.agents.orchestrator import route_and_handle
from app.agents.interview_agent import (
    start_interview, continue_interview, get_interview_feedback, suggest_adaptive_pick,
)
from app.agents.progress_agent import analyze_progress, get_topic_breakdown, get_diagnostic_report

router = APIRouter(prefix="/agent", tags=["agent"])


# ── Master orchestrator endpoint ────────────────────────────────────────
class AgentMessageRequest(BaseModel):
    message: str
    code: Optional[str] = None
    language: str = "python"
    room_id: Optional[str] = None
    intent: Optional[str] = None  # optional: client can force an intent (e.g. button tap)


@router.post("/message")
async def agent_message(
    payload: AgentMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await route_and_handle(
        message=payload.message,
        code=payload.code,
        language=payload.language,
        room_id=payload.room_id,
        user_id=current_user.id,
        db=db,
        forced_intent=payload.intent,
    )
    return result


# ── Mock Interview — dedicated stateful endpoints ───────────────────────
class InterviewStartRequest(BaseModel):
    topic: Optional[str] = None       # optional — company-only or behavioral/HR starts don't need it
    difficulty: str = "medium"
    company: Optional[str] = None     # company-grounded PYQ practice (technical rounds only)
    round_type: str = "technical_l1"  # technical_l1 | technical_l2 | technical_l3 | behavioral | hr


@router.post("/interview/start")
async def interview_start(
    payload: InterviewStartRequest,
    current_user: User = Depends(get_current_user),
):
    return await start_interview(
        topic=payload.topic,
        difficulty=payload.difficulty,
        user_id=current_user.id,
        company=payload.company,
        round_type=payload.round_type,
    )


@router.get("/interview/adaptive-pick")
async def interview_adaptive_pick(
    current_user: User = Depends(get_current_user),
):
    """Suggests a topic + difficulty based on the student's weakness scorecard.
    Only meaningful for technical rounds — frontend shows this hint before the
    topic-pick screen, not for behavioral/HR rounds."""
    return await suggest_adaptive_pick(current_user.id)


class InterviewContinueRequest(BaseModel):
    session_id: str
    message: str


@router.post("/interview/continue")
async def interview_continue(
    payload: InterviewContinueRequest,
    current_user: User = Depends(get_current_user),
):
    result = await continue_interview(payload.session_id, payload.message)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


class InterviewFeedbackRequest(BaseModel):
    session_id: str


@router.post("/interview/feedback")
async def interview_feedback(
    payload: InterviewFeedbackRequest,
    current_user: User = Depends(get_current_user),
):
    result = await get_interview_feedback(payload.session_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Progress — dashboard, topic breakdown, diagnostic report ───────────
@router.get("/progress")
async def progress(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await analyze_progress(db, current_user.id)


@router.get("/progress/topics")
async def progress_topics(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_topic_breakdown(db, current_user.id)


@router.get("/progress/diagnostic")
async def progress_diagnostic(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await get_diagnostic_report(db, current_user.id)