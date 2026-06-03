"""Rank-and-decide step: pick the SKU, or ask — the ask-vs-assume brain.

Given a customer intent and a shortlist of retrieved candidate SKUs, the LLM
decides one of: ``auto_matched`` (one candidate clearly fits), ``needs_clarification``
(plausible candidates differ in a way that matters — ask ONE precise question),
or ``not_found`` (nothing in the catalog fits — never invent a SKU).

The autonomous loop (``resolve``) asks at most two questions before committing:
stage 1 asks for the specific part name / a distinguishing detail; stage 2 shows
the concrete catalog options and asks which fits. After the budget is spent it
commits to its best candidate or declares not_found.

A post-LLM guard rejects any ``matched_sku`` that isn't in the candidate set, so
the model cannot hallucinate a SKU.
"""

from __future__ import annotations

from typing import Callable, Literal

import anthropic
from pydantic import BaseModel, Field

from .extract import LineItemIntent
from .normalize import normalize_oem
from .retriever import Candidate, CatalogIndex

DEFAULT_MODEL = "claude-opus-4-8"

DECIDE_SYSTEM = """\
You are the matching brain for RepuExpress, a Colombian auto & motorcycle parts \
distributor. You receive a customer's part intent and a SHORTLIST of candidate \
catalog SKUs already retrieved for it. Pick the SKU the customer most likely \
wants — choosing ONLY from the shortlist. NEVER invent a SKU; if nothing fits, \
say so.

Output exactly one decision:

- auto_matched: one candidate clearly fits (right part type + vehicle + specs). \
Set matched_sku, matched_name, a confidence in 0.80-1.00, and reasoning. Rules \
that matter: when the customer asked for the cheapest ("economico") and several \
equivalent candidates fit, pick the lowest price and say so. If the best match \
is discontinued or has a replaced_by / "reemplazado por" note, offer the \
REPLACEMENT SKU and explain it supersedes the old one. Respect stock — don't \
silently pick an out-of-stock item when an equivalent is in stock.

- needs_clarification: two or more candidates are plausible AND the difference \
matters to the customer (front vs rear, oil vs air filter, iridium vs standard, \
concentrate vs pre-mixed, gasoline vs diesel oil, ...), or a key detail is \
missing. Ask ONE precise question, in natural Colombian Spanish, and set \
confidence around 0.30-0.60:
  * Stage 1 (no question asked yet): ask whether the customer has the specific \
part name or a key distinguishing detail. Set question_stage = 1.
  * Stage 2 (one question already asked): present the concrete options you found \
— list each with its distinguishing spec and price — and ask which one fits. Set \
question_stage = 2 and fill suggested_options with those SKUs.

- not_found: no candidate is actually the requested part (e.g. the vehicle make \
isn't in the catalog at all). Set matched_sku = null, explain it's not available, \
and you may suggest a special order. Do NOT force a bad match.

The ask-vs-assume rule is the heart of your job: only ask when choosing wrong \
would cost a return or a wrong quote. If the candidates are equivalent for the \
customer's purpose, just pick one (assume) and justify it. Asking about \
everything is useless; assuming everything quotes wrong. Every decision's \
reasoning is read by a human reviewer — make it justify the call."""

_COMMIT_NOTE = (
    "\n\nNOTE: the question budget is spent. Do NOT ask again. Choose the single "
    "best candidate (auto_matched — note the residual uncertainty in reasoning and "
    "use a lower confidence) or declare not_found. clarifying_question must be null."
)


class Decision(BaseModel):
    matched_sku: str | None
    matched_name: str | None
    confidence: float
    decision: Literal["auto_matched", "needs_clarification", "not_found"]
    reasoning: str
    clarifying_question: str | None
    question_stage: int | None  # 1 = ask specific name, 2 = pick from options
    suggested_options: list[str] = Field(
        default_factory=list, description="SKUs shown to the customer at stage 2"
    )


def gather_candidates(
    intent: LineItemIntent, index: CatalogIndex, k: int = 15
) -> list[Candidate]:
    """OEM-exact matches first (if a code was given), then semantic matches, deduped."""
    candidates: list[Candidate] = []
    seen: set[str] = set()

    if intent.oem_code:
        key = normalize_oem(intent.oem_code)
        for item in index.catalog.by_oem.get(key, []):
            if item.sku not in seen:
                candidates.append(Candidate(item=item, score=1.0))  # exact code match
                seen.add(item.sku)

    for cand in index.retrieve(intent.part_query, k=k):
        if cand.item.sku not in seen:
            candidates.append(cand)
            seen.add(cand.item.sku)

    return candidates


def format_candidates(candidates: list[Candidate]) -> str:
    """Render the shortlist for the prompt, exposing what the decision turns on."""
    lines = []
    for i, cand in enumerate(candidates, 1):
        it = cand.item
        veh = " ".join(x for x in [it.make, it.model, it.year] if x) or "—"
        price = f"${it.price:,}" if it.price is not None else "price?"
        extra = []
        if it.replaced_by:
            extra.append(f"replaced_by={it.replaced_by}")
        if it.notes:
            extra.append(f"notes={it.notes}")
        tail = f" | {' ; '.join(extra)}" if extra else ""
        lines.append(
            f"{i}. {it.sku} | {it.name} | veh: {veh} | {price} | "
            f"stock: {it.stock_status.value}{tail}"
        )
    return "\n".join(lines) if lines else "(no candidates found)"


def _build_user_prompt(
    intent: LineItemIntent, candidates: list[Candidate], asked: int, force_commit: bool
) -> str:
    v = intent.vehicle
    veh = " ".join(x for x in [v.make, v.model, v.year] if x) or "unspecified"
    blocks = [
        "CUSTOMER INTENT",
        f"  said: {intent.customer_text!r}",
        f"  part: {intent.part_query}",
        f"  vehicle: {veh} | quantity: {intent.quantity} | oem: {intent.oem_code}",
        f"  qualifiers: {intent.qualifiers}",
        f"  questions already asked: {asked}",
        "",
        "CANDIDATE SKUS (choose only from these):",
        format_candidates(candidates),
    ]
    prompt = "\n".join(blocks)
    return prompt + (_COMMIT_NOTE if force_commit else "")


def _guard(decision: Decision, candidates: list[Candidate]) -> Decision:
    """No hallucinated SKUs: a matched_sku must be in the candidate set."""
    valid = {c.item.sku for c in candidates}
    if decision.matched_sku and decision.matched_sku not in valid:
        decision.decision = "not_found"
        decision.matched_sku = None
        decision.matched_name = None
        decision.confidence = min(decision.confidence, 0.3)
        decision.reasoning += " [guard: proposed SKU was not among candidates; suppressed]"
    return decision


def decide(
    intent: LineItemIntent,
    candidates: list[Candidate],
    *,
    asked: int = 0,
    force_commit: bool = False,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
) -> Decision:
    """One LLM decision over the candidate shortlist, with the anti-hallucination guard."""
    client = client or anthropic.Anthropic()
    response = client.messages.parse(
        model=model,
        max_tokens=2000,
        system=[
            {"type": "text", "text": DECIDE_SYSTEM, "cache_control": {"type": "ephemeral"}}
        ],
        messages=[
            {
                "role": "user",
                "content": _build_user_prompt(intent, candidates, asked, force_commit),
            }
        ],
        output_format=Decision,
    )
    return _guard(response.parsed_output, candidates)


# answer_fn receives the Decision (with its clarifying_question) and returns the
# customer's reply as text. CLI demo -> input(); tests -> a canned function.
AnswerFn = Callable[[Decision], str]


def resolve(
    intent: LineItemIntent,
    index: CatalogIndex,
    answer_fn: AnswerFn,
    *,
    max_questions: int = 2,
    k: int = 15,
    client: anthropic.Anthropic | None = None,
    model: str = DEFAULT_MODEL,
    decide_fn: Callable[..., Decision] | None = None,
) -> Decision:
    """The autonomous loop: ask up to ``max_questions``, then commit to a decision."""
    decide_fn = decide_fn or decide
    current = intent
    asked = 0
    while True:
        candidates = gather_candidates(current, index, k=k)
        force = asked >= max_questions
        decision = decide_fn(
            current,
            candidates,
            asked=asked,
            force_commit=force,
            client=client,
            model=model,
        )
        if force or decision.decision != "needs_clarification":
            return decision
        answer = answer_fn(decision)
        asked += 1
        # Fold the customer's reply into the query and re-retrieve next round.
        current = current.model_copy(
            update={"part_query": f"{current.part_query} {answer}".strip()}
        )
