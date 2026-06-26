"""Terminal actions: monta nota consolidada (PLAN §10) e dispara handoff.

PLAN §10:
  Estados que geram nota + workflow:
    - qualificado_agendado    (inclui dados do appointment)
    - qualificado_sem_agenda  (destaca "sem agendamento marcado")
    - handoff_solicitado      (motivo explícito do lead)
    - handoff_erro            (detalhe técnico)
  abandonado: sem nota, sem workflow (CRM trata).
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from dateutil import parser as dtparser

from zoi_agent.agent.schemas import SessionState
from zoi_agent.config import settings

TerminalReason = Literal[
    "qualificado_agendado",
    "qualificado_sem_agenda",
    "handoff_solicitado",
    "handoff_erro",
]


def _now_sp_str() -> str:
    return datetime.now(ZoneInfo(settings.app_timezone)).strftime("%Y-%m-%d %H:%M")


def _format_appointment(state: SessionState) -> str:
    if not state.appointment:
        return "sem agendamento marcado"
    iso = state.appointment.get("slot_iso") or ""
    if not iso:
        return "sem agendamento marcado"
    try:
        d = dtparser.isoparse(iso).astimezone(ZoneInfo(settings.app_timezone))
        return d.strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso


def _yes_no(b: bool | None) -> str:
    if b is True:
        return "sim"
    if b is False:
        return "não"
    return "-"


def _or_dash(v) -> str:
    if v is None or v == "":
        return "-"
    return str(v)


def _format_troca(state: SessionState) -> str:
    c = state.collected
    if not c.possui_troca:
        return "-"
    t = c.troca_completa
    if not t:
        return "sim, sem detalhes"
    parts = []
    if t.modelo:
        parts.append(t.modelo)
    if t.ano:
        parts.append(str(t.ano))
    if t.km is not None:
        parts.append(f"{t.km:_}km".replace("_", "."))
    quitado = "quitado" if t.quitado is True else ("financiado" if t.quitado is False else "")
    if quitado:
        parts.append(quitado)
    return " ".join(parts) if parts else "sim, sem detalhes"


def _format_pagamento(state: SessionState) -> str:
    c = state.collected
    if not c.forma_pagamento:
        return "-"
    base = c.forma_pagamento
    if c.forma_pagamento == "financiamento" and c.financiamento:
        fin = c.financiamento
        det = []
        if fin.entrada_status:
            det.append(f"entrada: {fin.entrada_status}")
        if fin.valor_entrada:
            det.append(f"valor: {fin.valor_entrada}")
        if det:
            return f"{base} ({', '.join(det)})"
    if c.forma_pagamento == "carta_credito" and c.banco_administradora:
        return f"{base} ({c.banco_administradora})"
    return base


def build_consolidated_note(
    *,
    state: SessionState,
    terminal_reason: TerminalReason,
    handoff_reason: str | None = None,
    observacoes: str | None = None,
) -> str:
    """Template completo PLAN §10 (campos do funil Nick)."""
    c = state.collected
    lines = [
        f"[NICK] Qualificação — {terminal_reason}",
        f"Data: {_now_sp_str()}",
        "",
        f"Lead: {_or_dash(c.nome)}",
        f"Cidade: {_or_dash(c.cidade)}",
        "",
        f"Veículo de interesse: {_or_dash(c.veiculo_interesse)}",
        f"Foco definido: {'sim' if c.veiculo_interesse_confirmado else '-'}",
        f"Intenção: {_or_dash(c.intencao)}",
        f"Possui troca: {_yes_no(c.possui_troca)}",
        f"Troca: {_format_troca(state)}",
        f"Pagamento: {_format_pagamento(state)}",
        f"Prazo de compra: {_or_dash(c.prazo_compra)}",
        "",
        f"Agendamento: {_format_appointment(state)}",
        f"Motivo encerramento: {_or_dash(handoff_reason)}",
        "",
        f"Observações: {_or_dash(observacoes)}",
    ]
    return "\n".join(lines)


# Estados terminais que disparam pipeline (nota + workflow + remove tag)
TERMINAL_REASONS = {
    "qualificado_agendado",
    "qualificado_sem_agenda",
    "handoff_solicitado",
    "handoff_erro",
}
