# PLAN — Agente Pré-Atendimento Nick Motors (Agno)

> **Status:** plano de migração aprovado (pós `/grill-me`).
> **Repo:** https://github.com/raul-behnke/Agente-Nick-Motors
> **Base:** fork limpo da AMC (`zoi_agent`) + camada de revisão portada do Veltron.
> **Fonte de verdade do produto.** Implementação segue as fases §6.

---

## 1. Intake (9 perguntas do arquiteto Agno)

| # | Pergunta | Resposta |
|---|---|---|
| 1 | **Goal** | Pré-atendimento automatizado WhatsApp: qualifica lead de seminovo da 1ª msg até agendar visita OU escalar pra consultor humano. NÃO negocia preço, NÃO fecha venda, NÃO emite proposta. |
| 2 | **Users** | Leads de revenda de seminovos (Nick Motors, São Paulo/Vila Vera, atende SP + Brasil) via WhatsApp. |
| 3 | **Channel** | WhatsApp (via GoHighLevel). **WhatsApp-first**; Instagram = fase 2. Type `SMS` no GHL. |
| 4 | **Integrations** | GHL (canal + custom values estoque/FAQ + conversations API + tag gate + workflows), GHL Calendar (agendamento), OpenAI (LLM + Whisper áudio), Postgres. |
| 5 | **Persisted data** | Postgres (`session_state` JSONB, Agno auto-schema) + eventos de telemetria/custo. Histórico canônico = GHL (fetch por turno). Transcrição de áudio = efêmera. |
| 6 | **Actions** | `search_inventory`, `get_vehicle_details`, `consultar_faq`, enviar fotos, `propose_slots`/`book_appointment` (GHL Calendar), `encaminhar_para_vendedor` (handoff + nota + workflow). |
| 7 | **Knowledge** | FAQ Nick (custom value `{{custom_values.faq}}` JSON, 69 Q/A — populado à parte). Estoque (custom value `{{custom_values.baseestoquejson}}`, 28 veículos, refresh 3h). |
| 8 | **Human handoff** | 4 terminais (ver §4.5) + `handoff_reason` discrimina setor. Workflow GHL `1b741458-895e-42b6-9225-d085d14a6d9e`. |
| 9 | **Success metrics** | `zoi_qualificados_total{com_agenda}`, `zoi_handoff_total{reason}`, custo USD/BRL por turno, latência por componente (Prometheus + Grafana). Eval: judge de humanização (portado do Veltron). |

---

## 2. Arquitetura — pipeline híbrido por turno

Decisão de orquestração: **híbrido determinístico + Agno Team** (não orquestração LLM pura).
O Maestro mega-prompt (3000 ln, regex/keyword) **morre** → vira código Python determinístico.

```
GHL Workflow ──POST──▶ /webhook/inbound (tag gate: agente-ia, HMAC ?secret=)
                                  │
                                  ▼
                    orchestrator.process_turn (preempção asyncio por contactId)
                                  │
        ┌─────────────────────────┼─────────────────────────────────────────┐
        ▼                                                                     │
  1. load session_state (Postgres)                                           │
  2. terminal? → ignora                                                       │
  3. fetch histórico GHL (limit 100) + Whisper se áudio                       │
  4. run_updater (LLM) → StateUpdate (extração: collected, intent, topics,    │
        sentiment, handoff flags)                                            │
  5. merge_into_state                                                         │
  6. plan_next_question (DETERMINÍSTICO — funil Nick §4.2)                    │
  7. dispatch determinístico (tom, ack, vehicle_in_focus, FAQ, slots)        │
  8. apply_guards (HARD CONSTRAINTS Nick §4.6 — preço, anti-invenção, IA-id)  │
  9. book_appointment (GHL Calendar) se slot escolhido                        │
 10. Team Agno: NICK (leader) + EstoqueExpert (member) → BubbleSequence rascunho│
 11. run_editor (LLM 2º passe — humaniza, fronteira-de-fato) → BubbleSequence │
 12. compose + _enforce_singular_question                                     │
 13. shield(send): fotos paralelo + bolhas sequenciais (imune a preempção)    │
 14. handle terminal (encaminhar_para_vendedor) + save state                  │
        └─────────────────────────────────────────────────────────────────────┘
```

Falha de updater/editor/team → catch → `terminal_reason=handoff_erro` + escala humano (fallback seguro).

### Escolha de primitivas (justificativa)
- **Team `coordinate`** (NICK leader + EstoqueExpert member): redação conversacional + especialista de estoque são responsabilidades genuinamente distintas. Leader tece bolhas; member decide veículos (`InventoryDecision`).
- **Código determinístico (não Workflow Agno)**: funil, anti-loop, gates, guards, escalonamento = regras de negócio → Python testável (`question_planner`, `guards`, `orchestrator`). Não vão pro prompt.
- **Editor (Agent LLM 2º passe)**: humanização de estilo com fronteira-de-fato. +1 LLM/turno (custo aceito).

---

## 3. Tabela de componentes

| Componente | Tipo | Responsabilidade | Origem |
|---|---|---|---|
| `orchestrator` | código | pipeline por turno, preempção, shield, telemetria | AMC (adaptar) |
| `updater` | Agent LLM | extrai `StateUpdate` (collected, intent, topics, sentiment, handoff) | AMC (reescrever schema Nick) |
| `question_planner` | código determinístico | próxima pergunta do funil Nick, anti-loop | AMC (reescrever funil) |
| `guards` | código determinístico | hard constraints Nick (preço, anti-invenção/ID, IA-id) | **Veltron (portar+adaptar)** |
| Team `NICK` | Team leader (Agno) | persona + tece `BubbleSequence` | AMC `patricia`→`NICK_INSTRUCTIONS` |
| `EstoqueExpert` | Team member (Agno) | decide veículos → `InventoryDecision` | AMC (reusar, ajustar schema estoque) |
| `editor` | Agent LLM | 2º passe humanização, fronteira-de-fato | **Veltron (portar)** |
| `tools/inventory` | tool | carrega estoque (custom value), `get_vehicle_details` | AMC (trocar ID + mapear schema) |
| `tools/photos` | código | resolve + envia fotos (≥2 imgs) | AMC (reusar) |
| `tools/faq` | tool | lê FAQ custom value JSON | AMC (YAML→JSON) |
| `tools/calendar` | tool | `propose_slots`/`book_appointment` GHL Calendar | AMC (reusar + calendar ID Nick) |
| `tools/handoff` | tool | nota + workflow GHL terminal | AMC (trocar workflow ID) |
| `audio/whisper` | código | transcreve voice note | AMC (reusar) |
| `ghl/*` | clients | conversations, contacts, custom_values, workflows | AMC (reusar + creds Nick) |
| `db/*` | persistência | Postgres sessions + eventos | AMC (reusar, instância isolada) |
| `endpoints/*` | FastAPI | greet, inbound, abandon, metrics | AMC (greet=saudação fixa Nick) |
| `metrics`/`usage`/`db.events` | telemetria | Prometheus + custo USD/BRL | AMC (reusar) |
| `judge_humanization` | eval | LLM judge de qualidade | **Veltron (portar)** |

---

## 4. Especificações Nick (divergências da AMC)

### 4.1 Persona — `NICK_INSTRUCTIONS`
Reescrita de `PATRICIA_INSTRUCTIONS`. "Nick", masculino, jovem-profissional, consultivo, WhatsApp-natural. Sem traço de marca específico por ora. Léxico: "veículo" (não "carro"). Evade ser IA (admite "atendente digital" na 2ª insistência — `ai_identity_asked_count >= 1`). Mantém estrutura `BubbleSequence` + multi-pergunta (`bolhas_extras` max 2) + delegação ao EstoqueExpert.

### 4.2 Funil determinístico (`PRIORITY_FUNNEL` Nick)
```
1.  nome
2.  cidade_regiao                 (sequência Nick — cedo, após nome)
3.  veiculo_interesse
4.  ►► GATE ESTOQUE: pesquisa + envia ficha/exposição ◄◄
5.  veiculo_interesse_confirmado
6.  intencao                      (compra | troca)
7.  [SE troca] troca_completa     (modelo, ano, km, quitado, metodo_restante)
8.  forma_pagamento               (avista | financiamento | carta_credito | cartao)
9.  [SE financiamento] entrada_status, valor_entrada
10. [SE carta_credito] banco_administradora
11. prazo_compra
12. interesse_visita → agendamento
```
`faixa_preco` NÃO é campo de funil → vive só no EstoqueExpert (sinal de busca).

### 4.3 Schema `Collected` (Nick)
```python
class TrocaInfo(BaseModel):
    modelo: str | None = None
    ano: int | None = None
    km: int | None = None
    quitado: bool | None = None
    metodo_restante: str | None = None   # como paga o saldo após troca

class Financiamento(BaseModel):
    entrada_status: Literal["sim","nao","nao_informado"] | None = None
    valor_entrada: str | None = None

class Collected(BaseModel):
    nome: str | None = None
    cidade: str | None = None
    veiculo_interesse: str | None = None
    veiculo_interesse_confirmado: bool = False
    intencao: Literal["compra","troca"] | None = None
    possui_troca: bool | None = None            # derivado de intencao=troca
    troca_completa: TrocaInfo | None = None
    forma_pagamento: Literal["avista","financiamento","carta_credito","cartao"] | None = None
    financiamento: Financiamento | None = None
    banco_administradora: str | None = None     # SE carta_credito
    prazo_compra: str | None = None
    interesse_agendamento: bool | None = None
```
`compute_missing` aplica `PRIORITY_FUNNEL` + condicionais: `troca_completa` só se `possui_troca`; `financiamento`/`banco_administradora` só conforme `forma_pagamento`.

### 4.4 Estoque
- Fonte: custom value GHL `iouHAMP2IGqv98XrNVIe` (`{{custom_values.baseestoquejson}}`), shape `{"vehicles":[...]}`, 28 veículos, refresh 3h (job externo). Cache 5min.
- Schema já AMC-compatível: `external_id, titulo, marca, modelo, versao, ano, preco, quilometragem, combustivel, cambio, carroceria, categoria, cor, descricao, opcionais, imagens[], status`. Filtra `status=active`.
- Busca: mini-LLM (EstoqueExpert recebe inventário no prompt, raciocina — padrão AMC).
- **GATE**: proibido avançar pra negociação sem estoque textualmente exposto ao lead (evidência na conversa, não só estado interno).

### 4.5 Fotos
Adotadas (padrão AMC). `imagens[]` pronto no schema (mediana 21 fotos; 23/28 com ≥2). Envio paralelo sob shield, só dispara com ≥2 imagens. Reusa `photos.py` direto.

### 4.6 Camada de revisão (portada do Veltron, adaptada)
**`agent/guards.py`** — hard constraints determinísticas Nick (dupla camada: prompt + código):
- **Preço**: IA nunca cota/negocia preço → suprime sempre. **Exceção**: valor-do-anúncio vindo do estoque é exibível. (Simplificado vs Veltron — sem perfil varejo/atacado.)
- **Anti-invenção / blindagem de ID**: `validate_inventory_ids` filtra `external_id` inexistente; degrada `mostrar_card_*` sem ID válido → `nao_mostrar`. `is_model_available` (status active).
- **Identidade IA**: evade → admite no limiar.
- **Endereço/visita** ⚠️ **INVERTIDO vs Veltron**: Veltron esconde endereço (→handoff). Nick: endereço/horário = resposta FAQ; visita = fluxo agendamento. NÃO força handoff.
- Não portar traços específicos Veltron (atacado, esconde-endereço, scooter).

**`team/editor.py`** — 2º passe LLM de estilo sobre `BubbleSequence`: humaniza, corta tique-de-IA/papagaio, **fronteira-de-fato inquebrável** (nunca inventa preço/spec — só estilo), 1 retry → fallback pro rascunho, telemetria `component="editor"`. +1 LLM/turno (aceito).

### 4.7 Escalonamento / terminais
4 terminais AMC + `handoff_reason` discrimina setor (não cria workflows por setor):
| Nick (origem) | Terminal AMC | handoff_reason |
|---|---|---|
| aceita visita → agenda | `qualificado_agendado` | — |
| qualificado, recusa visita | `qualificado_sem_agenda` | — |
| score≤3, "só vender" | `handoff_solicitado` | "atendente / só-vender" |
| financeiro sensível, RH, roubo insistente | `handoff_solicitado` | setor (string) |
| pediu simulação financiamento | `escalacao_pendente_motivo` → handoff | "simulação" |
| erro de pipeline | `handoff_erro` | exceção |

Escalonamentos "silenciosos" Nick = sem bolha de despedida ao cliente (tratar no compose terminal).

### 4.8 Agendamento
GHL Calendar nativo (padrão AMC): `propose_slots` (disponibilidade real), `find_exact_slot`, `book_appointment` (`appointmentStatus=confirmed`). Webhook `nick-booking` + Agendador LLM + `slots_visita_disponiveis` **morrem**. Pendente: **calendar ID GHL Nick**.

### 4.9 Modelos LLM
OpenAI, modelos mais novos (`gpt-4.1` família, configurável por papel via `settings`). 3 papéis: Updater, Team leader (NICK), EstoqueExpert + Editor. Whisper p/ áudio.

---

## 5. Config GHL (Nick) — IDs travados + pendências

| Item | Valor |
|---|---|
| LocationId | `PU8y2Tjx1xqN728ysqR5` |
| PIT token | (em `.env`, **rotacionar** — exposto no chat) |
| Custom value estoque | `iouHAMP2IGqv98XrNVIe` → `{{custom_values.baseestoquejson}}` |
| Custom value FAQ | `e3aRXb9EPD1dPonHlUcI` → `{{custom_values.faq}}` (vazio, popular 69 Q/A) |
| Tag gate | `agente-ia` |
| Workflow handoff | `1b741458-895e-42b6-9225-d085d14a6d9e` |
| Custom field saudação (idempotência) | `saudaçao inicial` |
| Workflows greet/inbound | já criados (ngrok testes → subdomínio deploy) |
| **Calendar ID GHL** | `OYoYdb3tAmRbJMQwgjei` ("NICK MOTORS - VISITAS", collective, slots 45min, 3 membros) |
| Custom field saudação (fieldKey real) | `contact.saudaao_inicial` (id `3YE5GCQG9b1fk0MdrAwS`, SINGLE_OPTIONS) |
| Pré-fill veículo interesse | `contact.veculo_de_interesse` (TEXT) |
| Pré-fill canal / interesse / flag estoque | `contact.canal_de_conversa_atual` · `contact.interesse` · `contact.autoconf_ok` |
| Pré-fill origem/nome | `source` (nativo) · `first_name` (nativo) |

---

## 6. Plano de implementação faseado

> **Progresso:** Fases 0–7 ✅ (código). Boot Docker/deploy real pendente de VPS+daemon.
> Suite: **148 testes verdes**. judge_humanization portado. Artefatos de deploy Nick prontos.

**Fase 0 — Scaffolding & rebase** ✅
- Fork limpo AMC → repo `Agente-Nick-Motors`, pacote `zoi_agent`, histórico AMC descartado.
- `.env` Nick (creds, IDs §5). Postgres isolado (docker-compose). Smoke `smoke_ghl.py` contra location Nick.

**Fase 1 — Schema & funil (núcleo determinístico)**
- Reescrever `agent/schemas.py`: `Collected` Nick (§4.3), `StateUpdate`, `PRIORITY_FIELDS`, `compute_missing` condicional.
- Reescrever `agent/question_planner.py`: `PRIORITY_FUNNEL` + `CANONICAL_QUESTIONS` Nick (§4.2).
- Testes unitários do funil (ordem, condicionais troca/financiamento/carta, anti-loop).

**Fase 2 — Updater & persona**
- Reescrever `agent/updater.py` (prompt extração Nick) → `StateUpdate`.
- `team/patricia.py` → `NICK_INSTRUCTIONS` (§4.1). `team/sdr_team.py` → `build_nick_team`.
- `EstoqueExpert`: ajustar mapeamento schema estoque Nick.
- Saudação fixa no `endpoints/greet.py` (texto verbatim §4.1, idempotência `saudaçao inicial`).

**Fase 3 — Tools & integrações**
- `tools/inventory.py`: trocar custom value ID + `_normalize_vehicle` p/ schema Nick.
- `tools/faq.py`: YAML→JSON (`responses[]`), custom value FAQ.
- `tools/calendar.py`: calendar ID Nick (quando disponível).
- `tools/handoff.py`: workflow ID Nick + mapeamento terminais §4.7.
- `tools/photos.py`: reusar (validar `imagens[]` Nick).

**Fase 4 — Camada de revisão (Veltron portada)**
- Portar `agent/guards.py` → adaptar: preço Nick, anti-invenção, IA-id, **inverter endereço** (§4.6).
- Portar `team/editor.py` → `run_editor` no pipeline (passo 11). Config `openai_model_editor`.
- Plugar `apply_guards` (passo 8) + `run_editor` (passo 11) no orchestrator.
- Testes `test_guards.py` (preço suprimido, ID inválido degradado, endereço→FAQ).

**Fase 5 — Orchestrator & compose**
- Adaptar `orchestrator.py`: integrar guards + editor + terminais Nick + escala silenciosa.
- `_enforce_singular_question`, shield send, preempção (reusar).

**Fase 6 — Testes & evals**
- Suite unitária (funil, guards, updater, terminais, photos, calendar).
- Cenários ponta-a-ponta (compra direta, troca, financiamento, carta, agendamento, escalas).
- Portar `judge_humanization.py` (eval de estilo).

**Fase 7 — Deploy & observabilidade**
- Docker (`compose.prod.yml`, nginx, subdomínio). ngrok p/ testes.
- Prometheus `/metrics` + Grafana dashboard. Eventos custo USD/BRL.
- Re-config workflows GHL apontando p/ URL final.

---

## 7. Pendências / riscos

- ✅ ~~Calendar ID GHL~~ → `OYoYdb3tAmRbJMQwgjei`. Disponibilidade **validada via free-slots API**: 108 slots/7 dias, ISO `-03:00`, 45min, seg–sáb (dom fechado). `propose_slots`/`book_appointment` AMC funcionam direto. (Detalhe mostra `openHours:{}` mas availability está a nível membro/collective.)
- ✅ ~~Pré-fill contato~~ → field keys confirmados (§5).
- ⚠️ **FAQ vazio** (0/69 respostas) — MVP roda com FAQ parcial; `consultar_faq` retorna o que houver. Popular depois.
- ⚠️ **Estoque teve 2 schemas** (job 3h): enxuto (`id/km/url`, sem imagens) vs completo (`external_id/quilometragem/imagens[]`, 89KB). Resolvido: (a) `inventory.py` normaliza AMBOS (ponte km→quilometragem, url→url_anuncio); (b) usuário republicou o schema completo → fotos ON (25/28 com ≥2 imgs, `will_send` validado). Risco residual: se o job reverter pro enxuto, fotos somem (degrada gracioso, sem crash). Manter job no schema completo.
- ⚠️ **PIT token exposto** no chat — rotacionar.
- Instagram = fase 2 (sender precisa roteamento de canal).
- Editor = +1 LLM/turno: monitorar latência/custo no Grafana.
```
