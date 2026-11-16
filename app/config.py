import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Settings:
    port: int
    mongo_uri: str
    mongo_db: str
    rabbitmq_url: str
    customer_api_url: str
    product_api_url: str
    tenant_api_url: str
    timezone: ZoneInfo


def load() -> Settings:
    return Settings(
        port=int(os.getenv("PORT", "8084")),
        mongo_uri=os.getenv("MONGO_URI", "mongodb://erp:erp-local-password@localhost:27017/?authSource=admin"),
        mongo_db=os.getenv("MONGO_DB", "erp_reports"),
        rabbitmq_url=os.getenv("RABBITMQ_URL", ""),
        customer_api_url=os.getenv("CUSTOMER_API_URL", "http://localhost:8081"),
        product_api_url=os.getenv("PRODUCT_API_URL", "http://localhost:8082"),
        tenant_api_url=os.getenv("TENANT_API_URL", ""),
        timezone=ZoneInfo(os.getenv("REPORT_TIMEZONE", "Europe/Istanbul")),
    )
