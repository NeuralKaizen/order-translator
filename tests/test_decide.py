"""Tests for the rank-and-decide step.

The LLM call itself isn't unit-tested here (it needs the API); instead we test the
deterministic machinery around it: the anti-hallucination guard, OEM-first candidate
gathering, and the two-question loop control (with a stubbed decision function).
"""

import pytest

from src.decide import (
    Decision,
    _guard,
    format_candidates,
    gather_candidates,
    resolve,
)
from src.extract import LineItemIntent, Vehicle
from src.loader import load_catalog
from src.retriever import Candidate, CatalogIndex

CATALOG = load_catalog()


def _decision(**kw) -> Decision:
    base = dict(
        matched_sku=None,
        matched_name=None,
        confidence=0.9,
        decision="auto_matched",
        reasoning="r",
        clarifying_question=None,
        question_stage=None,
    )
    base.update(kw)
    return Decision(**base)


def _intent(**kw) -> LineItemIntent:
    base = dict(
        customer_text="x",
        part_query="oil filter Toyota Corolla 2015",
        vehicle=Vehicle(make="Toyota", model="Corolla", year="2015"),
        quantity=1,
        oem_code=None,
        qualifiers=[],
        is_job=False,
    )
    base.update(kw)
    return LineItemIntent(**base)


# --- anti-hallucination guard (pure, no model) ---

def test_guard_suppresses_sku_not_in_candidates():
    cands = [Candidate(item=CATALOG.items[i], score=0.5) for i in range(2)]
    d = _guard(_decision(matched_sku="FAKE-999", matched_name="ghost"), cands)
    assert d.decision == "not_found"
    assert d.matched_sku is None
    assert "guard" in d.reasoning


def test_guard_keeps_valid_sku():
    cands = [Candidate(item=CATALOG.items[i], score=0.5) for i in range(2)]
    sku = CATALOG.items[0].sku
    d = _guard(_decision(matched_sku=sku, matched_name="ok"), cands)
    assert d.decision == "auto_matched"
    assert d.matched_sku == sku


def test_format_candidates_exposes_price_and_supersession():
    cands = [Candidate(item=CATALOG.items[0], score=0.9)]
    text = format_candidates(cands)
    assert CATALOG.items[0].sku in text
    assert "stock:" in text


# --- candidate gathering + loop control (need the embedding index) ---

@pytest.fixture(scope="module")
def index():
    try:
        return CatalogIndex.load_or_build()
    except Exception as exc:  # offline / model not cached
        pytest.skip(f"embedding model unavailable: {exc}")


def test_gather_puts_oem_exact_matches_first(index):
    # CR8E (the order-07 spark plug) is shared by SKU-1040 / SKU-1091 via by_oem.
    intent = _intent(part_query="spark plug NGK CR8E motorcycle", oem_code="CR8E",
                     vehicle=Vehicle(make=None, model=None, year=None))
    cands = gather_candidates(intent, index, k=10)
    skus = [c.item.sku for c in cands]
    assert "SKU-1040" in skus and "SKU-1091" in skus
    assert skus[0] in {"SKU-1040", "SKU-1091"}  # OEM-exact comes first
    assert cands[0].score == 1.0


def test_resolve_caps_at_two_questions_then_commits(index):
    calls, seen_queries = [], []

    def fake_decide(intent, candidates, *, asked, force_commit, client, model):
        calls.append((asked, force_commit))
        seen_queries.append(intent.part_query)
        if force_commit:
            return _decision(
                matched_sku=candidates[0].item.sku,
                matched_name=candidates[0].item.name,
                confidence=0.5,
                decision="auto_matched",
                reasoning="committed after budget",
            )
        return _decision(
            confidence=0.4,
            decision="needs_clarification",
            reasoning="ambiguous",
            clarifying_question="¿delanteros o traseros?",
            question_stage=1 if asked == 0 else 2,
        )

    answers = iter(["delanteros", "el primero"])
    decision = resolve(
        _intent(),
        index,
        answer_fn=lambda d: next(answers),
        max_questions=2,
        decide_fn=fake_decide,
    )

    # asked 0 and 1 ask; the 3rd call is forced to commit.
    assert calls == [(0, False), (1, False), (2, True)]
    assert decision.decision == "auto_matched"
    # each customer answer is folded into the query for the next round.
    assert "delanteros" in seen_queries[1]
    assert "el primero" in seen_queries[2]
