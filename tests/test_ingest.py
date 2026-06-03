"""Tests for order ingestion against the 15 real order files."""

from pathlib import Path

import pytest

from src.ingest import parse_order, parse_order_text

ORDERS_DIR = Path(__file__).resolve().parents[1] / "info" / "data" / "orders"
ALL_ORDERS = sorted(ORDERS_DIR.glob("order_*.txt"))


def test_all_orders_present():
    assert len(ALL_ORDERS) == 15


@pytest.mark.parametrize("path", ALL_ORDERS, ids=lambda p: p.stem)
def test_every_order_parses_with_core_fields(path):
    order = parse_order(path)
    assert order.order_id == path.stem
    assert order.channel  # CHANNEL present in all 15
    assert order.sender  # FROM present in all 15
    assert order.body  # non-empty customer message


def test_plain_order_01():
    order = parse_order(ORDERS_DIR / "order_01.txt")
    assert order.channel == "whatsapp"
    assert order.sender == "+57 310 555 0142"
    assert "filtro de aceite" in order.body
    assert order.has_image is False


def test_image_order_07_routes_to_attachment():
    order = parse_order(ORDERS_DIR / "order_07.txt")
    assert order.has_image is True
    att = order.attachments[0]
    assert att.filename == "pieza_cliente.jpg"
    # The vision stub is captured on the attachment, identifying the part by OEM.
    assert att.vision_text is not None
    assert "CR8E" in att.vision_text
    # ...and the raw IMAGE DESCRIPTION block is NOT left in the customer body.
    assert "IMAGE DESCRIPTION" not in order.body
    assert "me sirven esta" in order.body


def test_only_order_07_has_image():
    with_image = [parse_order(p).order_id for p in ALL_ORDERS if parse_order(p).has_image]
    assert with_image == ["order_07"]


def test_subject_header_is_captured():
    # order_03 carries a SUBJECT header.
    assert parse_order(ORDERS_DIR / "order_03.txt").subject is not None


def test_missing_separator_falls_back_to_body():
    order = parse_order_text("necesito una bateria", order_id="adhoc")
    assert order.body == "necesito una bateria"
    assert order.channel is None
