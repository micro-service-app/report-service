# report-service

[English](README.md) · [Türkçe](README.tr.md)

Multi-ERP'nin raporlama okuma modeli. Python 3.13, FastAPI, async PyMongo, aio-pika (RabbitMQ); [uv](https://docs.astral.sh/uv/) ile yönetilir.

API sözleşmesi: [`contracts/openapi/reports.yaml`](https://github.com/micro-service-app/contracts/blob/main/openapi/reports.yaml)

## Nasıl çalışır

Servis bir isteği yanıtlamak için başka servisleri hiç çağırmaz. Kendi projeksiyonunu `erp_reports` veritabanında tutar:

| Koleksiyon | Kaynağı |
|---|---|
| `customers` | `customer.*` olayları |
| `products` | `product.stock-changed` dahil `product.*` olayları |
| `invoices` | `invoice.approved`, `invoice.cancelled` |

Açılışta:

1. `report-service` quorum kuyruğunu tanımlar (`erp.events` exchange'inde `customer.#`, `product.#`, `invoice.#`'e bağlı) ve kuyrukta bekleyen olayları kuyruk boşalana kadar işler,
2. ardından müşteri ve ürün listelerinin tamamını HTTP ile çeker (`resync`); çünkü örnek veriler doğrudan MongoDB'ye yazılır ve olay üretmez,
3. yeni olayları arka planda, sırayla ve tek tek tüketmeye devam eder. Başarısız bir olay 5 saniye sonra yeniden denenir; 10 teslimden sonra `report-service.dead` kuyruğuna taşınır.

Her projeksiyon olayın `tenantId`'siyle saklanır ve her uç yalnızca `X-Tenant-Id`'deki çalışma alanı için yanıt verir; açılıştaki senkronlama tenant-service'in listelediği tüm alanları dolaşır. Her projeksiyon varlık kimliğine göre upsert'tür, bu yüzden yeniden teslim edilen olaylar güvenlidir. `invoice.approved` durumu yalnızca ilk eklemede yazar; tekrar gelen bir onay iptal edilmiş bir faturayı canlandırmaz.

Ciro, onaylı faturaların KDV dahil `grandTotal` değeridir ve `REPORT_TIMEZONE` saat diliminde aylara bölünür.

## Yerelde çalıştırma

```bash
make -C ../platform up
uv run uvicorn app.main:app --reload --port 8084
```

## Test ve lint

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## Ayarlar

| Değişken | Varsayılan |
|---|---|
| `PORT` | `8084` |
| `MONGO_URI` | `mongodb://erp:erp-local-password@localhost:27017/?authSource=admin` |
| `MONGO_DB` | `erp_reports` |
| `RABBITMQ_URL` | boş, olaylar kapalı |
| `CUSTOMER_API_URL` | `http://localhost:8081` |
| `PRODUCT_API_URL` | `http://localhost:8082` |
| `TENANT_API_URL` | boş; yalnızca `main` alanı senkronlanır |
| `REPORT_TIMEZONE` | `Europe/Istanbul` |

## Uçlar

| Metot | Yol | |
|---|---|---|
| GET | `/api/reports/summary` | KPI sayıları, bu ayın ve toplam ciro, son beş fatura |
| GET | `/api/reports/revenue?months=12` | Aylık ciro, boş aylar dahil |
| GET | `/api/reports/low-stock` | Kritik seviyede ya da altındaki ürünler |
| POST | `/api/reports/resync` | Müşteri ve ürünleri kendi servislerinden yeniden yükler |
