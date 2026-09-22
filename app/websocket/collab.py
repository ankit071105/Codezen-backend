import json
from datetime import datetime, timezone
from fastapi import WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from app.core.security import decode_access_token
from app.core.database import AsyncSessionLocal
from app.models.room import Room, RoomMember
from app.models.events import OpLog, AuditLog
from app.websocket.hub import manager
import logging

logger = logging.getLogger(__name__)


def apply_op(snapshot: str, op: dict) -> str:
    op_type = op.get("type")
    pos = op.get("pos", 0)
    text = op.get("text", "")
    length = op.get("length", 0)

    if op_type == "insert":
        return snapshot[:pos] + text + snapshot[pos:]
    elif op_type == "delete":
        return snapshot[:pos] + snapshot[pos + length:]
    elif op_type == "replace":
        return snapshot[:pos] + text + snapshot[pos + length:]
    return snapshot


def transform_op(op1: dict, op2: dict) -> dict:
    if op1.get("type") == "insert" and op2.get("type") == "insert":
        if op2["pos"] <= op1["pos"]:
            op1 = {**op1, "pos": op1["pos"] + len(op2.get("text", ""))}
    elif op1.get("type") == "delete" and op2.get("type") == "insert":
        if op2["pos"] < op1["pos"]:
            op1 = {**op1, "pos": op1["pos"] + len(op2.get("text", ""))}
    elif op1.get("type") == "insert" and op2.get("type") == "delete":
        if op2["pos"] < op1["pos"]:
            op1 = {**op1, "pos": max(op2["pos"], op1["pos"] - op2.get("length", 0))}
    return op1


async def handle_collab_ws(websocket: WebSocket, room_id: str, token: str):
    payload = await decode_access_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = payload["sub"]
    user_name = "Unknown"

    async with AsyncSessionLocal() as db:
        from app.models.user import User
        user_result = await db.execute(
            __import__('sqlalchemy').select(User).where(User.id == user_id)
        )
        user_obj = user_result.scalar_one_or_none()
        if user_obj:
            user_name = user_obj.name.split()[0]  # first name only
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
        if not member:
            await websocket.close(code=4003, reason="Not a member of this room")
            return

        user_role = member.role

        result = await db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        if not room:
            await websocket.close(code=4004, reason="Room not found")
            return

        if room.is_locked and user_role not in ("owner", "instructor"):
            await websocket.close(code=4005, reason="Room is locked")
            return

    await manager.connect(websocket, room_id, user_id)

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Room).where(Room.id == room_id))
        room = result.scalar_one_or_none()
        await websocket.send_text(json.dumps({
            "type": "init",
            "room_id": room_id,
            "code_snapshot": room.code_snapshot if room else "",
            "online_users": manager.get_online_users(room_id),
            "your_role": user_role,
            "your_name": user_name,
        }))

    await manager.broadcast_to_room(room_id, {
        "type": "user_joined",
        "user_id": user_id,
        "user_name": user_name,
        "online_users": manager.get_online_users(room_id),
    }, exclude_user=user_id)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = msg.get("type")

            if msg_type == "op":
                if user_role == "viewer":
                    await manager.send_to_user(room_id, user_id, {
                        "type": "error", "message": "Viewers cannot edit code"
                    })
                    continue

                op = msg.get("op", {})
                revision = msg.get("revision", 0)

                async with AsyncSessionLocal() as db:
                    result = await db.execute(select(Room).where(Room.id == room_id))
                    room = result.scalar_one_or_none()
                    if not room:
                        continue

                    new_snapshot = apply_op(room.code_snapshot, op)
                    await db.execute(
                        update(Room)
                        .where(Room.id == room_id)
                        .values(code_snapshot=new_snapshot, updated_at=datetime.now(timezone.utc))
                    )

                    log = OpLog(
                        room_id=room_id,
                        user_id=user_id,
                        op_type=op.get("type", "unknown"),
                        op_json=op,
                        revision=revision,
                        created_at=datetime.now(timezone.utc),
                    )
                    db.add(log)
                    await db.commit()

                await manager.broadcast_to_room(room_id, {
                    "type": "op",
                    "user_id": user_id,
                    "user_name": user_name,
                    "op": op,
                    "revision": revision,
                }, exclude_user=user_id)

            elif msg_type == "cursor":
                await manager.broadcast_to_room(room_id, {
                    "type": "cursor",
                    "user_id": user_id,
                    "user_name": user_name,
                    "position": msg.get("position"),
                    "selection": msg.get("selection"),
                }, exclude_user=user_id)

            elif msg_type == "presence":
                await manager.broadcast_to_room(room_id, {
                    "type": "presence",
                    "user_id": user_id,
                    "user_name": user_name,
                    "status": msg.get("status", "active"),
                }, exclude_user=user_id)

            elif msg_type == "lock_room" and user_role in ("owner", "instructor"):
                lock = msg.get("locked", True)
                async with AsyncSessionLocal() as db:
                    await db.execute(
                        update(Room).where(Room.id == room_id).values(is_locked=lock)
                    )
                    db.add(AuditLog(
                        room_id=room_id,
                        user_id=user_id,
                        event_type="room_locked" if lock else "room_unlocked",
                        meta_json={},
                        created_at=datetime.now(timezone.utc),
                    ))
                    await db.commit()
                await manager.broadcast_to_room(room_id, {
                    "type": "room_lock_changed",
                    "locked": lock,
                    "by": user_id,
                })

    except WebSocketDisconnect:
        manager.disconnect(room_id, user_id)
        await manager.broadcast_to_room(room_id, {
            "type": "user_left",
            "user_id": user_id,
            "user_name": user_name,
            "online_users": manager.get_online_users(room_id),
        })