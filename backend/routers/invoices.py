"""Invoice routes — thin HTTP layer, delegates to services."""

import logging

from backend.services import invoice_service

logger = logging.getLogger(__name__)


def handle_create(payload: dict) -> dict:
    """Handle POST /api/invoices."""
    invoice = invoice_service.create_invoice(payload["items"])
    return {
        "invoice_id": invoice.invoice_id,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
    }


def handle_get(invoice_id: str) -> dict | None:
    invoice = invoice_service.get_invoice(invoice_id)
    if invoice is None:
        return None
    return {
        "invoice_id": invoice.invoice_id,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
    }
