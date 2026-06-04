"""End-to-end pipeline: a raw order file -> a structured, quote-ready order.

ingest -> extract (LLM) -> retrieve -> rank-and-decide (LLM) -> quote -> reply (LLM).

This is the BATCH path used by ``run.py``: each ambiguous line carries its
clarifying question in the output (no interactive back-and-forth). The interactive
two-question loop lives in ``decide.resolve`` and is exercised by the demo script.

The LLM steps are injectable (``extract_fn`` / ``resolve_fn`` / ``reply_fn``) so the
assembly can be tested without hitting the API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import anthropic
from pydantic import BaseModel

from .decide import Decision, decide, gather_candidates
from .extract import LineItemIntent, extract_intents
from .ingest import RawOrder, parse_order
from .margin import AlternativeSuggestion, suggest_alternative
from .models import CatalogItem, StockStatus
from .quote import LineItemResult, build_line_item, quote_total
from .reply import draft_reply
from .retriever import CatalogIndex

DEFAULT_MODEL = "claude-opus-4-8"


class StructuredOrder(BaseModel):
    """The required per-order output: structured lines + quote + reply draft."""

    order_id: str
    channel: str | None
    line_items: list[LineItemResult]
    questions_for_customer: list[str]
    customer_reply_draft: str
    quote_total_partial: int
    estimated_margin_total: int  # hour-5: sum of per-line estimated margins


def process_order(
    path: str | Path,
    index: CatalogIndex,
    *,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    extract_fn: Callable[[RawOrder], object] | None = None,
    resolve_fn: Callable[[LineItemIntent], Decision] | None = None,
    reply_fn: Callable[[RawOrder, list[LineItemResult], list[str]], str] | None = None,
    alternative_fn: Callable[[CatalogItem], AlternativeSuggestion | None] | None = None,
) -> StructuredOrder:
    """Run one order through the full pipeline and assemble its structured output."""
    extract_fn = extract_fn or (
        lambda order: extract_intents(order, client=client, model=model)
    )
    resolve_fn = resolve_fn or (
        lambda intent: decide(
            intent, gather_candidates(intent, index), client=client, model=model
        )
    )
    reply_fn = reply_fn or (
        lambda order, lines, questions: draft_reply(
            order, lines, questions, client=client, model=model
        )
    )
    alternative_fn = alternative_fn or (lambda item: suggest_alternative(item, index))

    order = parse_order(path)
    extracted = extract_fn(order)

    line_items: list[LineItemResult] = []
    for intent in extracted.intents:
        line = build_line_item(intent, resolve_fn(intent), index.catalog)
        # hour-5: for an out-of-stock match, auto-suggest the closest in-stock SKU.
        if line.matched_sku:
            item = index.catalog.by_sku.get(line.matched_sku)
            if item and item.stock_status == StockStatus.OUT_OF_STOCK:
                line.suggested_alternative = alternative_fn(item)
        line_items.append(line)

    questions = [li.clarifying_question for li in line_items if li.clarifying_question]
    total = quote_total(line_items)
    margin_total = sum(li.line_margin for li in line_items if li.line_margin is not None)
    reply = reply_fn(order, line_items, questions)

    return StructuredOrder(
        order_id=order.order_id,
        channel=order.channel,
        line_items=line_items,
        questions_for_customer=questions,
        customer_reply_draft=reply,
        quote_total_partial=total,
        estimated_margin_total=margin_total,
    )
