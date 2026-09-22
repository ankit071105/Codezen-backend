import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.core.redis import redis_is_blacklisted, redis_blacklist_token

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(data: Dict[str, Any], expires_delta: timedelta, secret: str) -> str:
    payload = data.copy()
    payload["jti"] = str(uuid.uuid4())
    payload["iat"] = datetime.now(timezone.utc)
    payload["exp"] = datetime.now(timezone.utc) + expires_delta
    return jwt.encode(payload, secret, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: str, role: str) -> str:
    return _create_token(
        {"sub": user_id, "role": role, "type": "access"},
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        settings.JWT_SECRET_KEY,
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        {"sub": user_id, "type": "refresh"},
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        settings.JWT_SECRET_KEY,
    )


async def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )
        if payload.get("type") != "access":
            return None
        jti = payload.get("jti")
        if jti and await redis_is_blacklisted(jti):
            return None
        return payload
    except JWTError:
        return None


async def revoke_token(token: str) -> None:
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(0, exp - int(datetime.now(timezone.utc).timestamp()))
            await redis_blacklist_token(jti, ttl)
    except JWTError:
        pass


def create_invite_token(
    room_id: str,
    role: str,
    expires_hours: int = 24,
    single_use: bool = False,
) -> str:
    return _create_token(
        {
            "room_id": room_id,
            "role": role,
            "single_use": single_use,
            "type": "invite",
        },
        timedelta(hours=expires_hours),
        settings.INVITE_TOKEN_SECRET,
    )


def decode_invite_token(token: str) -> Optional[Dict[str, Any]]:
    try:
        payload = jwt.decode(
            token,
            settings.INVITE_TOKEN_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("type") != "invite":
            return None
        return payload
    except JWTError:
        return None
