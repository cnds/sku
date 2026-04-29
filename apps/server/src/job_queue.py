from __future__ import annotations

import json
import logging

from redis.asyncio import Redis, from_url

LOGGER = logging.getLogger(__name__)

_redis_client: Redis | None = None


def init_redis_client(redis_url: str) -> None:
    global _redis_client
    _redis_client = from_url(redis_url, encoding="utf-8", decode_responses=True)


def get_redis_client() -> Redis:
    if _redis_client is None:
        raise RuntimeError("Redis client has not been initialized.")
    return _redis_client


async def close_redis_client() -> None:
    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    _redis_client = None


async def enqueue_json(*, payload: dict[str, object], queue_name: str) -> bool:
    try:
        await get_redis_client().lpush(queue_name, json.dumps(payload))
        return True
    except Exception as exc:
        LOGGER.exception(
            "queue enqueue failed queue_name=%s job_id=%s product_id=%s shop_id=%s error=%s",
            queue_name,
            payload.get("job_id"),
            payload.get("product_id"),
            payload.get("shop_id"),
            exc,
        )
        return False


async def claim_json(*, queue_name: str, processing_queue_name: str) -> str | None:
    return await get_redis_client().rpoplpush(queue_name, processing_queue_name)


async def acknowledge_claimed_json(*, payload: str, processing_queue_name: str) -> None:
    await get_redis_client().lrem(processing_queue_name, 1, payload)


async def requeue_claimed_json(
    *,
    payload: str,
    processing_queue_name: str,
    queue_name: str,
) -> None:
    await acknowledge_claimed_json(payload=payload, processing_queue_name=processing_queue_name)
    await get_redis_client().rpush(queue_name, payload)


async def restore_claimed_json(
    *,
    queue_name: str,
    processing_queue_name: str,
) -> int:
    restored = 0
    while True:
        payload = await get_redis_client().rpoplpush(processing_queue_name, queue_name)
        if payload is None:
            return restored
        restored += 1
