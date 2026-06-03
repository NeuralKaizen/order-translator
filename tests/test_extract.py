"""Tests for the extract step.

The prompt-assembly logic is unit-tested without the API. The actual LLM call is
an opt-in integration test (set RUN_LLM_TESTS=1) so the default suite stays fast,
free, and offline.
"""

import os

import pytest

from src.extract import ExtractedOrder, LineItemIntent, build_user_content, extract_intents
from src.ingest import parse_order, parse_order_text

ORDERS = os.path.join(os.path.dirname(__file__), "..", "info", "data", "orders")


def test_build_user_content_includes_channel_and_body():
    order = parse_order_text(
        "CHANNEL: whatsapp\nFROM: x\n---\nnecesito un filtro", order_id="t"
    )
    content = build_user_content(order)
    assert "CHANNEL: whatsapp" in content
    assert "necesito un filtro" in content
    assert "IMAGE ANALYSIS" not in content  # no attachment


def test_build_user_content_folds_in_vision_text():
    order = parse_order(os.path.join(ORDERS, "order_07.txt"))
    content = build_user_content(order)
    assert "IMAGE ANALYSIS" in content
    assert "pieza_cliente.jpg" in content
    assert "CR8E" in content  # the part identity from the vision step
    assert "me sirven esta" in content  # the customer's own words still present


def test_schema_shapes():
    # The Pydantic models are the contract the LLM output is validated against.
    fields = LineItemIntent.model_fields
    assert set(fields) == {
        "customer_text",
        "part_query",
        "vehicle",
        "quantity",
        "oem_code",
        "qualifiers",
        "is_job",
    }
    assert "intents" in ExtractedOrder.model_fields


# --- opt-in integration tests (hit the real API) ---
needs_llm = pytest.mark.skipif(
    os.environ.get("RUN_LLM_TESTS") != "1",
    reason="set RUN_LLM_TESTS=1 to run live LLM extract tests",
)


@needs_llm
def test_extract_order_01_single_item():
    order = parse_order(os.path.join(ORDERS, "order_01.txt"))
    result = extract_intents(order)
    assert len(result.intents) == 1
    intent = result.intents[0]
    assert intent.part_query  # non-empty clean query
    assert intent.vehicle.model and "corolla" in intent.vehicle.model.lower()


@needs_llm
def test_extract_order_03_two_items():
    order = parse_order(os.path.join(ORDERS, "order_03.txt"))
    result = extract_intents(order)
    # "pastillas de freno" + "un par de amortiguadores" -> two intents.
    assert len(result.intents) == 2
    quantities = {i.quantity for i in result.intents}
    assert 2 in quantities  # "un par" -> 2
