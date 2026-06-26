from __future__ import annotations

import json

import pytest

from zoi_agent.tools import faq as faq_mod


@pytest.mark.asyncio
async def test_faq_cache_hits_only_once(monkeypatch) -> None:
    calls = {"n": 0}

    async def fake_fetch() -> str:
        calls["n"] += 1
        return "P: Onde fica?\nR: Vila Vera, SP"

    fresh = faq_mod.TTLCache(ttl_seconds=60, loader=fake_fetch)
    monkeypatch.setattr(faq_mod, "_faq_cache", fresh)

    a = await faq_mod.get_faq_raw()
    b = await faq_mod.get_faq_raw()
    assert a == b
    assert calls["n"] == 1


def test_format_responses_nick_json() -> None:
    """FAQ Nick = JSON {responses:[{question,answer}]}; só respondidas viram texto P/R."""
    raw = json.dumps({
        "source": "FAQ Nick Motors",
        "totalQuestions": 3,
        "responses": [
            {"question": "Qual o endereço?", "answer": "Av. Dom Helder Camara, 761b - Vila Vera, SP"},
            {"question": "Qual horário?", "answer": "Seg-Sex 9h-19h, Sáb 9h-17h"},
            {"question": "Não respondida", "answer": ""},  # sem resposta -> ignorada
        ],
    }, ensure_ascii=False)
    out = faq_mod._format_responses(raw)
    assert "P: Qual o endereço?" in out
    assert "R: Av. Dom Helder Camara" in out
    assert "Qual horário?" in out
    assert "Não respondida" not in out  # sem answer não entra


def test_format_responses_empty_shell() -> None:
    raw = json.dumps({"source": "FAQ Nick Motors", "totalQuestions": 69, "responses": []})
    assert faq_mod._format_responses(raw) == ""


def test_format_responses_blank() -> None:
    assert faq_mod._format_responses("") == ""
    assert faq_mod._format_responses("   ") == ""
