"""Extract step: messy customer message -> a validated list of line-item intents.

This is the first LLM stage. It turns the free-text order (plus any vision
analysis of an attached photo) into structured ``intents`` — one per distinct
part the customer wants. It ONLY structures: it does not match SKUs or decide
anything. Matching is the retrieval step; deciding is the rank-and-decide loop.

Structured output is enforced via ``messages.parse()`` against a Pydantic schema,
so the JSON always comes back valid and typed — no prose parsing. The stable
system prompt carries a cache breakpoint (engages once it exceeds the model's
~4096-token minimum).
"""

from __future__ import annotations

import anthropic
from pydantic import BaseModel, Field

from .ingest import RawOrder

DEFAULT_MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are the intake parser for RepuExpress, a Colombian auto & motorcycle parts \
distributor. Customers write in messy, bilingual Spanish/Spanglish with typos, \
slang, and missing details. Some send a photo of the part instead of naming it.

Your ONLY job is to STRUCTURE the request into line-item intents — one per \
distinct part the customer wants. You do NOT match catalog SKUs, you do NOT pick \
a specific product, and you do NOT invent parts the customer didn't ask for. \
A later step handles matching and decisions.

For each intent:
- customer_text: the customer's own words for this item, VERBATIM and in the \
original language (a short snippet, not the whole message).
- part_query: a clean, retrieval-ready description of the part, leaning English \
to maximize catalog matching. Include the part TYPE plus vehicle and any key \
spec that is stated (e.g. "front brake disc Mazda 3 2016", "diesel engine oil \
Toyota Hilux 2018"). Translate slang to the real part ("balineras" -> "wheel \
bearing", "pastillas" -> "brake pads").
- vehicle: make / model / year when mentioned; null for any field not given.
- quantity: the count requested. Map "un par"/"las dos" -> 2, a stated number \
-> that number, a single discrete item -> 1. Use null ONLY when the needed \
quantity must be computed or asked (e.g. liters of oil for an oil change).
- oem_code: an OEM or cross-reference code if the customer (or the image) gives \
one (e.g. "90915-YZZD4", "CR8E"); otherwise null.
- qualifiers: short free-text specs that matter for choosing later — e.g. \
"front", "rear", "iridium", "cheapest", "diesel". If a variant is needed but \
the customer didn't specify it, record the open question (e.g. \
"front-or-rear unspecified"). Empty list if none.
- is_job: true when the request is a SERVICE/JOB that implies a SET of parts \
without naming them (e.g. "sincronizacion completa", "afinacion"); false for a \
named part.

If an IMAGE ANALYSIS block is provided, it is the output of a vision step \
describing the photographed part — treat it as the identity of what the customer \
is asking about and fold it into the relevant intent's part_query / oem_code.

Return strictly the structured intents. No commentary."""


class Vehicle(BaseModel):
    make: str | None
    model: str | None
    year: str | None


class LineItemIntent(BaseModel):
    customer_text: str
    part_query: str
    vehicle: Vehicle
    quantity: int | None
    oem_code: str | None
    qualifiers: list[str]
    is_job: bool


class ExtractedOrder(BaseModel):
    intents: list[LineItemIntent] = Field(
        description="One intent per distinct part the customer wants."
    )


def build_user_content(order: RawOrder) -> str:
    """Assemble the customer message + any vision analysis into the user turn."""
    parts = [f"CHANNEL: {order.channel}", f"MESSAGE:\n{order.body}"]
    for att in order.attachments:
        if att.vision_text:
            parts.append(
                f"IMAGE ANALYSIS (vision step output for '{att.filename}'):\n"
                f"{att.vision_text}"
            )
    return "\n\n".join(parts)


def extract_intents(
    order: RawOrder,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> ExtractedOrder:
    """Run the LLM extract step and return the validated intents."""
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=4000,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},  # engages past ~4096 tokens
            }
        ],
        messages=[{"role": "user", "content": build_user_content(order)}],
        output_format=ExtractedOrder,
    )
    return response.parsed_output
