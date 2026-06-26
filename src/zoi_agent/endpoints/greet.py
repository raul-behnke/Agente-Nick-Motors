"""POST /sessions/{contactId}/greet — síncrono, idempotente. Saudação oficial Nick."""
from __future__ import annotations

import asyncio
import random

from fastapi import APIRouter, Depends, HTTPException, Path

from zoi_agent.agent.schemas import SessionState, VeiculoOrigem
from zoi_agent.config import settings
from zoi_agent.db import sessions as session_repo
from zoi_agent.db.events import emit_event
from zoi_agent.ghl import contacts as ghl_contacts
from zoi_agent.ghl import conversations as ghl_conv
from zoi_agent.logging import get_logger
from zoi_agent.security import require_secret

router = APIRouter()
log = get_logger(__name__)


# Saudação oficial Nick Motors (PLAN §4.1) — abertura fixa + 1ª pergunta do funil
# (nome). Personaliza pela presença do veículo de interesse pré-preenchido. 3 bolhas.
SAUD_B1 = "Oi! 😊"
SAUD_B2 = "Aqui é da Equipe do Pré-Atendimento da Nick Motors Seminovos."
SAUD_B3_SEM_VEICULO = "Pra começar, como posso te chamar?"
SAUD_B3_COM_VEICULO = "Vi seu interesse no {veiculo}! Pra começar, como posso te chamar?"


def _greeting_bubbles(veiculo: str | None = None) -> list[str]:
    if veiculo and veiculo.strip():
        b3 = SAUD_B3_COM_VEICULO.format(veiculo=veiculo.strip())
    else:
        b3 = SAUD_B3_SEM_VEICULO
    return [SAUD_B1, SAUD_B2, b3]


@router.post("/sessions/{contact_id}/greet", dependencies=[Depends(require_secret)])
async def greet(contact_id: str = Path(..., min_length=1)) -> dict:
    log.info("greet_start", contact_id=contact_id)

    # 1) state local
    state = await session_repo.load_or_new(contact_id)

    # 2) busca contato (custom fields: saudação + veículo de interesse)
    try:
        contact_resp = await ghl_contacts.get_contact(contact_id)
    except Exception as e:
        log.error("greet_contact_fetch_failed", err=str(e))
        raise HTTPException(status_code=502, detail="ghl contact fetch failed") from e

    saud_value = ghl_contacts.read_custom_field_value(
        contact_resp, settings.ghl_field_saudacao_prevendas
    )
    saud_sim = (saud_value or "").strip().lower() == "sim"

    # 3) idempotência
    if state.greeted or saud_sim:
        log.info(
            "greet_skipped_idempotent",
            contact_id=contact_id,
            state_greeted=state.greeted,
            saud_sim=saud_sim,
        )
        return {"status": "ok", "skipped": True, "reason": "already_greeted"}

    veiculo = ghl_contacts.read_custom_field_value(
        contact_resp, settings.ghl_field_veiculo_interesse
    )
    veiculo_str = (veiculo or "").strip() or None

    bubbles = _greeting_bubbles(veiculo_str)

    # 4) envia saudação oficial (síncrono — só 200 após todas as bolhas)
    try:
        for i, b in enumerate(bubbles):
            await ghl_conv.send_message(contact_id=contact_id, message=b, message_type="SMS")
            if i < len(bubbles) - 1:
                await asyncio.sleep(
                    random.uniform(settings.responder_sleep_min, settings.responder_sleep_max)
                )
    except Exception as e:
        log.error("greet_send_failed", err=str(e))
        raise HTTPException(status_code=502, detail="ghl send failed") from e

    # 5) marca custom field saudação = "sim"
    try:
        await ghl_contacts.update_custom_field(
            contact_id, settings.ghl_field_saudacao_prevendas, "sim"
        )
    except Exception as e:
        log.error("greet_mark_failed", err=str(e))

    # 6) persiste state. Veículo pré-fill -> origem p/ foco no 1º turno. A saudação
    # já perguntou o nome -> registra em last_asked_fields p/ o planner não repetir.
    new_state = SessionState(
        stage="abertura",
        greeted=True,
        veiculo_origem=VeiculoOrigem(texto=veiculo_str) if veiculo_str else None,
        last_asked_fields=["nome"],
    )
    try:
        await session_repo.save(contact_id, new_state)
    except Exception as e:
        log.error("greet_state_save_failed", err=str(e))

    await emit_event(
        event_type="CONVERSATION_STARTED",
        contact_id=contact_id,
        payload={"veiculo_origem": veiculo_str, "com_veiculo": bool(veiculo_str)},
    )

    log.info("greet_sent", contact_id=contact_id, com_veiculo=bool(veiculo_str), veiculo=veiculo_str)
    return {
        "status": "ok",
        "skipped": False,
        "bubbles": len(bubbles),
        "com_veiculo": bool(veiculo_str),
        "veiculo": veiculo_str,
    }
