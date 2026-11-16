from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from bson.decimal128 import Decimal128

from app.reports import ApprovedInvoice, is_low_stock, last_months, low_stock_item, revenue_series, summary

IST = ZoneInfo("Europe/Istanbul")
NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


def invoice(n: int, total: str, at: datetime) -> ApprovedInvoice:
    return ApprovedInvoice(f"i{n}", f"ERP202600000000{n}", "Örnek Gıda", Decimal(total), at)


def test_last_months_crosses_year_boundary():
    assert last_months(datetime(2026, 2, 10, tzinfo=UTC), 4, IST) == ["2025-11", "2025-12", "2026-01", "2026-02"]


def test_revenue_series_fills_empty_months_and_uses_local_month():
    invoices = [
        invoice(1, "2375.70", datetime(2026, 11, 3, tzinfo=UTC)),
        invoice(2, "100.00", datetime(2026, 11, 10, tzinfo=UTC)),
        invoice(3, "50.00", datetime(2026, 10, 31, 22, 30, tzinfo=UTC)),
        invoice(4, "999.00", datetime(2025, 1, 1, tzinfo=UTC)),
    ]

    series = revenue_series(invoices, 3, NOW, IST)

    assert series == [
        {"month": "2026-09", "revenue": "0.00", "invoiceCount": 0},
        {"month": "2026-10", "revenue": "0.00", "invoiceCount": 0},
        {"month": "2026-11", "revenue": "2525.70", "invoiceCount": 3},
    ]


def test_summary_totals_and_recent_order():
    invoices = [
        invoice(1, "2375.70", datetime(2026, 10, 5, tzinfo=UTC)),
        invoice(2, "100.00", datetime(2026, 11, 10, tzinfo=UTC)),
        invoice(3, "40.30", datetime(2026, 11, 12, tzinfo=UTC)),
    ]

    result = summary(3, 5, invoices, 1, NOW, IST, recent=2)

    assert result["invoiceCount"] == 3
    assert result["revenueThisMonth"] == "140.30"
    assert result["revenueTotal"] == "2516.00"
    assert [r["id"] for r in result["recentInvoices"]] == ["i3", "i2"]
    assert result["recentInvoices"][0]["approvedAt"] == "2026-11-12T00:00:00.000Z"


def test_low_stock_rules():
    critical = {
        "_id": "p1",
        "sku": "PRD-2",
        "name": "Mouse",
        "stock": Decimal128("8"),
        "criticalStock": Decimal128("15"),
    }
    negative = {**critical, "stock": Decimal128("-5")}
    untracked = {**critical, "stock": Decimal128("0"), "criticalStock": Decimal128("0")}
    healthy = {**critical, "stock": Decimal128("117.0")}

    assert is_low_stock(critical)
    assert is_low_stock(negative)
    assert not is_low_stock(untracked)
    assert not is_low_stock(healthy)
    assert low_stock_item(healthy)["stock"] == "117"
