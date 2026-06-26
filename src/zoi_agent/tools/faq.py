"""FAQ tool: JSON do Custom Value GHL (Nick), cache 5min.

Formato Nick (`{{custom_values.faq}}`):
    {"source":"FAQ Nick Motors","totalQuestions":69,"answeredQuestions":N,
     "responses":[{"question":"...","answer":"..."}, ...]}

`get_faq_raw` devolve um texto Q/R limpo (só perguntas respondidas) pronto pra
injetar no prompt da persona. FAQ vazio -> string vazia (persona cai em
"confirmo com o consultor").
"""
from __future__ import annotations

import json
from typing import Any

from zoi_agent.cache import TTLCache
from zoi_agent.config import settings
from zoi_agent.ghl.custom_values import extract_value, get_custom_value
from zoi_agent.logging import get_logger

log = get_logger(__name__)


def _format_responses(raw: str) -> str:
    """Parse JSON Nick e formata só as respostas preenchidas em texto P/R."""
    if not raw or not raw.strip():
        return ""
    try:
        data = json.loads(raw)
    except Exception:
        # Já é texto livre (ou YAML legado) — injeta cru.
        return raw
    if isinstance(data, dict):
        responses = data.get("responses") or data.get("faq") or []
    elif isinstance(data, list):
        responses = data
    else:
        return raw

    blocks: list[str] = []
    for item in responses:
        if not isinstance(item, dict):
            continue
        q = (item.get("question") or item.get("pergunta") or "").strip()
        a = (item.get("answer") or item.get("resposta") or "").strip()
        if q and a:
            blocks.append(f"P: {q}\nR: {a}")
    return "\n\n".join(blocks)


async def _fetch_faq_raw() -> str:
    cv = await get_custom_value(settings.ghl_faq_custom_value_id)
    raw = extract_value(cv) or ""
    formatted = _format_responses(raw)
    log.info("faq_loaded", raw_bytes=len(raw), formatted_bytes=len(formatted))
    return formatted


_faq_cache: TTLCache[str] = TTLCache(
    ttl_seconds=settings.faq_cache_ttl_seconds, loader=_fetch_faq_raw
)


async def get_faq_raw() -> str:
    """Texto Q/R formatado (só respondidas), pronto pra injetar no prompt."""
    return await _faq_cache.get()


async def get_faq_parsed() -> Any:
    """Dict cru do FAQ (introspecção/teste)."""
    cv = await get_custom_value(settings.ghl_faq_custom_value_id)
    raw = extract_value(cv) or ""
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def invalidate_faq_cache() -> None:
    _faq_cache.invalidate()
