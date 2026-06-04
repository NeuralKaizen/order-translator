"""Quoting: turn an intent + its decision into a priced line item.

Deterministic — prices were already normalized to integer COP at load time, so
this just looks up the matched SKU's price and multiplies by quantity. Lines that
weren't confidently matched carry no price and don't count toward the total.
"""

from __future__ import annotations

from pydantic import BaseModel

from .decide import Decision
from .extract import LineItemIntent
from .models import Catalog


def format_cop(amount: int | None) -> str:
    """Render COP the Colombian way: 68000 -> '$68.000'. None -> '—'."""
    if amount is None:
        return "—"
    return "$" + f"{amount:,}".replace(",", ".")


class LineItemResult(BaseModel):
    """One quoted line of the structured order — the per-item output."""

    customer_text: str
    matched_sku: str | None
    matched_name: str | None
    quantity: int
    unit_price: int | None  # COP
    line_total: int | None  # unit_price * quantity
    confidence: float
    decision: str  # auto_matched | needs_clarification | not_found
    reasoning: str
    clarifying_question: str | None


def build_line_item(
    intent: LineItemIntent, decision: Decision, catalog: Catalog
) -> LineItemResult:
    """Combine the intent and the decision, pricing the matched SKU from the catalog."""
    quantity = intent.quantity or 1
    unit_price: int | None = None
    name = decision.matched_name

    if decision.matched_sku:
        item = catalog.by_sku.get(decision.matched_sku)
        if item:
            unit_price = item.price
            name = name or item.name

    line_total = unit_price * quantity if unit_price is not None else None

    return LineItemResult(
        customer_text=intent.customer_text,
        matched_sku=decision.matched_sku,
        matched_name=name,
        quantity=quantity,
        unit_price=unit_price,
        line_total=line_total,
        confidence=decision.confidence,
        decision=decision.decision,
        reasoning=decision.reasoning,
        clarifying_question=decision.clarifying_question,
    )


def quote_total(line_items: list[LineItemResult]) -> int:
    """Sum the priced lines — a partial total when some lines are unresolved."""
    return sum(li.line_total for li in line_items if li.line_total is not None)
