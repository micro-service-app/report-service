from datetime import datetime
from typing import Any

from pymongo import AsyncMongoClient

from .money import to_decimal
from .projections import CUSTOMERS, INVOICES, MAIN_TENANT, PRODUCTS, Operation, product_fields
from .reports import ApprovedInvoice


class Store:
    def __init__(self, uri: str, database: str) -> None:
        self.client: AsyncMongoClient = AsyncMongoClient(uri, appname="report-service", tz_aware=True)
        self.db = self.client[database]

    async def close(self) -> None:
        await self.client.close()

    async def ping(self) -> None:
        await self.client.admin.command("ping")

    async def ensure_indexes(self) -> None:
        for collection in (CUSTOMERS, PRODUCTS, INVOICES):
            await self.db[collection].update_many({"tenantId": {"$exists": False}}, {"$set": {"tenantId": MAIN_TENANT}})
        for collection, old in ((INVOICES, "status_approved_at"), (PRODUCTS, "deleted"), (CUSTOMERS, "deleted")):
            if old in await self.db[collection].index_information():
                await self.db[collection].drop_index(old)
        await self.db[INVOICES].create_index(
            [("tenantId", 1), ("status", 1), ("approvedAt", -1)], name="tenant_status_approved_at"
        )
        await self.db[PRODUCTS].create_index([("tenantId", 1), ("deleted", 1)], name="tenant_deleted")
        await self.db[CUSTOMERS].create_index([("tenantId", 1), ("deleted", 1)], name="tenant_deleted")

    async def apply(self, op: Operation) -> None:
        await self.db[op.collection].update_one(op.filter, op.update, upsert=True)

    async def count_active(self, tenant: str, collection: str) -> int:
        return await self.db[collection].count_documents({"tenantId": tenant, "deleted": False})

    async def approved_invoices(self, tenant: str, since: datetime | None = None) -> list[ApprovedInvoice]:
        query: dict[str, Any] = {"tenantId": tenant, "status": "approved"}
        if since is not None:
            query["approvedAt"] = {"$gte": since}
        cursor = self.db[INVOICES].find(query, {"number": 1, "customerName": 1, "grandTotal": 1, "approvedAt": 1})
        return [
            ApprovedInvoice(
                id=doc["_id"],
                number=doc.get("number") or "",
                customer_name=doc.get("customerName") or "",
                grand_total=to_decimal(doc.get("grandTotal")),
                approved_at=doc["approvedAt"],
            )
            async for doc in cursor
        ]

    async def tracked_products(self, tenant: str) -> list[dict[str, Any]]:
        cursor = self.db[PRODUCTS].find({"tenantId": tenant, "deleted": False}).sort("sku", 1)
        return [doc async for doc in cursor]

    async def replace_customers(self, tenant: str, customers: list[dict[str, Any]]) -> None:
        ids = [c["id"] for c in customers]
        for c in customers:
            await self.db[CUSTOMERS].update_one(
                {"_id": c["id"], "tenantId": tenant},
                {"$set": {"name": c["name"], "type": c.get("type"), "deleted": False}},
                upsert=True,
            )
        await self.db[CUSTOMERS].update_many({"tenantId": tenant, "_id": {"$nin": ids}}, {"$set": {"deleted": True}})

    async def replace_products(self, tenant: str, products: list[dict[str, Any]]) -> None:
        ids = [p["id"] for p in products]
        for p in products:
            await self.db[PRODUCTS].update_one(
                {"_id": p["id"], "tenantId": tenant}, {"$set": product_fields(p)}, upsert=True
            )
        await self.db[PRODUCTS].update_many({"tenantId": tenant, "_id": {"$nin": ids}}, {"$set": {"deleted": True}})
