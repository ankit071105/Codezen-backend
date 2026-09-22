"""Saved Items API — generic save/list/get/delete for interview sessions,
canvas designs, tutor chats, code reviews, and editor code snippets. One
table, one API, polymorphic via item_type."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.saved_item import SavedItem

router = APIRouter(prefix="/saved", tags=["saved-items"])

ALLOWED_TYPES = {"interview", "canvas", "tutor_chat", "code_review", "editor_code"}


class SaveItemRequest(BaseModel):
    item_type: str
    title: str
    payload: dict[str, Any]


class SavedItemResponse(BaseModel):
    id: str
    item_type: str
    title: str
    payload: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("", response_model=SavedItemResponse)
async def save_item(
    payload: SaveItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.item_type not in ALLOWED_TYPES:
        raise HTTPException(status_code=400, detail=f"item_type must be one of {ALLOWED_TYPES}")

    item = SavedItem(
        user_id=current_user.id,
        item_type=payload.item_type,
        title=payload.title[:200],
        payload=payload.payload,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return item


@router.get("", response_model=list[SavedItemResponse])
async def list_saved_items(
    item_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(SavedItem).where(SavedItem.user_id == current_user.id)
    if item_type:
        query = query.where(SavedItem.item_type == item_type)
    query = query.order_by(SavedItem.updated_at.desc())

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/{item_id}", response_model=SavedItemResponse)
async def get_saved_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedItem).where(SavedItem.id == item_id, SavedItem.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")
    return item


class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    payload: Optional[dict[str, Any]] = None


@router.patch("/{item_id}", response_model=SavedItemResponse)
async def update_saved_item(
    item_id: str,
    payload: UpdateItemRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(SavedItem).where(SavedItem.id == item_id, SavedItem.user_id == current_user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Not found")

    if payload.title is not None:
        item.title = payload.title[:200]
    if payload.payload is not None:
        item.payload = payload.payload

    await db.commit()
    await db.refresh(item)
    return item


@router.delete("/{item_id}")
async def delete_saved_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        delete(SavedItem).where(SavedItem.id == item_id, SavedItem.user_id == current_user.id)
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}