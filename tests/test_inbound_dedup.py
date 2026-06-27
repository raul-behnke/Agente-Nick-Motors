"""Dedup de inbound: GHL re-tenta webhook (timeout/restart) com mesmo messageId."""
from __future__ import annotations

from zoi_agent.endpoints import inbound as inb


def test_seen_inbound_first_time_false_then_true():
    inb._SEEN_INBOUND.clear()
    assert inb._seen_inbound("msg-1") is False  # 1ª vez: processa
    assert inb._seen_inbound("msg-1") is True   # 2ª vez: já visto
    assert inb._seen_inbound("msg-1") is True


def test_seen_inbound_distinct_ids():
    inb._SEEN_INBOUND.clear()
    assert inb._seen_inbound("a") is False
    assert inb._seen_inbound("b") is False
    assert inb._seen_inbound("a") is True


def test_seen_inbound_empty_id_never_dedups():
    inb._SEEN_INBOUND.clear()
    assert inb._seen_inbound("") is False
    assert inb._seen_inbound("") is False


def test_seen_inbound_bounded():
    inb._SEEN_INBOUND.clear()
    old = inb._SEEN_MAX
    inb._SEEN_MAX = 5
    try:
        for i in range(10):
            inb._seen_inbound(f"m{i}")
        assert len(inb._SEEN_INBOUND) <= 5
        # os mais antigos foram evictados
        assert "m0" not in inb._SEEN_INBOUND
        assert "m9" in inb._SEEN_INBOUND
    finally:
        inb._SEEN_MAX = old
