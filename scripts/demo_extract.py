"""Live demo of the extract step. Needs a real ANTHROPIC_API_KEY in the env.

Usage:
    .venv/bin/python scripts/demo_extract.py                 # a spread of orders
    .venv/bin/python scripts/demo_extract.py order_07        # one order
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.extract import extract_intents  # noqa: E402
from src.ingest import parse_order  # noqa: E402

ORDERS_DIR = Path(__file__).resolve().parents[1] / "info" / "data" / "orders"
DEFAULT = ["order_01", "order_03", "order_06", "order_07", "order_11"]


def main() -> None:
    ids = sys.argv[1:] or DEFAULT
    for oid in ids:
        order = parse_order(ORDERS_DIR / f"{oid}.txt")
        t0 = time.time()
        result = extract_intents(order)
        dt = time.time() - t0
        print(f"\n===== {oid}  ({dt:.1f}s, {len(result.intents)} intent(s)) =====")
        print(f"  body: {order.body[:90]!r}")
        for it in result.intents:
            v = it.vehicle
            veh = " ".join(x for x in [v.make, v.model, v.year] if x) or "—"
            print(f"  • customer_text : {it.customer_text!r}")
            print(f"    part_query    : {it.part_query!r}")
            print(
                f"    vehicle/qty   : {veh} | qty={it.quantity} "
                f"| oem={it.oem_code} | job={it.is_job}"
            )
            if it.qualifiers:
                print(f"    qualifiers    : {it.qualifiers}")


if __name__ == "__main__":
    main()
