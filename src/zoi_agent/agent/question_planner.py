"""Planner determinístico da próxima pergunta — funil Nick Motors (PLAN §4.2).

Resolve estruturalmente os 3 vícios do Maestro legado:
  - REPETIDA: cruza missing real com state.last_asked_fields (rolling window).
  - AMBÍGUA: 1 campo por turno; frase canônica vem do Python.
  - SEM LÓGICA: ignora update.missing/next_action; recalcula missing do
    state.collected real após o merge.

Não usa LLM. O Team leader (NICK) recebe a `NextQuestion` no payload e veste de
persona — mas o TEMA é fixo aqui.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zoi_agent.agent.schemas import Collected, SessionState, StateUpdate, _tem_troca

QuestionIntent = Literal["funil", "foco", "agendamento", "duvida", "nenhum"]


@dataclass
class NextQuestion:
    field: str | None
    intent: QuestionIntent
    canonical_text: str
    skip_funnel_reason: str | None = None


# Frases-tema por campo. NICK pode variar tom mas mantém o tópico.
CANONICAL_QUESTIONS: dict[str, str] = {
    "nome": "Como posso te chamar?",
    "cidade": "De qual cidade/região você fala com a gente?",
    "veiculo_interesse": "Qual veículo te interessou?",
    "veiculo_interesse_confirmado": "Esse foi o que chamou atenção?",
    "intencao": "É compra direta ou tá pensando em dar seu carro na troca?",
    "troca_completa.modelo": "Qual o modelo do carro que você daria na troca?",
    "troca_completa.ano": "E o ano dele?",
    "troca_completa.km": "Quilometragem aproximada?",
    "troca_completa.quitado": "Tá quitado?",
    "troca_completa.metodo_restante": "Como você pretende pagar o restante além da troca?",
    "forma_pagamento": "Como pretende fazer o pagamento: à vista, financiamento, carta de crédito ou cartão?",
    "financiamento.entrada_status": "Você tem valor de entrada pro financiamento?",
    "financiamento.valor_entrada": "Qual valor de entrada você consegue dar?",
    "banco_administradora": "Qual banco/administradora é a sua carta de crédito?",
    "prazo_compra": "Pra quando você pretende fechar a compra?",
    "interesse_agendamento": "Quer agendar uma visita pra ver pessoalmente?",
}


# Ordem PRIORITY com subcampos granulares (troca / financiamento).
PRIORITY_FUNNEL: tuple[str, ...] = (
    "nome",
    "cidade",
    "veiculo_interesse",
    "veiculo_interesse_confirmado",
    "intencao",
    "troca_completa.modelo",
    "troca_completa.ano",
    "troca_completa.km",
    "troca_completa.quitado",
    "troca_completa.metodo_restante",
    "forma_pagamento",
    "financiamento.entrada_status",
    "financiamento.valor_entrada",
    "banco_administradora",
    "prazo_compra",
    "interesse_agendamento",
)


def _is_filled(c: Collected, field: str) -> bool:
    """True se o campo está preenchido (ou não-aplicável = tratado como preenchido)."""
    if field.startswith("troca_completa."):
        sub = field.split(".", 1)[1]
        if not _tem_troca(c):
            return True  # não-aplicável → pula
        t = c.troca_completa
        if t is None:
            return False
        if sub == "metodo_restante":
            # Opcional: só exigido se a troca não cobre tudo. Não bloqueia funil.
            return True
        val = getattr(t, sub, None)
        return val is not None and val != ""

    if field.startswith("financiamento."):
        sub = field.split(".", 1)[1]
        if c.forma_pagamento != "financiamento":
            return True  # não-aplicável
        fin = c.financiamento
        if fin is None:
            return False
        if sub == "entrada_status":
            return fin.entrada_status not in (None, "nao_informado")
        if sub == "valor_entrada":
            # Só exigido quando tem entrada.
            if fin.entrada_status != "sim":
                return True
            return bool(fin.valor_entrada)
        return True

    if field == "banco_administradora":
        if c.forma_pagamento != "carta_credito":
            return True
        return bool(c.banco_administradora)

    if field == "veiculo_interesse_confirmado":
        return c.veiculo_interesse_confirmado is True

    if field == "intencao":
        return c.intencao is not None

    if field == "interesse_agendamento":
        return c.interesse_agendamento is not None

    val = getattr(c, field, None)
    if val is None or val == "":
        return False
    return True


def compute_missing(c: Collected) -> list[str]:
    """missing[] AO VIVO do collected real. Substitui update.missing do LLM."""
    return [f for f in PRIORITY_FUNNEL if not _is_filled(c, f)]


def _was_asked_recently(state: SessionState, field: str, *, window: int = 2) -> int:
    recent = state.last_asked_fields[-window:] if state.last_asked_fields else []
    return sum(1 for f in recent if f == field)


def plan_next_question(
    *,
    state: SessionState,
    update: StateUpdate,
    history: list[dict] | None = None,
) -> NextQuestion:
    """Decide a próxima pergunta DEPOIS do merge (state já tem update aplicado)."""
    # 1. Terminal -> sem pergunta
    if update.terminal_reason or state.terminal_reason:
        return NextQuestion(
            field=None, intent="nenhum", canonical_text="", skip_funnel_reason="terminal"
        )

    # 2. Dúvida operacional: cai no cálculo normal de missing (NICK responde a
    #    dúvida via FAQ E avança 1 campo do funil no mesmo turno).

    # 3. Apresentação em andamento -> pergunta de FOCO, não funil.
    topics = set(update.topics or [])
    if update.intent_secundario:
        topics.add(update.intent_secundario)
    if "ver_outros_carros" in topics or update.intent == "apresentar":
        return NextQuestion(
            field=None, intent="foco",
            canonical_text="Algum desses chamou sua atenção?",
            skip_funnel_reason="apresentação ativa",
        )

    # 3b. Apresentação iminente da origem do CRM (veículo de interesse pré-fill).
    if (
        state.veiculo_origem
        and not state.origem_apresentada
        and not state.collected.veiculo_interesse_confirmado
    ):
        return NextQuestion(
            field=None, intent="foco",
            canonical_text="Esse te interessou?",
            skip_funnel_reason="apresentação iminente da origem do CRM",
        )

    # 4. Gate de agendamento.
    quer_agendar = (
        state.collected.interesse_agendamento is True
        or update.intent == "agendamento"
        or "agendamento" in topics
    )
    has_single_focus = (
        bool(state.last_card_external_id) or len(state.vehicles_shown or []) == 1
    )
    focus_ok = state.collected.veiculo_interesse_confirmado is True or has_single_focus
    if quer_agendar and focus_ok:
        return NextQuestion(
            field=None, intent="agendamento",
            canonical_text="Qual horário fica melhor pra você?",
            skip_funnel_reason="agendamento",
        )

    # 5. Funil — primeiro missing não perguntado 2x sem resposta.
    missing = compute_missing(state.collected)
    if not missing:
        return NextQuestion(
            field="interesse_agendamento", intent="funil",
            canonical_text=CANONICAL_QUESTIONS["interesse_agendamento"],
        )

    chosen = None
    for f in missing:
        if _was_asked_recently(state, f, window=2) >= 2:
            continue
        chosen = f
        break
    if chosen is None:
        chosen = missing[0]

    return NextQuestion(
        field=chosen, intent="funil",
        canonical_text=CANONICAL_QUESTIONS.get(chosen, "Me passa essa informação?"),
    )


def push_asked_field(state: SessionState, field: str | None, *, window: int = 5) -> None:
    """Registra campo perguntado neste turno. Rolling window."""
    if not field:
        return
    state.last_asked_fields = (state.last_asked_fields + [field])[-window:]
