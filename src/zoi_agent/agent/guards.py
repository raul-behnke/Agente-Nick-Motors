"""Guards críticos determinísticos Nick (camada Veltron portada, simplificada).

Dupla camada: a persona (NICK_INSTRUCTIONS) reforça no prompt; aqui garantimos
em código o que não pode depender do LLM.

Escopo Nick (deliberadamente enxuto — sem traços Veltron como perfil
varejo/atacado ou esconder-endereço):
  - Identidade IA: frase canônica de admissão no limiar.
  - (Endereço/visita NÃO é guard de handoff no Nick — endereço/horário é FAQ e
    visita é fluxo de agendamento. INVERTIDO vs Veltron, de propósito.)
  - (Anti-invenção / blindagem de external_id vive em
    team.runner._validate_inventory_decision — não duplicar aqui.)
  - (Preço: a IA nunca cota/negocia — reforçado na persona + fronteira-de-fato
    do editor; pedido explícito vira escalacao_pendente no updater.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from zoi_agent.agent.schemas import SessionState, StateUpdate

AI_IDENTITY_TEXT = (
    "Sou um atendente digital da Nick Motors e tô aqui pra te ajudar com as "
    "primeiras informações. Qualquer detalhe específico eu passo pra um consultor."
)


def should_admit_ai_identity(state: SessionState, threshold: int = 2) -> bool:
    """Admite ser assistente só quando questionado o suficiente (limiar atingido)."""
    return state.ai_identity_asked_count >= threshold


@dataclass
class GuardOutcome:
    """Resultado consolidado dos guards de um turno."""

    terminal_reason: str | None = None
    handoff_reason: str | None = None
    forced_text: str | None = None
    ai_identity_text: str | None = None
    topics_forced: list[str] = field(default_factory=list)


def apply_guards(
    state: SessionState,
    update: StateUpdate,
    user_text: str = "",
    *,
    ai_identity_threshold: int = 2,
) -> GuardOutcome:
    """Guards determinísticos Nick. Hoje: identidade IA."""
    out = GuardOutcome()

    asked_now = update.ai_identity_asked_count_delta > 0
    # +1 deste turno ainda não foi mergeado no state quando chamamos aqui;
    # considera o limiar incluindo o turno atual.
    effective = state.ai_identity_asked_count + (1 if asked_now else 0)
    if effective >= ai_identity_threshold:
        out.ai_identity_text = AI_IDENTITY_TEXT

    return out
