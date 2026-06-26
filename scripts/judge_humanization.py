"""Robô-juiz da humanização (SOB DEMANDA — não roda no caminho do turno).

Pega rascunhos do NICK (problemáticos de propósito), roda o EDITOR pra obter a
revisão, e um JUIZ LLM pontua rascunho→revisão contra a rubrica (papagaio?
empatia? pergunta no fim? tique de IA? fidelidade de fato?).

Uso:
    .venv/bin/python scripts/judge_humanization.py            # cenários embutidos
    .venv/bin/python scripts/judge_humanization.py "rascunho livre aqui"

Requer .env com OPENAI_API_KEY.
"""
from __future__ import annotations

import asyncio
import sys

from pydantic import BaseModel, Field


class JudgeScore(BaseModel):
    sem_papagaio: int = Field(ge=0, le=10, description="0=papagueia, 10=sem eco/repetição")
    empatia: int = Field(ge=0, le=10)
    pergunta_qualificacao_no_fim: int = Field(ge=0, le=10)
    sem_tique_de_ia: int = Field(ge=0, le=10, description="cordial na medida, sem robô")
    fidelidade_de_fato: int = Field(ge=0, le=10, description="10=não inventou preço/spec/km")
    nota_geral: int = Field(ge=0, le=10)
    melhorias_aplicadas: list[str] = Field(default_factory=list)
    comentario: str = ""


JUDGE_SYSTEM = """\
Você é um AVALIADOR de qualidade conversacional do pré-atendimento da Nick Motors
(seminovos, WhatsApp). Recebe um RASCUNHO e a REVISÃO (depois do editor de estilo)
+ contexto. Pontue a REVISÃO de 0 a 10 por critério:
- sem_papagaio: não ecoa a fala do lead nem repete info já dita no histórico.
- empatia: acolhe/valida na medida, sem exagero forçado.
- pergunta_qualificacao_no_fim: termina puxando o lead pro funil.
- sem_tique_de_ia: cordial na medida, sem formal-robô, emoji/entusiasmo moderados.
- fidelidade_de_fato: NÃO inventou preço/km/ano/spec fora de modelo_em_foco/faq/cards.
Liste melhorias_aplicadas e um comentario curto. Responda no schema JudgeScore.
"""

SCENARIOS = [
    {
        "nome": "papagaio_eco",
        "last_user_text": "é pra trabalho mesmo, faço entregas",
        "historico_recente": "nick: compra direta ou troca?",
        "modelo_em_foco": None,
        "rascunho": {
            "abertura": "Ah, pra trabalho! Que legal que é pra trabalho com entregas!",
            "bolhas_extras": ["Entendi perfeitamente!"],
            "fechamento": "Você prefere à vista ou financiamento?",
        },
    },
    {
        "nome": "robo_formal",
        "last_user_text": "quanto custa o HB20?",
        "historico_recente": "",
        "modelo_em_foco": {"modelo": "HB20", "preco": 67900, "ano": 2020},
        "rascunho": {
            "abertura": "Olá! Como posso ajudá-lo hoje?",
            "bolhas_extras": ["Fico à disposição para esclarecer suas dúvidas. ✅✅✅"],
            "fechamento": "Você está pensando em adquirir um veículo?",
        },
    },
]


def _to_bubbles(seq) -> list[str]:
    out = []
    if seq.abertura:
        out.append(seq.abertura)
    out.extend(b for b in (seq.bolhas_extras or []) if b and b.strip())
    if seq.fechamento:
        out.append(seq.fechamento)
    return out


async def main() -> None:
    from zoi_agent import usage as usage_sink
    from zoi_agent.llm import parse_structured
    from zoi_agent.team import editor
    from zoi_agent.team.schemas import BubbleSequence

    livre = sys.argv[1] if len(sys.argv) > 1 else None
    cenarios = (
        [{"nome": "livre", "last_user_text": "", "historico_recente": "",
          "modelo_em_foco": None,
          "rascunho": {"abertura": livre, "bolhas_extras": [], "fechamento": ""}}]
        if livre
        else SCENARIOS
    )

    usage_sink.start_turn()
    for sc in cenarios:
        rascunho = BubbleSequence(**sc["rascunho"])
        revisao = await editor.run_editor(
            rascunho=rascunho,
            last_user_text=sc["last_user_text"],
            historico_recente=sc["historico_recente"],
            modelo_em_foco=sc["modelo_em_foco"],
        )
        judge_user = (
            f"CONTEXTO:\nlast_user_text: {sc['last_user_text']}\n"
            f"historico_recente: {sc['historico_recente']}\n"
            f"modelo_em_foco: {sc['modelo_em_foco']}\n\n"
            f"RASCUNHO:\n{rascunho.model_dump()}\n\nREVISÃO:\n{revisao.model_dump()}"
        )
        from zoi_agent.config import settings
        score = await parse_structured(
            model=settings.openai_model_editor, schema=JudgeScore,
            system=JUDGE_SYSTEM, user=judge_user, component="judge",
        )
        print(f"\n=== {sc['nome']} ===")
        print("RASCUNHO :", _to_bubbles(rascunho))
        print("REVISAO  :", _to_bubbles(revisao))
        print("NOTA     :", score.model_dump())

    tin = tout = 0
    for rec in usage_sink.drain():
        tin += rec.tokens_input or 0
        tout += rec.tokens_output or 0
        print(f"[tokens] {rec.component}: in={rec.tokens_input} out={rec.tokens_output}")
    print(f"\n[tokens TOTAL] in={tin} out={tout} soma={tin + tout}")


if __name__ == "__main__":
    asyncio.run(main())
