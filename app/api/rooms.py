from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.security import create_invite_token, decode_invite_token
from app.models.user import User
from app.models.room import Room, RoomMember
from app.models.events import AuditLog

router = APIRouter(prefix="/rooms", tags=["rooms"])


class CreateRoomRequest(BaseModel):
    name: str
    language: str = "python"
    description: Optional[str] = None


class InviteRequest(BaseModel):
    role: str = "editor"
    expires_hours: int = 24
    single_use: bool = False


class JoinRoomRequest(BaseModel):
    invite_token: str


class UpdateRoomRequest(BaseModel):
    name: Optional[str] = None
    is_locked: Optional[bool] = None
    language: Optional[str] = None


def room_to_dict(room: Room, member_role: str = None) -> dict:
    return {
        "id": room.id,
        "name": room.name,
        "owner_id": room.owner_id,
        "language": room.language,
        "is_locked": room.is_locked,
        "description": room.description,
        "code_snapshot": room.code_snapshot,
        "created_at": room.created_at,
        "your_role": member_role,
    }


async def get_member_role(db: AsyncSession, room_id: str, user_id: str) -> Optional[str]:
    result = await db.execute(
        select(RoomMember).where(
            and_(
                RoomMember.room_id == room_id,
                RoomMember.user_id == user_id,
                RoomMember.is_revoked == False,
            )
        )
    )
    member = result.scalar_one_or_none()
    return member.role if member else None


async def log_audit(db: AsyncSession, room_id: str, user_id: str, event_type: str, meta: dict):
    log = AuditLog(
        room_id=room_id,
        user_id=user_id,
        event_type=event_type,
        meta_json=meta,
        created_at=datetime.now(timezone.utc),
    )
    db.add(log)


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: CreateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    room = Room(
        name=payload.name,
        owner_id=current_user.id,
        language=payload.language,
        description=payload.description,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(room)
    await db.flush()

    member = RoomMember(
        room_id=room.id,
        user_id=current_user.id,
        role="owner",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    await log_audit(db, room.id, current_user.id, "room_created", {"name": room.name})
    return room_to_dict(room, "owner")


@router.get("/")
async def list_my_rooms(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(RoomMember, Room)
        .join(Room, RoomMember.room_id == Room.id)
        .where(
            and_(
                RoomMember.user_id == current_user.id,
                RoomMember.is_revoked == False,
            )
        )
    )
    rows = result.all()
    return [room_to_dict(room, member.role) for member, room in rows]


@router.get("/{room_id}")
async def get_room(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    return room_to_dict(room, role)


@router.patch("/{room_id}")
async def update_room(
    room_id: str,
    payload: UpdateRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if role not in ("owner", "instructor"):
        raise HTTPException(status_code=403, detail="Only owner or instructor can update room")

    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    if payload.name is not None:
        room.name = payload.name
    if payload.is_locked is not None:
        room.is_locked = payload.is_locked
    if payload.language is not None:
        room.language = payload.language
    room.updated_at = datetime.now(timezone.utc)

    await log_audit(db, room_id, current_user.id, "room_updated", payload.model_dump(exclude_none=True))
    return room_to_dict(room, role)


@router.post("/{room_id}/invite")
async def create_invite(
    room_id: str,
    payload: InviteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if role not in ("owner", "instructor"):
        raise HTTPException(status_code=403, detail="Only owner or instructor can invite")

    if payload.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot invite someone as owner")

    token = create_invite_token(
        room_id=room_id,
        role=payload.role,
        expires_hours=payload.expires_hours,
        single_use=payload.single_use,
    )

    await log_audit(db, room_id, current_user.id, "invite_created", {"role": payload.role})

    return {
        "invite_token": token,
        "invite_url": f"http://localhost:8000/rooms/join?token={token}",
        "role": payload.role,
        "expires_hours": payload.expires_hours,
    }


@router.post("/join")
async def join_room(
    payload: JoinRoomRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token_data = decode_invite_token(payload.invite_token)
    if not token_data:
        raise HTTPException(status_code=400, detail="Invalid or expired invite token")

    room_id = token_data["room_id"]
    role = token_data["role"]

    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    existing = await get_member_role(db, room_id, current_user.id)
    if existing:
        raise HTTPException(status_code=400, detail="Already a member of this room")

    member = RoomMember(
        room_id=room_id,
        user_id=current_user.id,
        role=role,
        invite_token=payload.invite_token,
        joined_at=datetime.now(timezone.utc),
    )
    db.add(member)

    await log_audit(db, room_id, current_user.id, "member_joined", {"role": role})
    return room_to_dict(room, role)


@router.delete("/{room_id}/members/{user_id}")
async def revoke_member(
    room_id: str,
    user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    requester_role = await get_member_role(db, room_id, current_user.id)
    if requester_role not in ("owner", "instructor"):
        raise HTTPException(status_code=403, detail="Only owner or instructor can revoke access")

    result = await db.execute(
        select(RoomMember).where(
            and_(RoomMember.room_id == room_id, RoomMember.user_id == user_id)
        )
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if member.role == "owner":
        raise HTTPException(status_code=400, detail="Cannot revoke the owner")

    member.is_revoked = True
    await log_audit(db, room_id, current_user.id, "member_revoked", {"target_user_id": user_id})
    return {"message": "Access revoked"}


@router.get("/{room_id}/members")
async def list_members(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this room")

    result = await db.execute(
        select(RoomMember, User)
        .join(User, RoomMember.user_id == User.id)
        .where(and_(RoomMember.room_id == room_id, RoomMember.is_revoked == False))
    )
    rows = result.all()
    return [
        {
            "user_id": user.id,
            "name": user.name,
            "email": user.email,
            "role": member.role,
            "joined_at": member.joined_at,
        }
        for member, user in rows
    ]


@router.get("/{room_id}/audit")
async def get_audit_log(
    room_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if role not in ("owner", "instructor"):
        raise HTTPException(status_code=403, detail="Only owner or instructor can view audit log")

    result = await db.execute(
        select(AuditLog)
        .where(AuditLog.room_id == room_id)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
    )
    logs = result.scalars().all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "event_type": log.event_type,
            "meta": log.meta_json,
            "created_at": log.created_at,
        }
        for log in logs
    ]


@router.patch("/{room_id}/code")
async def save_code(
    room_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    role = await get_member_role(db, room_id, current_user.id)
    if not role:
        raise HTTPException(status_code=403, detail="Not a member of this room")
    if role == "viewer":
        raise HTTPException(status_code=403, detail="Viewers cannot save code")

    result = await db.execute(select(Room).where(Room.id == room_id))
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    room.code_snapshot = payload.get("code", room.code_snapshot)
    room.updated_at = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
    await log_audit(db, room_id, current_user.id, "code_saved", {"length": len(room.code_snapshot)})
    return {"saved": True, "length": len(room.code_snapshot)}