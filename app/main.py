import asyncio
import logging
import re
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse

from . import config
from .backfill import resync, resync_all
from .consumer import EventConsumer
from .projections import CUSTOMERS, PRODUCTS
from .reports import is_low_stock, last_months, low_stock_item, revenue_series, summary
from .store import Store

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("report-service")

settings = config.load()
store = Store(settings.mongo_uri, settings.mongo_db)
RESYNC_RETRY = 10


async def resync_until_success() -> None:
    while True:
        try:
            await resync_all(store, settings.tenant_api_url, settings.customer_api_url, settings.product_api_url)
            return
        except Exception as e:
            log.warning("initial resync failed (%s), retrying in %ss", e, RESYNC_RETRY)
            await asyncio.sleep(RESYNC_RETRY)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await store.ensure_indexes()
    tasks: list[asyncio.Task] = []
    consumer: EventConsumer | None = None

    if settings.rabbitmq_url:
        consumer = EventConsumer(settings.rabbitmq_url, store)
        await consumer.start()
        replayed = await consumer.catch_up()
        log.info("caught up with %d events", replayed)
        tasks.append(asyncio.create_task(consumer.run()))
    else:
        log.warning("RABBITMQ_URL not set, events are disabled")

    tasks.append(asyncio.create_task(resync_until_success()))
    yield

    for task in tasks:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    if consumer is not None:
        await consumer.close()
    await store.close()


app = FastAPI(title="report-service", version="0.1.0", lifespan=lifespan)
TENANT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def tenant_id(x_tenant_id: Annotated[str | None, Header()] = None) -> str:
    if not x_tenant_id or not TENANT_PATTERN.fullmatch(x_tenant_id):
        raise HTTPException(status_code=401, detail="Workspace required")
    return x_tenant_id


Tenant = Annotated[str, Depends(tenant_id)]


@app.get("/health")
async def health():
    return {"status": "up"}


@app.get("/ready")
async def ready():
    try:
        await store.ping()
    except Exception as e:
        return JSONResponse({"status": "down", "mongo": str(e)}, status_code=503)
    return {"status": "ready"}


@app.get("/api/reports/summary")
async def get_summary(tenant: Tenant):
    products = await store.tracked_products(tenant)
    return summary(
        customer_count=await store.count_active(tenant, CUSTOMERS),
        product_count=await store.count_active(tenant, PRODUCTS),
        invoices=await store.approved_invoices(tenant),
        low_stock_count=sum(1 for p in products if is_low_stock(p)),
        now=datetime.now(UTC),
        tz=settings.timezone,
    )


@app.get("/api/reports/revenue")
async def get_revenue(tenant: Tenant, months: int = Query(12, ge=1, le=24)):
    now = datetime.now(UTC)
    first = last_months(now, months, settings.timezone)[0]
    since = datetime.fromisoformat(f"{first}-01T00:00:00").replace(tzinfo=settings.timezone)
    return revenue_series(await store.approved_invoices(tenant, since), months, now, settings.timezone)


@app.get("/api/reports/low-stock")
async def get_low_stock(tenant: Tenant):
    return [low_stock_item(p) for p in await store.tracked_products(tenant) if is_low_stock(p)]


@app.post("/api/reports/resync")
async def post_resync(tenant: Tenant):
    return await resync(store, tenant, settings.customer_api_url, settings.product_api_url)
