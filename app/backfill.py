import logging
from typing import Any

import httpx

from .projections import MAIN_TENANT
from .store import Store

log = logging.getLogger(__name__)
PAGE_SIZE = 100
TENANT_HEADER = "X-Tenant-Id"


async def fetch_all(client: httpx.AsyncClient, url: str, tenant: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        response = await client.get(url, params={"page": page, "size": PAGE_SIZE}, headers={TENANT_HEADER: tenant})
        response.raise_for_status()
        body = response.json()
        items.extend(body["items"])
        if page >= body["meta"]["totalPages"]:
            return items
        page += 1


async def tenants(tenant_api: str) -> list[str]:
    if not tenant_api:
        return [MAIN_TENANT]
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{tenant_api}/internal/tenants")
        response.raise_for_status()
        return [str(t) for t in response.json()]


async def resync(store: Store, tenant: str, customer_api: str, product_api: str) -> dict[str, int]:
    async with httpx.AsyncClient(timeout=10) as client:
        customers = await fetch_all(client, f"{customer_api}/api/customers", tenant)
        products = await fetch_all(client, f"{product_api}/api/products", tenant)
    await store.replace_customers(tenant, customers)
    await store.replace_products(tenant, products)
    log.info("resynced tenant=%s customers=%d products=%d", tenant, len(customers), len(products))
    return {"customers": len(customers), "products": len(products)}


async def resync_all(store: Store, tenant_api: str, customer_api: str, product_api: str) -> int:
    ids = await tenants(tenant_api)
    for tenant in ids:
        await resync(store, tenant, customer_api, product_api)
    return len(ids)
