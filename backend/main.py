"""Entry point for the demo backend — wires routers and services together."""

import logging

from backend.db import store
from backend.routers import invoices

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_invoice(payload: dict) -> dict:
    return invoices.handle_create(payload)


def get_invoice(invoice_id: str) -> dict | None:
    return invoices.handle_get(invoice_id)


def list_invoices() -> list:
    return [{"invoice_id": inv.invoice_id, "total": inv.total} for inv in store.list_all()]


if __name__ == "__main__":
    logger.info("demo backend ready")
