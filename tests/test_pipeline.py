"""Test the end-to-end assembly with the LLM steps stubbed (no API, no model)."""

from pathlib import Path
from types import SimpleNamespace

from src.decide import Decision
from src.extract import ExtractedOrder, LineItemIntent, Vehicle
from src.loader import load_catalog
from src.pipeline import process_order

ORDER_03 = Path(__file__).resolve().parents[1] / "info" / "data" / "orders" / "order_03.txt"
CATALOG = load_catalog()
MATCHED_SKU = "SKU-1010"  # Pastillas de Freno Renault Duster 2016


def _intent(text, query, qty):
    return LineItemIntent(
        customer_text=text,
        part_query=query,
        vehicle=Vehicle(make="Renault", model="Duster", year="2016"),
        quantity=qty,
        oem_code=None,
        qualifiers=[],
        is_job=False,
    )


def _fake_extract(order):
    return ExtractedOrder(
        intents=[
            _intent("pastillas de freno", "brake pads Renault Duster 2016", 1),
            _intent("un par de amortiguadores", "shock absorber Renault Duster 2016", 2),
        ]
    )


def _fake_resolve(intent):
    # brake pads resolve confidently; shocks need front/rear clarification.
    if "brake" in intent.part_query:
        return Decision(
            matched_sku=MATCHED_SKU,
            matched_name="Pastillas de Freno Renault Duster 2016",
            confidence=0.93,
            decision="auto_matched",
            reasoning="single confident match",
            clarifying_question=None,
            question_stage=None,
        )
    return Decision(
        matched_sku=None,
        matched_name=None,
        confidence=0.4,
        decision="needs_clarification",
        reasoning="front vs rear shocks",
        clarifying_question="¿Los amortiguadores son delanteros o traseros?",
        question_stage=1,
    )


def test_process_order_assembles_structured_output():
    fake_index = SimpleNamespace(catalog=CATALOG)
    result = process_order(
        ORDER_03,
        fake_index,
        extract_fn=_fake_extract,
        resolve_fn=_fake_resolve,
        reply_fn=lambda order, lines, qs: "Hola, ya te cotizo.",
    )

    assert result.order_id == "order_03"
    assert result.channel  # parsed from the real header
    assert len(result.line_items) == 2

    matched = result.line_items[0]
    assert matched.decision == "auto_matched"
    assert matched.line_total == CATALOG.by_sku[MATCHED_SKU].price * 1

    shocks = result.line_items[1]
    assert shocks.decision == "needs_clarification"
    assert shocks.line_total is None

    # the open question is collected, and only the matched line counts toward the total.
    assert result.questions_for_customer == ["¿Los amortiguadores son delanteros o traseros?"]
    assert result.quote_total_partial == CATALOG.by_sku[MATCHED_SKU].price
    assert result.customer_reply_draft == "Hola, ya te cotizo."


def test_structured_order_serializes_to_json():
    fake_index = SimpleNamespace(catalog=CATALOG)
    result = process_order(
        ORDER_03,
        fake_index,
        extract_fn=_fake_extract,
        resolve_fn=_fake_resolve,
        reply_fn=lambda order, lines, qs: "ok",
    )
    blob = result.model_dump_json()
    assert '"order_id":"order_03"' in blob
    assert '"quote_total_partial"' in blob
