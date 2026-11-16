from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from .money import money, quantity, to_decimal


@dataclass(frozen=True)
class ApprovedInvoice:
    id: str
    number: str
    customer_name: str
    grand_total: Decimal
    approved_at: datetime


def month_key(moment: datetime, tz: ZoneInfo) -> str:
    local = moment.replace(tzinfo=moment.tzinfo or UTC).astimezone(tz)
    return f"{local.year:04d}-{local.month:02d}"


def last_months(now: datetime, months: int, tz: ZoneInfo) -> list[str]:
    local = now.astimezone(tz)
    year, month = local.year, local.month
    keys = []
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return list(reversed(keys))


def revenue_series(invoices: list[ApprovedInvoice], months: int, now: datetime, tz: ZoneInfo) -> list[dict[str, Any]]:
    buckets = {key: [Decimal(0), 0] for key in last_months(now, months, tz)}
    for invoice in invoices:
        bucket = buckets.get(month_key(invoice.approved_at, tz))
        if bucket is not None:
            bucket[0] += invoice.grand_total
            bucket[1] += 1
    return [{"month": key, "revenue": money(total), "invoiceCount": count} for key, (total, count) in buckets.items()]


def is_low_stock(product: dict[str, Any]) -> bool:
    critical = to_decimal(product.get("criticalStock"))
    return critical > 0 and to_decimal(product.get("stock")) <= critical


def low_stock_item(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "productId": product["_id"],
        "sku": product["sku"],
        "name": product["name"],
        "stock": quantity(to_decimal(product.get("stock"))),
        "criticalStock": quantity(to_decimal(product.get("criticalStock"))),
    }


def summary(
    customer_count: int,
    product_count: int,
    invoices: list[ApprovedInvoice],
    low_stock_count: int,
    now: datetime,
    tz: ZoneInfo,
    recent: int = 5,
) -> dict[str, Any]:
    this_month = month_key(now, tz)
    monthly = (i.grand_total for i in invoices if month_key(i.approved_at, tz) == this_month)
    ordered = sorted(invoices, key=lambda i: i.approved_at, reverse=True)
    return {
        "customerCount": customer_count,
        "productCount": product_count,
        "invoiceCount": len(invoices),
        "revenueThisMonth": money(sum(monthly, Decimal(0))),
        "revenueTotal": money(sum((i.grand_total for i in invoices), Decimal(0))),
        "lowStockCount": low_stock_count,
        "recentInvoices": [
            {
                "id": i.id,
                "number": i.number,
                "customerName": i.customer_name,
                "grandTotal": money(i.grand_total),
                "approvedAt": i.approved_at.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            }
            for i in ordered[:recent]
        ],
    }
