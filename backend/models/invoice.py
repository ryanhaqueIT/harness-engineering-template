"""Invoice domain model — pure data structure, no dependencies."""

from dataclasses import dataclass


@dataclass
class LineItem:
    description: str
    quantity: int
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class Invoice:
    invoice_id: str
    line_items: list[LineItem]
    tax_rate: float = 0.10

    @property
    def subtotal(self) -> float:
        return sum(item.total for item in self.line_items)

    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax, 2)
