"""Live demo of the retrieve -> rank-and-decide loop (the 2-question agent).

Walks one order through: ingest -> extract -> for each intent, resolve (asking up
to two clarifying questions interactively) -> print the decision.

Usage:
    .venv/bin/python scripts/demo_decide.py            # order_03 (multi-item)
    .venv/bin/python scripts/demo_decide.py order_02   # underspecified filter
Needs a real ANTHROPIC_API_KEY in the env.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.decide import Decision, resolve  # noqa: E402
from src.extract import extract_intents  # noqa: E402
from src.ingest import parse_order  # noqa: E402
from src.retriever import CatalogIndex  # noqa: E402

ORDERS_DIR = Path(__file__).resolve().parents[1] / "info" / "data" / "orders"


def ask(decision: Decision) -> str:
    print(f"\n  🤖 (pregunta {decision.question_stage}): {decision.clarifying_question}")
    if decision.suggested_options:
        print(f"     opciones del catálogo: {decision.suggested_options}")
    return input("  👤 tu respuesta: ").strip()


def main() -> None:
    oid = sys.argv[1] if len(sys.argv) > 1 else "order_03"
    print("Loading catalog + embedding index...")
    index = CatalogIndex.load_or_build()
    order = parse_order(ORDERS_DIR / f"{oid}.txt")
    print(f"\n=== {oid} ===\n  body: {order.body!r}")

    extracted = extract_intents(order)
    print(f"  extracted {len(extracted.intents)} intent(s)")

    for it in extracted.intents:
        print(f"\n--- intent: {it.customer_text!r}  ->  {it.part_query!r}")
        decision = resolve(it, index, answer_fn=ask)
        print(f"  decision : {decision.decision}  (confidence {decision.confidence:.2f})")
        print(f"  sku      : {decision.matched_sku}  {decision.matched_name or ''}")
        print(f"  reasoning: {decision.reasoning}")


if __name__ == "__main__":
    main()
