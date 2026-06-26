from __future__ import annotations

from zoi_agent.agent.schemas import (
    Collected,
    Financiamento,
    SessionState,
    TrocaInfo,
)
from zoi_agent.tools.terminal import build_consolidated_note


def _full_state(appointment=None) -> SessionState:
    return SessionState(
        collected=Collected(
            nome="Raul",
            cidade="São Paulo",
            veiculo_interesse="Renault Duster",
            veiculo_interesse_confirmado=True,
            intencao="troca",
            possui_troca=True,
            troca_completa=TrocaInfo(modelo="Gol", ano=2001, km=280000, quitado=True),
            forma_pagamento="financiamento",
            financiamento=Financiamento(entrada_status="sim", valor_entrada="R$ 20 mil"),
            prazo_compra="30 dias",
            interesse_agendamento=True,
        ),
        appointment=appointment,
    )


def test_note_qualificado_agendado() -> None:
    state = _full_state(
        appointment={"slot_iso": "2026-06-03T09:30:00-03:00", "id": "apt-1", "modelo": "Duster"},
    )
    note = build_consolidated_note(
        state=state, terminal_reason="qualificado_agendado", observacoes="primeira visita"
    )
    assert "[NICK] Qualificação — qualificado_agendado" in note
    assert "Lead: Raul" in note
    assert "Cidade: São Paulo" in note
    assert "Veículo de interesse: Renault Duster" in note
    assert "Foco definido: sim" in note
    assert "Intenção: troca" in note
    assert "Possui troca: sim" in note
    assert "Troca: Gol 2001 280.000km quitado" in note
    assert "Pagamento: financiamento (entrada: sim, valor: R$ 20 mil)" in note
    assert "Prazo de compra: 30 dias" in note
    assert "Agendamento: 03/06/2026 09:30" in note
    assert "Motivo encerramento: -" in note
    assert "Observações: primeira visita" in note


def test_note_qualificado_sem_agenda() -> None:
    state = _full_state()
    note = build_consolidated_note(state=state, terminal_reason="qualificado_sem_agenda")
    assert "qualificado_sem_agenda" in note
    assert "Agendamento: sem agendamento marcado" in note


def test_note_handoff_solicitado() -> None:
    state = SessionState(collected=Collected(nome="Raul"))
    note = build_consolidated_note(
        state=state,
        terminal_reason="handoff_solicitado",
        handoff_reason="lead pediu vendedor 2x",
    )
    assert "handoff_solicitado" in note
    assert "Lead: Raul" in note
    assert "Motivo encerramento: lead pediu vendedor 2x" in note
    assert "Cidade: -" in note
    assert "Veículo de interesse: -" in note


def test_note_handoff_erro() -> None:
    note = build_consolidated_note(
        state=SessionState(),
        terminal_reason="handoff_erro",
        handoff_reason="falha LLM updater 3x",
    )
    assert "handoff_erro" in note
    assert "Motivo encerramento: falha LLM updater 3x" in note


def test_note_carta_credito_pagamento() -> None:
    state = SessionState(
        collected=Collected(nome="X", forma_pagamento="carta_credito", banco_administradora="Itaú")
    )
    note = build_consolidated_note(
        state=state, terminal_reason="handoff_solicitado", handoff_reason="x"
    )
    assert "Pagamento: carta_credito (Itaú)" in note


def test_note_troca_sem_detalhes() -> None:
    state = SessionState(
        collected=Collected(nome="X", possui_troca=True, troca_completa=None),
    )
    note = build_consolidated_note(
        state=state, terminal_reason="handoff_solicitado", handoff_reason="x"
    )
    assert "Troca: sim, sem detalhes" in note


def test_note_sem_troca() -> None:
    state = SessionState(collected=Collected(nome="X", possui_troca=False))
    note = build_consolidated_note(
        state=state, terminal_reason="handoff_solicitado", handoff_reason="x"
    )
    assert "Possui troca: não" in note
    assert "Troca: -" in note
