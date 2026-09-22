import json
import redis.asyncio as aioredis
from typing import Any, Optional
from app.core.config import settings

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client


async def redis_set(key: str, value: Any, ttl: Optional[int] = None) -> None:
    r = await get_redis()
    serialized = json.dumps(value) if not isinstance(value, str) else value
    if ttl:
        await r.setex(key, ttl, serialized)
    else:
        await r.set(key, serialized)


async def redis_get(key: str) -> Optional[Any]:
    r = await get_redis()
    val = await r.get(key)
    if val is None:
        return None
    try:
        return json.loads(val)
    except (json.JSONDecodeError, TypeError):
        return val


async def redis_delete(key: str) -> None:
    r = await get_redis()
    await r.delete(key)


async def redis_exists(key: str) -> bool:
    r = await get_redis()
    return await r.exists(key) > 0


async def redis_publish(channel: str, message: Any) -> None:
    r = await get_redis()
    payload = json.dumps(message) if not isinstance(message, str) else message
    await r.publish(channel, payload)


async def redis_blacklist_token(jti: str, ttl: int) -> None:
    await redis_set(f"blacklist:{jti}", "1", ttl=ttl)


async def redis_is_blacklisted(jti: str) -> bool:
    return await redis_exists(f"blacklist:{jti}")


async def redis_save_chat(room_id: str, user_id: str, role: str, content: str) -> None:
    key = f"chat:{room_id}"
    r = await get_redis()
    message = json.dumps({"user_id": user_id, "role": role, "content": content})
    await r.rpush(key, message)
    await r.expire(key, settings.CHAT_HISTORY_TTL_SECONDS)


async def redis_get_chat_history(room_id: str, limit: int = 20) -> list:
    key = f"chat:{room_id}"
    r = await get_redis()
    raw = await r.lrange(key, -limit, -1)
    return [json.loads(m) for m in raw]


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None
