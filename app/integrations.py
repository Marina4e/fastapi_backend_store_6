from __future__ import annotations

import json
import asyncio
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from redis.asyncio import Redis

from app.config import Settings


class Integrations:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.redis: Redis | None = None
        self.rabbitmq: AbstractRobustConnection | None = None
        self.rabbitmq_channel: AbstractChannel | None = None

    async def connect(self, attempts: int = 10, delay_seconds: float = 2.0) -> None:
        self.redis = Redis.from_url(self.settings.redis_url, decode_responses=True)
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                self.rabbitmq = await aio_pika.connect_robust(self.settings.rabbitmq_url)
                break
            except Exception as exc:
                last_error = exc
                await asyncio.sleep(delay_seconds)
        else:
            if last_error is not None:
                raise last_error

        self.rabbitmq_channel = await self.rabbitmq.channel(publisher_confirms=False)
        await self.rabbitmq_channel.declare_queue(
            self.settings.rabbitmq_purchase_queue,
            durable=True,
        )

    async def close(self) -> None:
        if self.redis is not None:
            await self.redis.aclose()
        if self.rabbitmq is not None:
            await self.rabbitmq.close()

    async def publish_purchase(self, payload: dict[str, Any]) -> None:
        if self.redis is not None:
            now = datetime.now(UTC).isoformat()
            pipe = self.redis.pipeline(transaction=False)
            pipe.incr("store:purchases:success")
            pipe.set(
                "store:purchases:last",
                json.dumps({**payload, "created_at": now}, separators=(",", ":")),
            )
            await pipe.execute()

        if self.rabbitmq_channel is not None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            await self.rabbitmq_channel.default_exchange.publish(
                aio_pika.Message(
                    body=body,
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json",
                ),
                routing_key=self.settings.rabbitmq_purchase_queue,
            )

    async def status(self) -> dict[str, Any]:
        redis_status: dict[str, Any] = {"connected": False}
        rabbitmq_status: dict[str, Any] = {"connected": False}

        if self.redis is not None:
            try:
                pong = await self.redis.ping()
                success_count = await self.redis.get("store:purchases:success")
                last_purchase = await self.redis.get("store:purchases:last")
                redis_status = {
                    "connected": bool(pong),
                    "successful_purchases_recorded": int(success_count or 0),
                    "last_purchase": json.loads(last_purchase) if last_purchase else None,
                }
            except Exception as exc:
                redis_status = {"connected": False, "error": type(exc).__name__}

        if self.rabbitmq is not None and self.rabbitmq_channel is not None:
            try:
                queue = await self.rabbitmq_channel.declare_queue(
                    self.settings.rabbitmq_purchase_queue,
                    durable=True,
                    passive=True,
                )
                rabbitmq_status = {
                    "connected": not self.rabbitmq.is_closed,
                    "queue": self.settings.rabbitmq_purchase_queue,
                    "messages_ready": queue.declaration_result.message_count,
                    "consumers": queue.declaration_result.consumer_count,
                }
            except Exception as exc:
                rabbitmq_status = {"connected": False, "error": type(exc).__name__}

        return {"redis": redis_status, "rabbitmq": rabbitmq_status}
