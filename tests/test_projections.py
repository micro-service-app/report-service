from datetime import UTC, datetime
from decimal import Decimal

from bson.decimal128 import Decimal128

from app.projections import CUSTOMERS, INVOICES, PRODUCTS, project


def event(event_type: str, **data):
    return {"id": "evt", "type": event_type, "data": data}


def test_customer_events_upsert_and_soft_delete():
    created = project(event("customer.created", id="c1", name="Örnek Gıda", type="corporate"))
    deleted = project(event("customer.deleted", id="c1"))

    assert created.collection == CUSTOMERS
    assert created.filter == {"_id": "c1", "tenantId": "main"}
    assert created.update == {"$set": {"name": "Örnek Gıda", "type": "corporate", "deleted": False}}
    assert deleted.update == {"$set": {"deleted": True}}


def test_product_stock_changed_stores_decimals():
    op = project(event("product.stock-changed", id="p1", sku="PRD-1", name="Bal", stock="117.0", criticalStock="20"))

    assert op.collection == PRODUCTS
    assert op.update["$set"]["stock"] == Decimal128(Decimal("117.0"))
    assert op.update["$set"]["criticalStock"] == Decimal128(Decimal("20"))


def test_approved_invoice_never_overrides_cancellation():
    op = project(
        event(
            "invoice.approved",
            id="i1",
            number="ERP2026000000001",
            customerId="c1",
            customerName="Örnek Gıda",
            grandTotal="2375.70",
            at="2026-11-14T10:00:00Z",
            lines=[],
        )
    )

    assert op.collection == INVOICES
    assert op.update["$setOnInsert"] == {"status": "approved"}
    assert "status" not in op.update["$set"]
    assert op.update["$set"]["approvedAt"] == datetime(2026, 11, 14, 10, tzinfo=UTC)
    assert op.update["$set"]["grandTotal"] == Decimal128(Decimal("2375.70"))


def test_cancelled_invoice_sets_status():
    op = project(event("invoice.cancelled", id="i1", at="2026-11-15T08:30:00.123+03:00"))

    assert op.update["$set"]["status"] == "cancelled"
    assert op.update["$set"]["cancelledAt"] == datetime(2026, 11, 15, 5, 30, 0, 123000, tzinfo=UTC)


def test_unknown_or_incomplete_events_are_ignored():
    assert project(event("invoice.updated", id="i1")) is None
    assert project(event("customer.created")) is None
    assert project({"type": "product.created"}) is None


def test_events_are_scoped_to_their_tenant():
    op = project(
        {"id": "evt", "type": "product.updated", "tenantId": "t1", "data": {"id": "p1", "sku": "A", "name": "B"}}
    )

    assert op.filter == {"_id": "p1", "tenantId": "t1"}
