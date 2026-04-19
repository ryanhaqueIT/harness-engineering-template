"""Invoice service — business logic. Imports from db and models only."""

import logging
import uuid

from backend.db import store
from backend.models.invoice import Invoice, LineItem

logger = logging.getLogger(__name__)


def create_invoice(items: list[dict]) -> Invoice:
    """Create a new invoice from a list of line item dicts."""
    line_items = [
        LineItem(
            description=item["description"],
            quantity=item["quantity"],
            unit_price=item["unit_price"],
        )
        for item in items
    ]
    invoice = Invoice(
        invoice_id=str(uuid.uuid4()),
        line_items=line_items,
    )
    logger.info("created invoice %s with %d items", invoice.invoice_id, len(line_items))
    return store.save(invoice)


def get_invoice(invoice_id: str) -> Invoice | None:
    return store.get(invoice_id)
