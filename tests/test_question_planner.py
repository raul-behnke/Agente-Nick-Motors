"""Testes do funil determinístico Nick (PLAN §4.2) — schemas + question_planner."""
from __future__ import annotations

from zoi_agent.agent.schemas import (
    Collected,
    Financiamento,
    SessionState,
    StateUpdate,
    TrocaInfo,
)
from zoi_agent.agent.schemas import compute_missing as schema_missing
from zoi_agent.agent.question_planner import (
    PRIORITY_FUNNEL,
    compute_missing,
    plan_next_question,
    push_asked_field,
)


def _update(**kw) -> StateUpdate:
    base = dict(
        stage="descoberta", collected=Collected(), missing=[], next_action="x",
        sentiment="neutro", intent="qualificar",
    )
    base.update(kw)
    return StateUpdate(**base)


def _plan(c: Collected, **upd) -> str | None:
    st = SessionState(collected=c, stage="descoberta")
    nq = plan_next_question(state=st, update=_update(collected=c, **upd), history=[])
    return nq.field if nq.intent == "funil" else f"<{nq.intent}>"


# --- ordem do funil ---------------------------------------------------------

def test_funil_comeca_por_nome():
    assert _plan(Collected()) == "nome"


def test_cidade_vem_cedo_apos_nome():
    assert _plan(Collected(nome="Raul")) == "cidade"


def test_apos_cidade_vai_veiculo():
    assert _plan(Collected(nome="Raul", cidade="SP")) == "veiculo_interesse"


def test_confirmar_veiculo_antes_de_intencao():
    c = Collected(nome="Raul", cidade="SP", veiculo_interesse="HB20")
    assert _plan(c) == "veiculo_interesse_confirmado"
    c.veiculo_interesse_confirmado = True
    assert _plan(c) == "intencao"


# --- ramo troca -------------------------------------------------------------

def test_troca_abre_bloco_troca():
    c = Collected(nome="R", cidade="SP", veiculo_interesse="HB20",
                  veiculo_interesse_confirmado=True, intencao="troca")
    assert _plan(c) == "troca_completa.modelo"


def test_troca_progride_subcampos():
    c = Collected(nome="R", cidade="SP", veiculo_interesse="HB20",
                  veiculo_interesse_confirmado=True, intencao="troca",
                  possui_troca=True,
                  troca_completa=TrocaInfo(modelo="Gol", ano=2012))
    assert _plan(c) == "troca_completa.km"


def test_compra_pula_bloco_troca():
    c = Collected(nome="R", cidade="SP", veiculo_interesse="HB20",
                  veiculo_interesse_confirmado=True, intencao="compra")
    assert _plan(c) == "forma_pagamento"


# --- ramo pagamento ---------------------------------------------------------

def _base_pago(forma=None) -> Collected:
    return Collected(nome="R", cidade="SP", veiculo_interesse="HB20",
                     veiculo_interesse_confirmado=True, intencao="compra",
                     forma_pagamento=forma)


def test_financiamento_exige_entrada():
    c = _base_pago("financiamento")
    assert _plan(c) == "financiamento.entrada_status"


def test_financiamento_com_entrada_pede_valor():
    c = _base_pago("financiamento")
    c.financiamento = Financiamento(entrada_status="sim")
    assert _plan(c) == "financiamento.valor_entrada"


def test_financiamento_sem_entrada_pula_valor():
    c = _base_pago("financiamento")
    c.financiamento = Financiamento(entrada_status="nao")
    assert _plan(c) == "prazo_compra"


def test_carta_credito_exige_banco():
    c = _base_pago("carta_credito")
    assert _plan(c) == "banco_administradora"


def test_avista_pula_para_prazo():
    c = _base_pago("avista")
    assert _plan(c) == "prazo_compra"


def test_cartao_pula_para_prazo():
    c = _base_pago("cartao")
    assert _plan(c) == "prazo_compra"


# --- fechamento -------------------------------------------------------------

def test_funil_completo_pede_agendamento():
    c = _base_pago("avista")
    c.prazo_compra = "30 dias"
    assert _plan(c) == "interesse_agendamento"


def test_agendamento_gate_quando_quer_e_tem_foco():
    c = _base_pago("avista")
    c.prazo_compra = "30 dias"
    c.interesse_agendamento = True
    st = SessionState(collected=c, stage="fechamento", last_card_external_id="960913")
    nq = plan_next_question(state=st, update=_update(collected=c, intent="agendamento"), history=[])
    assert nq.intent == "agendamento"


# --- anti-loop --------------------------------------------------------------

def test_anti_loop_pula_campo_perguntado_2x():
    c = Collected(nome="R", cidade="SP")
    st = SessionState(collected=c, stage="descoberta")
    push_asked_field(st, "veiculo_interesse")
    push_asked_field(st, "veiculo_interesse")
    nq = plan_next_question(state=st, update=_update(collected=c), history=[])
    assert nq.field != "veiculo_interesse"


# --- coerência schema x planner --------------------------------------------

def test_schema_e_planner_concordam_em_vazio():
    c = Collected()
    assert schema_missing(c)[0] == "nome"
    assert compute_missing(c)[0] == "nome"


def test_priority_funnel_cobre_todos_canonical():
    from zoi_agent.agent.question_planner import CANONICAL_QUESTIONS
    for f in PRIORITY_FUNNEL:
        assert f in CANONICAL_QUESTIONS, f"falta canonical: {f}"
