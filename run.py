"""Demo runner: python run.py order_XX.txt -> structured order + quote + reply (JSON).

Accepts a path, or a bare order name/file resolved against info/data/orders/.
Needs a real ANTHROPIC_API_KEY in the environment.
"""

import sys
from pathlib import Path

from src.pipeline import process_order
from src.retriever import CatalogIndex

ORDERS_DIR = Path(__file__).resolve().parent / "info" / "data" / "orders"


def resolve_path(arg: str) -> Path:
    """Accept a real path, or a bare 'order_03' / 'order_03.txt' under the orders dir."""
    p = Path(arg)
    if p.exists():
        return p
    name = arg if arg.endswith(".txt") else f"{arg}.txt"
    candidate = ORDERS_DIR / name
    if candidate.exists():
        return candidate
    raise SystemExit(f"order file not found: {arg}")


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python run.py <order_XX.txt>")
    path = resolve_path(sys.argv[1])
    index = CatalogIndex.load_or_build()
    result = process_order(path, index)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
