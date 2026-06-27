"""Camada editor — 2º passe de estilo sobre o rascunho do NICK (camada Veltron portada).

Reescreve in-place o `BubbleSequence` pra soar humano: corta papagaio/excesso/
tique de IA, garante pergunta de avanço no fim. NUNCA toca em fato (preço/spec/
km/ano/garantia) — só estilo. Fonte de verdade vem no payload.

Robustez: 1 retry → fallback pro rascunho original (nunca trava o turno).
Telemetria: `component="editor"` → cai no usage_sink (tokens+custo).
"""
from __future__ import annotations

import json
import time
from typing import Any

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from zoi_agent import usage as usage_sink
from zoi_agent.config import settings
from zoi_agent.logging import get_logger
from zoi_agent.team.schemas import BubbleSequence

log = get_logger(__name__)

_EDITOR_TIMEOUT_S = 30.0

EDITOR_INSTRUCTIONS = """\
Você é o EDITOR de estilo do pré-atendimento Nick Motors (não fala com o lead).
Recebe um RASCUNHO de resposta e reescreve pra soar como uma pessoa de verdade no
WhatsApp — um atendente brasileiro gente boa, consultivo, que manja de seminovos.

SEU TRABALHO: melhorar o ESTILO. Devolve um BubbleSequence polido (abertura
opcional, bolhas_extras opcionais, fechamento com a pergunta de avanço).

CORTE (tiques de IA / papagaio) — SEJA AGRESSIVO:
- 🚨 ABERTURA DE ELOGIO/RECONHECIMENTO EM TURNO DE FUNIL: se a `abertura` do
  rascunho é elogio/eco sobre uma resposta rotineira do lead (cidade, nome, forma
  de pagamento, 'comprar', 'sem entrada', sim/não) — ex: "Legal, São Paulo...",
  "Essa BMW chama atenção mesmo", "Ótimo saber que...", "Bacana ver que...",
  "Legal saber que..." — REMOVA a abertura (deixe None) e mantenha SÓ o
  fechamento (a pergunta). NÃO reformule o elogio; ELIMINE.
- ECO DA FALA DO LEAD: nunca repita de volta o que o lead disse ("você é de SP!",
  "gostou da BMW!"). O lead lembra. Corte.
- REPETIÇÃO ENTRE TURNOS: se `historico_recente` já disse um dado/pitch, NÃO repita.
- BORDÃO ENLATADO / RITUAL: corte "{ÂNCORA}, {CAMPO} então.", "Anotei aqui.",
  "Entendido.", "Fico à disposição", "Como posso te ajudar", "Que bom!", "Show!".
- EXCESSO: cordialidade na medida; no máx 1 emoji (quase nunca); SEM âncora de elogio.
- Acknowledgment/rapport SÓ sobrevive quando o lead revelou contexto PESSOAL real
  (motivo de compra, primeiro carro) — e no máximo 1 vez na conversa. Em resposta
  de funil rotineira, a abertura DEVE sumir.

MANTENHA / GARANTA:
- ESQUELETO: [reconhecimento empático só se agrega] → [valor/resposta] → [UMA
  pergunta que avança a qualificação]. Em resposta transacional, NÃO force rapport.
- 🚨 FECHAMENTO = `pergunta_alvo` (quando vier no payload). É a ÚNICA pergunta do
  turno: a próxima do funil. Vista de tom, NÃO mude o tópico, NÃO adicione
  segunda pergunta. PROIBIDO pergunta aberta/exploratória ('tem alguma dúvida
  sobre o {veículo}?', 'o que achou?', 'quer saber mais detalhes?', 'tem algum
  item específico?', 'procura outro modelo?', 'quer ver mais opções?', qualquer
  'ou' que ofereça caminhos). Se o rascunho tem uma dessas, SUBSTITUA pelo
  `pergunta_alvo`. Se `pergunta_alvo` veio vazio, mantenha o fechamento do
  rascunho (turno terminal/informativo).
- PERGUNTA DE AVANÇO no fechamento, SEMPRE (puxa o lead de volta pro funil).
- Léxico "veículo" (não "carro", salvo se o lead usou).
- Gramática e pontuação corretas. Hedging leve ok ("acho que", "geralmente").
- No máximo 3 bolhas curtas. Pode mesclar/dividir/reordenar bolhas do rascunho.

FRONTEIRA DE FATO (inquebrável):
- NUNCA invente ou altere número, preço, km, ano, spec, garantia, prazo, endereço,
  pagamento. Use SÓ o que está em `modelo_em_foco`, `faq_yaml` e nos cards. Se o
  rascunho trouxe um número que NÃO está nessas fontes, REMOVA-O (não substitua).
- A IA NUNCA cota/negocia preço de negociação. Preço de anúncio do card/estoque pode.
- Se `already_greeted=true`, NÃO escreva saudação ("Olá/Oi/Bom dia/Bem-vindo").
- Se `has_cards=false`, é PROIBIDO prometer veículos/fotos ("separei opções", "olha essas").
- Se `identity_text` veio preenchido, INCORPORE essa frase (lead questionou se é IA).
- Se o rascunho já está bom, faça poucos ou nenhum ajuste — não estrague texto bom.

Responda no schema BubbleSequence (abertura opcional, bolhas_extras, fechamento).
"""


def _build_editor_agent() -> Agent:
    return Agent(
        name="EditorNick",
        model=OpenAIChat(id=settings.openai_model_editor, api_key=settings.openai_api_key),
        description="Editor de estilo (2º passe). Humaniza sem tocar em fato.",
        instructions=[EDITOR_INSTRUCTIONS],
        output_schema=BubbleSequence,
        markdown=False,
        telemetry=False,
    )


def _record_usage(result: Any, *, latency_ms: int | None) -> None:
    metrics = getattr(result, "metrics", None)
    if metrics is None:
        return
    try:
        def _i(v: Any) -> int:
            if isinstance(v, (list, tuple)):
                return int(sum(x for x in v if isinstance(x, (int, float))))
            return int(v) if isinstance(v, (int, float)) else 0
        ti, to, tt = _i(getattr(metrics, "input_tokens", None)), _i(getattr(metrics, "output_tokens", None)), _i(getattr(metrics, "total_tokens", None))
        if ti or to or tt:
            usage_sink.record(
                component="editor", model=settings.openai_model_editor,
                tokens_input=ti, tokens_output=to, tokens_total=tt,
                reasoning_tokens=None, latency_ms=latency_ms,
            )
    except Exception as e:
        log.warning("editor_usage_extract_failed", err=str(e))


async def run_editor(
    *,
    rascunho: BubbleSequence,
    last_user_text: str = "",
    historico_recente: str = "",
    modelo_em_foco: dict[str, Any] | None = None,
    has_cards: bool = False,
    faq_yaml: str = "",
    sentiment: str = "neutro",
    already_greeted: bool = True,
    identity_text: str | None = None,
    pergunta_alvo: str | None = None,
) -> BubbleSequence:
    """Reescreve o rascunho pra soar humano. 1 retry → fallback pro rascunho."""
    payload = {
        "rascunho": rascunho.model_dump(exclude={"inventory_decision"}),
        "last_user_text": last_user_text,
        "historico_recente": historico_recente,
        "modelo_em_foco": modelo_em_foco,
        "has_cards": has_cards,
        "faq_yaml": faq_yaml,
        "sentiment": sentiment,
        "already_greeted": already_greeted,
        "identity_text": identity_text,
        "pergunta_alvo": pergunta_alvo,
    }
    user = json.dumps(payload, ensure_ascii=False, default=str)

    last_exc: Exception | None = None
    for _ in range(2):
        try:
            agent = _build_editor_agent()
            _t0 = time.perf_counter()
            result = await agent.arun(input=user)
            _record_usage(result, latency_ms=int((time.perf_counter() - _t0) * 1000))
            content = getattr(result, "content", None)
            if isinstance(content, BubbleSequence):
                # editor não decide estoque: preserva a decisão do rascunho original
                content.inventory_decision = rascunho.inventory_decision
                return content
            log.warning("editor_output_not_schema", type=type(content).__name__)
        except Exception as e:  # degrada gracioso, nunca trava o turno
            last_exc = e
    log.error("editor_failed_fallback_rascunho", error=str(last_exc) if last_exc else "no_schema")
    return rascunho
