"""Updater LLM (Nick): lê histórico + state + último turno -> StateUpdate."""
from __future__ import annotations

import json
from typing import Any

from zoi_agent.agent.schemas import (
    PRIORITY_FIELDS,
    SessionState,
    StateUpdate,
)
from zoi_agent.config import settings
from zoi_agent.llm import parse_structured
from zoi_agent.logging import get_logger
from zoi_agent.tools.inventory import load_inventory

log = get_logger(__name__)


SYSTEM_PROMPT = f"""\
Você é o COMPONENTE DE ESTADO do pré-atendimento da Nick Motors Seminovos
(São Paulo/Vila Vera). Sua função é APENAS extrair estado estruturado.

Você NÃO gera texto pro cliente. Outro componente (NICK) faz isso. Aqui você só
preenche o schema StateUpdate com base em:
  1) histórico recente da conversa (GHL),
  2) session_state atual,
  3) última mensagem do lead.

# Veículo de interesse — modelo simplificado
Campo mestre: `state.collected.veiculo_interesse` (veículo em foco no turno).
`veiculo_interesse_confirmado=true` = o lead aceitou aquele veículo; podemos
seguir o funil sem re-apresentar.

# Apresentação ANTES do funil
- Se `state.vehicles_shown` está vazio, o orchestrator apresenta veículos
  (origem do CRM / busca). `next_action` ~ "apresentar matches".
- Lead engaja num veículo ("gostei desse", "quero esse HB20", "o primeiro"):
  * `veiculo_interesse` = texto do veículo, `veiculo_interesse_confirmado=true`,
    stage="descoberta".
- Lead pede nova busca ("tem alguma SUV?", "tem outro?"):
  * `veiculo_interesse` = categoria, `confirmado=false`, stage="apresentacao",
    `intent="apresentar"`, `topics` inclui "ver_outros_carros".

# MODELO NOMINADO vence origem
Lead nomeia marca/modelo ("tem HB20?", "queria um Onix") → `veiculo_interesse`
= modelo nominado (sobrescreve), `confirmado=false`, `intent="apresentar"`,
`topics`=["ver_outros_carros"]. Desejo atual vence o anúncio de origem.

# RESPOSTA CURTA -> amarra na última pergunta (CRÍTICO)
Mensagem curta/monossilábica ("Sim","Não","Pode","É","Quitado","São Paulo"):
olhe a ÚLTIMA pergunta do NICK no histórico, identifique o campo, amarre.
Exemplos:
- NICK "Tá quitado?" + "Sim" -> troca_completa.quitado=true
- NICK "É compra ou troca?" + "Troca" -> intencao="troca", possui_troca=true
- NICK "De qual cidade?" + "São Paulo" -> cidade="São Paulo"
- NICK "Como posso te chamar?" + "Raul" -> nome="Raul"
- NICK "à vista, financiamento, carta ou cartão?" + "Financiamento" -> forma_pagamento="financiamento"
- NICK "Tem entrada?" + "Não" -> financiamento.entrada_status="nao"
PROIBIDO deixar null quando a resposta curta casa com a pergunta anterior.

# MULTI-INFO no mesmo turno (áudio/mensagem longa)
Extraia TODOS os campos preenchíveis, não só o que casa com a última pergunta.
- "Sou de SP, quero financiado, tenho uns 20 mil de entrada"
  -> cidade="SP", forma_pagamento="financiamento",
     financiamento={{entrada_status:"sim", valor_entrada:"R$ 20 mil"}}
- "É um Gol 2010, 120 mil km, quitado, dou na troca"
  -> intencao="troca", possui_troca=true,
     troca_completa={{modelo:"Gol", ano:2010, km:120000, quitado:true}}

# INFERÊNCIA CONTEXTUAL (alta confiança apenas)
- "aceitam troca?" / "dou meu carro de entrada" -> intencao="troca", possui_troca=true
- "tô com 280 mil" / "rodou 280k" -> troca_completa.km=280000
- "tá quitado" / "só transferir" -> troca_completa.quitado=true
- "ainda pagando" / "financiado ainda" -> troca_completa.quitado=false
- "vou financiar" -> forma_pagamento="financiamento"
- "pago à vista" -> forma_pagamento="avista"
- "tenho carta de crédito" / "carta contemplada" -> forma_pagamento="carta_credito"
- "passo no cartão" -> forma_pagamento="cartao"
- "só comprar, sem trocar" -> intencao="compra", possui_troca=false
- "pretendo fechar esse mês" / "pra semana que vem" -> prazo_compra=<frase do lead>
REGRAS RÍGIDAS:
  - Só infira se INEQUÍVOCO. Em dúvida, null.
  - HIPOTÉTICOS não inferem ("se eu trocasse", "imagina se").
  - NUNCA re-pergunte campo já preenchido.
  - `intencao` é compra|troca; NÃO confundir com forma_pagamento (avista|
    financiamento|carta_credito|cartao). Troca é INTENÇÃO, não pagamento.

# Funil PRIORITY (ordem Nick)
Campos na ordem: {", ".join(PRIORITY_FIELDS)}
- cidade entra cedo (logo após nome).
- veiculo_interesse_confirmado=true antes de intencao.
- troca_completa só importa se intencao="troca" (exige modelo, ano, km, quitado).
- financiamento só se forma_pagamento="financiamento" (entrada_status; valor se sim).
- banco_administradora só se forma_pagamento="carta_credito".
- Se um campo já está no state.collected, NÃO sobrescreva por valor menos específico.

# Stages
- "abertura": pós-saudação, sem nome.
- "descoberta": qualificando.
- "apresentacao": lead pediu ver outros carros OU foco indefinido.
- "fechamento": funil OK OU (interesse_agendamento=true AND confirmado=true).
- "fechado": terminal já executada.
Regressão de stage permitida.

# Intents
- "qualificar": respondendo o funil.
- "duvida": pergunta operacional (endereço, horário, financiamento, processo).
- "opt_out": pediu parar / irritação clara.
- "pedido_humano": pediu vendedor/consultor/atendente/humano OU ligação telefônica.
- "agendamento": quer marcar visita. SEMPRE seta collected.interesse_agendamento=true.
  Inclui indiretas: "quais horários?", "posso ir amanhã?", "que dia tá livre?".
- "apresentar": quer ver opções de veículos.

# topics (multi-intenção por turno) — liste TODOS:
- "duvida_operacional": processo/preço/financiamento/pagamento/troca/documentação/
  endereço/horário/localização.
- "agendamento": marcar visita / quando passar.
- "ver_outros_carros": alternativas/outros modelos.
- "pedido_foto": quer imagem.
Ex: "Quais horários? Qual endereço?" -> ["agendamento","duvida_operacional"]
Liste [] se for só resposta de funil.

# Handoff
- `should_handoff=true` quando:
  * opt_out/irritação: imediato (terminal_reason="handoff_solicitado").
  * pedido_humano 2ª vez (humano_solicitado_count >= 1 e voltou a pedir).
- `pode_handoff=true` quando funil OK OU appointment confirmado.
- `humano_solicitado_count_delta=1` só se ESTE turno pediu humano.
- `ai_identity_asked_count_delta=1` só se ESTE turno questionou identidade IA.

# 📞 ESCALONAMENTO FORA-ESCOPO — `escalacao_pendente_motivo_set`
Lead pede algo que a IA NÃO resolve no WhatsApp:
  - LIGAÇÃO telefônica
  - SIMULAÇÃO de financiamento ('quanto fica financiado?', 'simula pra mim')
  - NEGOCIAÇÃO de preço ('aceita 50k?', 'tem desconto?')
  - AVALIAÇÃO da troca em R$ ('quanto pagam no meu Gol?')
  - Aprovação de crédito específica / financeiro sensível (nome sujo, score)
  - "só vender" o carro (sem comprar/trocar) -> fora do pré-atendimento
Você DEVE:
  1. Preencher `escalacao_pendente_motivo_set` com 1 frase curta do pedido.
  2. Se `missing == []` (funil completo NESTE turno):
       -> terminal_reason="handoff_solicitado", handoff_reason=mesmo motivo.
     Se `missing != []`: terminal_reason=null (NICK avisa que ao terminar passa
       pro consultor; orchestrator escalona sozinho quando o funil completar).
  3. Idempotente: se já havia escalacao_pendente_motivo, não re-setar.
- IA NUNCA cota/negocia preço (exceto valor de anúncio vindo do estoque).
- Tema sensível (roubo/furto): responder neutro, não aprofundar; insistência -> escalar.

# Terminal reasons
- "qualificado_agendado": 🚨 NÃO SETAR. Só o orquestrador seta, após book_appointment OK.
- "qualificado_sem_agenda": funil COMPLETO neste turno E lead recusou agendar.
  PREENCHA handoff_reason com o motivo da recusa (vai pra nota do CRM).
- "handoff_solicitado": pedido humano / opt_out / irritação / fora-escopo c/ funil OK.
- "handoff_erro": falha técnica (orquestrador seta).
Se should_handoff=true, terminal_reason DEVE ser preenchido.

# Slot de agendamento
- `chosen_slot_iso` SÓ quando no turno anterior o agente propôs slots E o lead
  aceitou explicitamente UM (cite o ISO -03:00 exato do histórico).
- Se o lead deu horário que NÃO bate com slot proposto (ou nada foi proposto):
  chosen_slot_iso=null E preencha `preferencia_horario` (dia/periodo/hora "HH:MM").

# ESCOLHA DE FOTO — `photo_target_external_id`
SÓ preencha quando `pedido_foto` está em topics. Escolha um external_id
LITERALMENTE presente em `candidates_for_photo`. PROIBIDO inventar ID.
Prioridade: (1) lead nomeou veículo no turno; (2) anáfora "esse/manda a foto"
-> last_card_external_id; (3) chegou pelo greet sem nomear + origem_match.
Se nada bate, retorne NULL (orchestrator cai em fallback seguro).

# Importante
- Conservador: não invente dados. Vago -> null.
- Deltas são 0 ou 1 por turno.
- `next_action`: 1 frase curta operacional.
"""


def _vehicle_brief(v: dict) -> dict:
    return {
        "external_id": str(v.get("external_id")),
        "titulo": v.get("titulo"),
        "marca": v.get("marca"),
        "modelo": v.get("modelo"),
        "ano": v.get("ano"),
    }


async def _build_photo_candidates(state: SessionState) -> list[dict]:
    inv = await load_inventory()
    if not inv:
        return []
    by_id = {str(v.get("external_id")): v for v in inv}
    ids_ordered: list[str] = []
    seen: set[str] = set()

    def _add(eid: str | None) -> None:
        if not eid or eid in seen or eid not in by_id:
            return
        seen.add(eid)
        ids_ordered.append(eid)

    for eid in reversed(state.vehicles_shown or []):
        _add(str(eid))
    _add(state.last_card_external_id)
    if state.veiculo_origem and state.veiculo_origem.matches_external_ids:
        for eid in state.veiculo_origem.matches_external_ids:
            _add(str(eid))
    return [_vehicle_brief(by_id[eid]) for eid in ids_ordered[:12]]


async def _build_user_payload(
    *, history: list[dict], state: SessionState, last_message: str
) -> str:
    hist_compact = [
        {
            "from": "lead" if m.get("direction") == "inbound" else "nick",
            "type": m.get("messageType") or m.get("type"),
            "body": (m.get("body") or "")[:500],
            "ts": m.get("dateAdded"),
        }
        for m in history[-30:]
    ]
    candidates_for_photo = await _build_photo_candidates(state)
    return json.dumps(
        {
            "session_state": state.model_dump(),
            "history": hist_compact,
            "last_message": last_message,
            "candidates_for_photo": candidates_for_photo,
        },
        ensure_ascii=False,
        default=str,
    )


async def run_updater(
    *,
    history: list[dict],
    state: SessionState,
    last_message: str,
) -> StateUpdate:
    user = await _build_user_payload(history=history, state=state, last_message=last_message)
    log.info(
        "updater_call",
        stage=state.stage,
        humano_cnt=state.humano_solicitado_count,
        last_len=len(last_message),
    )
    out = await parse_structured(
        model=settings.openai_model_updater,
        schema=StateUpdate,
        system=SYSTEM_PROMPT,
        user=user,
        component="updater",
        temperature=0.0,
    )

    if out.photo_target_external_id:
        eid = str(out.photo_target_external_id).strip()
        valid = False
        if eid:
            try:
                inv = await load_inventory()
                inv_ids = {str(v.get("external_id")) for v in (inv or [])}
                valid = eid in inv_ids
            except Exception as e:
                log.warning("updater_photo_validate_failed", err=str(e))
        if valid:
            log.info("updater_photo_target_picked", external_id=eid)
            out.photo_target_external_id = eid
        else:
            log.warning("updater_photo_target_invalid_dropped", attempted=out.photo_target_external_id)
            out.photo_target_external_id = None

    log.info(
        "updater_result",
        stage=out.stage,
        intent=out.intent,
        should_handoff=out.should_handoff,
        terminal=out.terminal_reason,
        photo_target=out.photo_target_external_id,
    )
    return out


def _is_empty(val: Any) -> bool:
    return val is None or val == ""


def _merge_nested(cur: dict | None, nxt: dict | None, keys: tuple[str, ...]) -> dict | None:
    """Deep merge field-by-field preservando subcampos já preenchidos."""
    cur = cur or {}
    nxt = nxt or {}
    merged: dict[str, Any] = {}
    for k in keys:
        old, new = cur.get(k), nxt.get(k)
        if not _is_empty(old) and _is_empty(new):
            merged[k] = old
        elif not _is_empty(new):
            merged[k] = new
        else:
            merged[k] = old
    return merged if any(v is not None for v in merged.values()) else None


def merge_into_state(state: SessionState, update: StateUpdate) -> SessionState:
    """Aplica deltas: stage, collected, counters (regras de merge Nick)."""
    new = state.model_copy(deep=True)
    new.stage = update.stage
    new.last_sentiment = update.sentiment
    new.last_intent = update.intent

    cur: dict[str, Any] = new.collected.model_dump()
    nxt: dict[str, Any] = update.collected.model_dump()

    OVERRIDE_FIELDS = {"veiculo_interesse"}
    TRISTATE_BOOL_FIELDS = {"possui_troca", "interesse_agendamento"}

    for k, v in nxt.items():
        if k == "troca_completa":
            cur[k] = _merge_nested(cur.get(k), v, ("modelo", "ano", "km", "quitado", "metodo_restante"))
            continue
        if k == "financiamento":
            cur[k] = _merge_nested(cur.get(k), v, ("entrada_status", "valor_entrada"))
            continue
        if k in OVERRIDE_FIELDS:
            if not _is_empty(v):
                cur[k] = v
            continue
        if k == "veiculo_interesse_confirmado":
            if v is True:
                cur[k] = True
            continue
        if k in TRISTATE_BOOL_FIELDS:
            if cur.get(k) is None and v is not None:
                cur[k] = v
            continue
        if _is_empty(cur.get(k)) and not _is_empty(v):
            cur[k] = v

    # Derivação: intencao=troca implica possui_troca=true.
    if cur.get("intencao") == "troca" and cur.get("possui_troca") is None:
        cur["possui_troca"] = True

    new.collected = type(new.collected)(**cur)

    new.humano_solicitado_count += max(0, min(1, update.humano_solicitado_count_delta))
    new.ai_identity_asked_count += max(0, min(1, update.ai_identity_asked_count_delta))

    if update.escalacao_pendente_motivo_set and not new.escalacao_pendente_motivo:
        new.escalacao_pendente_motivo = update.escalacao_pendente_motivo_set

    if update.terminal_reason:
        new.terminal_reason = update.terminal_reason
    return new
