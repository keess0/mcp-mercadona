"""Tests de las salvaguardas de place_order a nivel de servidor MCP."""

import pytest

from mercadona_mcp import server
from mercadona_mcp.client import MercadonaError


def test_place_order_blocked_without_enable_checkout(monkeypatch):
    monkeypatch.delenv("MERCADONA_ENABLE_CHECKOUT", raising=False)
    with pytest.raises(MercadonaError, match="MERCADONA_ENABLE_CHECKOUT"):
        server.place_order(confirm=server.CONFIRM_PHRASE)


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_place_order_blocked_with_falsy_enable_checkout(monkeypatch, value):
    monkeypatch.setenv("MERCADONA_ENABLE_CHECKOUT", value)
    with pytest.raises(MercadonaError, match="MERCADONA_ENABLE_CHECKOUT"):
        server.place_order(confirm=server.CONFIRM_PHRASE)


def test_place_order_still_requires_confirm_phrase(monkeypatch):
    monkeypatch.setenv("MERCADONA_ENABLE_CHECKOUT", "1")
    with pytest.raises(MercadonaError, match="CONFIRMO EL PAGO"):
        server.place_order(confirm="lo que sea")


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes"])
def test_place_order_enabled_reaches_api(monkeypatch, value):
    monkeypatch.setenv("MERCADONA_ENABLE_CHECKOUT", value)
    called = {}

    def fake_place_order(slot_id, address_id, payment_card_id):
        called["args"] = (slot_id, address_id, payment_card_id)
        return {"order_id": "O1"}

    monkeypatch.setattr(server.api, "place_order", fake_place_order)
    out = server.place_order(confirm=server.CONFIRM_PHRASE, slot_id="s1")
    assert out == {"order_id": "O1"}
    assert called["args"] == ("s1", None, None)
