import asyncio
import json
import logging

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractQueue, AbstractRobustConnection

from .projections import project
from .store import Store

log = logging.getLogger(__name__)

EXCHANGE = "erp.events"
DEAD_EXCHANGE = "erp.dead"
QUEUE = "report-service"
BINDINGS = ["customer.#", "product.#", "invoice.#"]
DELIVERY_LIMIT = 10
PREFETCH = 50
RETRY_DELAY = 5


class EventConsumer:
    def __init__(self, url: str, store: Store) -> None:
        self.url = url
        self.store = store
        self.connection: AbstractRobustConnection | None = None
        self.queue: AbstractQueue | None = None

    async def start(self) -> None:
        self.connection = await aio_pika.connect_robust(self.url, client_properties={"connection_name": QUEUE})
        channel = await self.connection.channel()
        await channel.set_qos(prefetch_count=PREFETCH)
        events = await channel.declare_exchange(EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        dead = await channel.declare_exchange(DEAD_EXCHANGE, aio_pika.ExchangeType.TOPIC, durable=True)
        self.queue = await channel.declare_queue(
            QUEUE,
            durable=True,
            arguments={
                "x-queue-type": "quorum",
                "x-delivery-limit": DELIVERY_LIMIT,
                "x-dead-letter-exchange": DEAD_EXCHANGE,
                "x-dead-letter-routing-key": QUEUE,
            },
        )
        for key in BINDINGS:
            await self.queue.bind(events, key)
        parked = await channel.declare_queue(f"{QUEUE}.dead", durable=True, arguments={"x-queue-type": "quorum"})
        await parked.bind(dead, QUEUE)

    async def catch_up(self) -> int:
        handled = 0
        while True:
            message = await self.queue.get(no_ack=False, fail=False)
            if message is None:
                return handled
            await self._handle(message)
            handled += 1

    async def run(self) -> None:
        while True:
            try:
                async with self.queue.iterator() as messages:
                    async for message in messages:
                        await self._handle(message)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("event loop failed, retrying")
                await asyncio.sleep(RETRY_DELAY)

    async def _handle(self, message: AbstractIncomingMessage) -> None:
        try:
            operation = project(json.loads(message.body))
            if operation is not None:
                await self.store.apply(operation)
            await message.ack()
        except Exception:
            log.exception("projecting %s failed", message.routing_key)
            await asyncio.sleep(RETRY_DELAY)
            await message.nack(requeue=True)

    async def close(self) -> None:
        if self.connection is not None:
            await self.connection.close()
