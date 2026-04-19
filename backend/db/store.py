"""In-memory invoice store — only module allowed to hold persistence state."""

from backend.models.invoice import Invoice

_invoices: dict[str, Invoice] = {}


def save(invoice: Invoice) -> Invoice:
    _invoices[invoice.invoice_id] = invoice
    return invoice


def get(invoice_id: str) -> Invoice | None:
    return _invoices.get(invoice_id)


def list_all() -> list[Invoice]:
    return list(_invoices.values())


def clear() -> None:
    _invoices.clear()
