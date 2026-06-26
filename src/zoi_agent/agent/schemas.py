"""Schemas de StateUpdate e session_state — funil Nick Motors (PLAN §4.2/§4.3).

Divergência da AMC: troca é INTENÇÃO (não forma de pagamento); forma_pagamento
ganha financiamento/carta_credito/cartao com sub-blocos condicionais; cidade
entra cedo (sequência Nick).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Stage = Literal["abertura", "descoberta", "apresentacao", "fechamento", "fechado"]
Sentiment = Literal["neutro", "positivo", "negativo", "irritado"]
Intent = Literal[
    "qualificar",
    "duvida",
    "opt_out",
    "pedido_humano",
    "agendamento",
    "apresentar",
]
IntentSecundario = Literal["duvida_operacional", "ver_outros_carros", "pedido_foto"] | None

Topic = Literal[
    "duvida_operacional",
    "agendamento",
    "ver_outros_carros",
    "pedido_foto",
]

Intencao = Literal["compra", "troca"]
FormaPagamento = Literal["avista", "financiamento", "carta_credito", "cartao"]


class TrocaInfo(BaseModel):
    modelo: str | None = None
    ano: int | None = None
    km: int | None = None
    quitado: bool | None = None
    metodo_restante: str | None = None  # como paga o saldo após a troca


class Financiamento(BaseModel):
    entrada_status: Literal["sim", "nao", "nao_informado"] | None = None
    valor_entrada: str | None = None


class Collected(BaseModel):
    nome: str | None = None
    cidade: str | None = None
    veiculo_interesse: str | None = None
    veiculo_interesse_confirmado: bool = False
    intencao: Intencao | None = None
    possui_troca: bool | None = None  # derivado de intencao=="troca"
    troca_completa: TrocaInfo | None = None
    forma_pagamento: FormaPagamento | None = None
    financiamento: Financiamento | None = None       # SE forma_pagamento=financiamento
    banco_administradora: str | None = None           # SE forma_pagamento=carta_credito
    prazo_compra: str | None = None
    interesse_agendamento: bool | None = None


class PreferenciaHorario(BaseModel):
    dia: str | None = None
    periodo: Literal["manha", "tarde", "noite"] | None = None
    hora: str | None = None  # "HH:MM" quando lead dá horário explícito


class StateUpdate(BaseModel):
    """Output estruturado do updater."""

    stage: Stage
    collected: Collected
    missing: list[str] = Field(
        description="Campos do funil ainda não preenchidos, em ordem PRIORITY"
    )
    next_action: str = Field(
        description="Próxima ação curta e operacional, ex: 'perguntar nome', 'apresentar matches'"
    )
    sentiment: Sentiment
    intent: Intent
    intent_secundario: IntentSecundario = None
    topics: list[Topic] = Field(
        default_factory=list,
        description=(
            "TODOS os tópicos identificados na mensagem do lead nesta rodada. "
            "Ex: 'Quais horários? Qual endereço?' -> ['agendamento','duvida_operacional']."
        ),
    )
    should_handoff: bool = False
    handoff_reason: str | None = None
    pode_handoff: bool = False
    terminal_reason: str | None = Field(
        default=None,
        description="Quando aplicável: qualificado_agendado, qualificado_sem_agenda, handoff_solicitado, handoff_erro",
    )
    preferencia_horario: PreferenciaHorario | None = None
    chosen_slot_iso: str | None = Field(
        default=None,
        description="ISO8601 com offset. SOMENTE quando o lead aceitou explicitamente um slot proposto no turno anterior.",
    )
    humano_solicitado_count_delta: int = Field(default=0, description="Incremento (0 ou 1)")
    escalacao_pendente_motivo_set: str | None = Field(
        default=None,
        description=(
            "Motivo de escalonamento pendente quando o lead pediu algo fora do escopo "
            "(ligação, simulação de financiamento, negociação de preço, avaliação de "
            "troca em R$). Preencha SOMENTE no turno em que o pedido apareceu."
        ),
    )
    ai_identity_asked_count_delta: int = Field(default=0, description="Incremento (0 ou 1)")
    photo_target_external_id: str | None = Field(
        default=None,
        description=(
            "Quando pedido_foto: external_id do veículo cujas fotos enviar, ESCOLHIDO "
            "estritamente de candidates_for_photo. NULL se não for pedido_foto ou alvo ambíguo. "
            "PROIBIDO inventar ID."
        ),
    )


class VeiculoOrigem(BaseModel):
    texto: str
    matches_external_ids: list[str] = Field(default_factory=list)


class SessionState(BaseModel):
    """Shape persistido em session_state JSONB."""

    stage: Stage = "abertura"
    greeted: bool = False
    conversation_id: str | None = None
    veiculo_origem: VeiculoOrigem | None = None
    collected: Collected = Field(default_factory=Collected)
    vehicles_shown: list[str] = Field(default_factory=list)
    origem_apresentada: bool = False
    last_asked_fields: list[str] = Field(default_factory=list)
    last_card_external_id: str | None = None
    humano_solicitado_count: int = 0
    ai_identity_asked_count: int = 0
    last_sentiment: Sentiment = "neutro"
    last_intent: Intent = "qualificar"
    terminal_reason: str | None = None
    appointment: dict | None = None
    escalacao_pendente_motivo: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


# Ordem PRIORITY do funil Nick (PLAN §4.2). Condicionais resolvidos em compute_missing.
PRIORITY_FIELDS: tuple[str, ...] = (
    "nome",
    "cidade",
    "veiculo_interesse",
    "veiculo_interesse_confirmado",
    "intencao",
    "troca_completa",          # SE intencao=="troca"
    "forma_pagamento",
    "financiamento",            # SE forma_pagamento=="financiamento"
    "banco_administradora",     # SE forma_pagamento=="carta_credito"
    "prazo_compra",
    "interesse_agendamento",
)


def _tem_troca(c: Collected) -> bool:
    return c.intencao == "troca" or c.possui_troca is True


def compute_missing(c: Collected) -> list[str]:
    """Aplica ordem PRIORITY + condicionais Nick.

    - troca_completa só se intencao=="troca" (exige modelo, ano, km, quitado).
    - financiamento só se forma_pagamento=="financiamento" (exige entrada_status;
      valor_entrada só se entrada_status=="sim").
    - banco_administradora só se forma_pagamento=="carta_credito".
    """
    miss: list[str] = []
    d = c.model_dump()
    for f in PRIORITY_FIELDS:
        if f == "veiculo_interesse_confirmado":
            if not c.veiculo_interesse_confirmado:
                miss.append(f)
            continue
        if f == "troca_completa":
            if _tem_troca(c):
                t = c.troca_completa
                if not t or not all([t.modelo, t.ano, t.km, t.quitado is not None]):
                    miss.append(f)
            continue
        if f == "financiamento":
            if c.forma_pagamento == "financiamento":
                fin = c.financiamento
                if not fin or fin.entrada_status in (None, "nao_informado"):
                    miss.append(f)
                elif fin.entrada_status == "sim" and not fin.valor_entrada:
                    miss.append(f)
            continue
        if f == "banco_administradora":
            if c.forma_pagamento == "carta_credito" and not c.banco_administradora:
                miss.append(f)
            continue
        if f == "interesse_agendamento":
            if c.interesse_agendamento is None:
                miss.append(f)
            continue
        if d.get(f) in (None, ""):
            miss.append(f)
    return miss
