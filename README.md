# report-service

[English](README.md) · [Türkçe](README.tr.md)

Reporting read model for Multi-ERP. Python 3.13, FastAPI, PyMongo async, aio-pika (RabbitMQ), managed with [uv](https://docs.astral.sh/uv/).

API contract: [`contracts/openapi/reports.yaml`](https://github.com/micro-service-app/contracts/blob/main/openapi/reports.yaml)

## How it works

The service never calls other services to answer a request. It keeps its own projection in `erp_reports`:

| Collection | Built from |
|---|---|
| `customers` | `customer.*` events |
| `products` | `product.*` events, including `product.stock-changed` |
| `invoices` | `invoice.approved`, `invoice.cancelled` |

On startup it

1. declares its quorum queue `report-service` (bound to `customer.#`, `product.#`, `invoice.#` on the `erp.events` exchange) and handles the events waiting in it until it is empty,
2. then pulls the full customer and product lists over HTTP (`resync`), because seed data is written straight into MongoDB and never produces events,
3. keeps consuming new events in the background, one at a time and in order. A failing event is retried after 5 seconds; after 10 deliveries it moves to `report-service.dead`.

Every projection is stored with the event's `tenantId` and every endpoint answers only for the workspace in `X-Tenant-Id`; the startup resync walks every workspace listed by tenant-service. Every projection is an upsert keyed by the entity id, so redelivered events are safe. `invoice.approved` sets the status only on insert, so a replayed approval never revives a cancelled invoice.

Revenue is the VAT-inclusive `grandTotal` of approved invoices, bucketed by month in `REPORT_TIMEZONE`.

## Run locally

```bash
make -C ../platform up
uv run uvicorn app.main:app --reload --port 8084
```

## Test and lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Configuration

| Variable | Default |
|---|---|
| `PORT` | `8084` |
| `MONGO_URI` | `mongodb://erp:erp-local-password@localhost:27017/?authSource=admin` |
| `MONGO_DB` | `erp_reports` |
| `RABBITMQ_URL` | empty, events disabled |
| `CUSTOMER_API_URL` | `http://localhost:8081` |
| `PRODUCT_API_URL` | `http://localhost:8082` |
| `TENANT_API_URL` | empty, resync only the `main` workspace |
| `REPORT_TIMEZONE` | `Europe/Istanbul` |

## Endpoints

| Method | Path | |
|---|---|---|
| GET | `/api/reports/summary` | KPI counts, revenue this month and in total, five most recent invoices |
| GET | `/api/reports/revenue?months=12` | Monthly revenue, empty months included |
| GET | `/api/reports/low-stock` | Products at or below their critical level |
| POST | `/api/reports/resync` | Reload customers and products from their services |
