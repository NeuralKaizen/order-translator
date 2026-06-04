"""Customer reply draft: a short, natural Colombian-Spanish message.

Takes the priced line items + open questions and asks the LLM for a friendly
WhatsApp/email-style reply: quote what matched, ask what's ambiguous, flag what
isn't in the catalog. Free-text output (not structured) — it's prose for a human.
"""

from __future__ import annotations

import anthropic

from .ingest import RawOrder
from .quote import LineItemResult, format_cop

DEFAULT_MODEL = "claude-opus-4-8"

REPLY_SYSTEM = """\
You write the customer-facing reply for RepuExpress, a Colombian auto & motorcycle \
parts distributor. Tone: warm, concise, natural Colombian Spanish (WhatsApp/email).

You are given the result of processing one order: matched items with prices (COP), \
items that need a clarifying question, and items not found in the catalog. Write a \
single short reply that:
- quotes the matched items with their prices,
- asks the open clarifying questions naturally (don't dump them as a list),
- for not-found items, says they're not in the catalog and offers to look for an \
alternative or special-order them.

Never invent prices, parts, or SKUs — use only what you're given. Keep it to a few \
sentences. Output ONLY the reply text, no preamble."""


def _context(order: RawOrder, line_items: list[LineItemResult], questions: list[str]) -> str:
    lines = [f"CHANNEL: {order.channel}", f"CUSTOMER WROTE: {order.body!r}", ""]
    for li in line_items:
        if li.decision == "auto_matched":
            lines.append(
                f"[MATCHED] {li.customer_text!r} -> {li.matched_name} "
                f"({format_cop(li.unit_price)} x{li.quantity} = {format_cop(li.line_total)})"
            )
        elif li.decision == "needs_clarification":
            lines.append(f"[ASK] {li.customer_text!r}: {li.clarifying_question}")
        else:
            lines.append(f"[NOT FOUND] {li.customer_text!r}: not in catalog")
    return "\n".join(lines)


def draft_reply(
    order: RawOrder,
    line_items: list[LineItemResult],
    questions: list[str],
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> str:
    """Draft the Spanish customer reply for one processed order."""
    client = client or anthropic.Anthropic()
    response = client.messages.create(
        model=model,
        max_tokens=600,
        system=[
            {"type": "text", "text": REPLY_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[{"role": "user", "content": _context(order, line_items, questions)}],
    )
    return next(b.text for b in response.content if b.type == "text").strip()
