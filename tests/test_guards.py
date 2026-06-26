"""Testes dos guards determinísticos Nick (camada Veltron portada, slim)."""
from __future__ import annotations

from zoi_agent.agent.guards import AI_IDENTITY_TEXT, apply_guards, should_admit_ai_identity
from zoi_agent.agent.schemas import Collected, SessionState, StateUpdate


def _update(**kw) -> StateUpdate:
    base = dict(
        stage="descoberta", collected=Collected(), missing=[], next_action="x",
        sentiment="neutro", intent="qualificar",
    )
    base.update(kw)
    return StateUpdate(**base)


def test_ai_identity_silent_when_never_asked():
    st = SessionState(ai_identity_asked_count=0)
    out = apply_guards(st, _update(), "tudo bem?", ai_identity_threshold=2)
    assert out.ai_identity_text is None


def test_ai_identity_evades_first_time():
    # 1ª vez questionado neste turno (delta=1), state ainda 0 → effective=1 < 2 → evade
    st = SessionState(ai_identity_asked_count=0)
    out = apply_guards(st, _update(ai_identity_asked_count_delta=1), "você é um robô?", ai_identity_threshold=2)
    assert out.ai_identity_text is None


def test_ai_identity_admits_second_time():
    # já questionou antes (state=1) + de novo agora (delta=1) → effective=2 → admite
    st = SessionState(ai_identity_asked_count=1)
    out = apply_guards(st, _update(ai_identity_asked_count_delta=1), "é IA mesmo?", ai_identity_threshold=2)
    assert out.ai_identity_text == AI_IDENTITY_TEXT


def test_should_admit_threshold():
    assert should_admit_ai_identity(SessionState(ai_identity_asked_count=2)) is True
    assert should_admit_ai_identity(SessionState(ai_identity_asked_count=1)) is False


def test_guard_outcome_defaults_clean():
    out = apply_guards(SessionState(), _update(), "oi", ai_identity_threshold=2)
    assert out.terminal_reason is None
    assert out.forced_text is None
    assert out.topics_forced == []
