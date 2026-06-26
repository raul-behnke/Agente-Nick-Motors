# CLAUDE.md

Guidance for Claude Code working in this repo.

## Product

WhatsApp pre-attendance agent ("NICK") for **Nick Motors Seminovos** (used-car
dealer, São Paulo/Vila Vera) on top of GoHighLevel (GHL). Single-tenant, PIT
auth. Portuguese (pt-BR). Migrated from GHL Custom Actions (GPT) to **Agno**.

Source of truth: [`PLAN.md`](./PLAN.md). Reference artifacts (old GHL framework,
prompts, templates, stock) under [`reference/`](./reference/).

## Origin

Clean fork of the **AMC `zoi_agent`** base (same domain, production-proven) +
review layer ported from **Veltron** (`guards.py`, `editor.py`). Package kept as
`zoi_agent` (ZOI = agency/platform; Nick = tenant, config-driven).

## Architecture — hybrid pipeline per inbound turn

```
Updater (LLM → StateUpdate) → question_planner (deterministic funnel)
→ dispatch (tom/ack/faq/slots/focus) → apply_guards (hard constraints)
→ Team Agno (NICK leader + EstoqueExpert) → BubbleSequence draft
→ run_editor (LLM 2nd pass, humanize, fact-boundary) → compose → shield(send)
```

Business rules = deterministic Python (planner, guards, orchestrator), NOT prompt.
LLM handles extraction (Updater), copy (NICK/EstoqueExpert), polish (Editor).

## Funnel (deterministic, PLAN §4.2)

nome → cidade → veiculo_interesse → [GATE: stock exposed] →
veiculo_interesse_confirmado → intencao(compra|troca) → [troca bloco] →
forma_pagamento(avista|financiamento|carta_credito|cartao) →
[financiamento: entrada] / [carta: banco] → prazo_compra → interesse_visita → agenda.

`faixa_preco` is NOT a funnel field — lives only in EstoqueExpert.

## GHL config (PLAN §5) — all live-tested

- Location `PU8y2Tjx1xqN728ysqR5`, tag gate `agente-ia`
- Stock CV `iouHAMP2IGqv98XrNVIe` (`{{custom_values.baseestoquejson}}`, ~28 veh, 3h refresh, has `imagens[]`)
- FAQ CV `e3aRXb9EPD1dPonHlUcI` (`{{custom_values.faq}}`, JSON `responses[]`, EMPTY — populate later)
- Calendar `OYoYdb3tAmRbJMQwgjei` (NICK MOTORS - VISITAS, 45min slots)
- Handoff workflow `1b741458-895e-42b6-9225-d085d14a6d9e`
- Saudação field `contact.saudaao_inicial`, veículo `contact.veculo_de_interesse`

## Key divergences from AMC

- Persona `NICK_INSTRUCTIONS` (male), fixed greeting verbatim.
- Payment = AMC-clean (troca is intention, not payment type).
- Photos adopted (stock has `imagens[]`).
- Review layer ADDED: `agent/guards.py` (price never quoted, anti-invention/ID,
  AI-identity; **endereço INVERTED** vs Veltron → FAQ/agenda not handoff) +
  `team/editor.py` (humanization 2nd pass).
- Models: `gpt-4.1` family (config per role in `settings`).

## Conventions

- Timezone `America/Sao_Paulo`; ISO8601 -03:00 for appointments.
- Lexical: "veículo" not "carro" in persona text.
- Tests: `pytest tests/`. Smokes hit live GHL via `.env` PIT (`scripts/smoke_*.py`).

## Status

Phase 0 (fork + scaffolding) in progress. Phases in PLAN.md §6.
