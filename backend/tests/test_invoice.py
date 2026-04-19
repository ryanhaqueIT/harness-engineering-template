"""Tests for the invoice demo — exercises models, services, and routers."""

import pytest

from backend.db import store
from backend.models.invoice import Invoice, LineItem
from backend.routers import invoices
from backend.services import invoice_service


@pytest.fixture(autouse=True)
def clean_store():
    store.clear()
    yield
    store.clear()


def test_line_item_total():
    item = LineItem(description="Widget", quantity=3, unit_price=10.0)
    assert item.total == 30.0


def test_invoice_totals():
    invoice = Invoice(
        invoice_id="inv-001",
        line_items=[
            LineItem(description="Widget", quantity=3, unit_price=10.0),
            LineItem(description="Gadget", quantity=1, unit_price=25.0),
        ],
    )
    assert invoice.subtotal == 55.0
    assert invoice.tax == 5.50
    assert invoice.total == 60.50


def test_service_creates_and_retrieves_invoice():
    created = invoice_service.create_invoice(
        [{"description": "Widget", "quantity": 2, "unit_price": 10.0}]
    )
    fetched = invoice_service.get_invoice(created.invoice_id)
    assert fetched is not None
    assert fetched.total == 22.0


def test_router_create_returns_totals():
    response = invoices.handle_create(
        {"items": [{"description": "Widget", "quantity": 3, "unit_price": 10.0}]}
    )
    assert response["subtotal"] == 30.0
    assert response["tax"] == 3.0
    assert response["total"] == 33.0
    assert "invoice_id" in response


def test_router_get_missing_returns_none():
    assert invoices.handle_get("missing-id") is None


def test_router_get_existing_returns_dict():
    created = invoice_service.create_invoice(
        [{"description": "Item", "quantity": 1, "unit_price": 5.0}]
    )
    got = invoices.handle_get(created.invoice_id)
    assert got is not None
    assert got["invoice_id"] == created.invoice_id
