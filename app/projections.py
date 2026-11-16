from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .money import to_decimal128

MAIN_TENANT = "main"

CUSTOMERS = "customers"
PRODUCTS = "products"
INVOICES = "invoices"


@dataclass(frozen=True)
class Operation:
    collection: str
    filter: dict[str, Any]
    update: dict[str, Any]


def parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(UTC)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def product_fields(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "sku": data["sku"],
        "name": data["name"],
        "stock": to_decimal128(data.get("stock")),
        "criticalStock": to_decimal128(data.get("criticalStock")),
        "deleted": False,
    }


def project(event: dict[str, Any]) -> Operation | None:
    event_type = event.get("type", "")
    data = event.get("data") or {}
    entity_id = data.get("id")
    if not entity_id:
        return None
    key = {"_id": entity_id, "tenantId": event.get("tenantId") or MAIN_TENANT}

    match event_type:
        case "customer.created" | "customer.updated":
            fields = {"name": data["name"], "type": data.get("type"), "deleted": False}
            return Operation(CUSTOMERS, key, {"$set": fields})
        case "customer.deleted":
            return Operation(CUSTOMERS, key, {"$set": {"deleted": True}})
        case "product.created" | "product.updated" | "product.stock-changed":
            return Operation(PRODUCTS, key, {"$set": product_fields(data)})
        case "product.deleted":
            return Operation(PRODUCTS, key, {"$set": {"deleted": True}})
        case "invoice.approved":
            fields = {
                "number": data.get("number"),
                "customerId": data.get("customerId"),
                "customerName": data.get("customerName"),
                "grandTotal": to_decimal128(data.get("grandTotal")),
                "approvedAt": parse_time(data.get("at")),
            }
            return Operation(
                INVOICES,
                key,
                {"$set": fields, "$setOnInsert": {"status": "approved"}},
            )
        case "invoice.cancelled":
            fields = {"status": "cancelled", "cancelledAt": parse_time(data.get("at"))}
            return Operation(INVOICES, key, {"$set": fields})
        case _:
            return None
