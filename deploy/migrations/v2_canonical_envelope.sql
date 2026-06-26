-- ============================================================================
-- MIGRAÇÃO v2 — Envelope canônico v1 (CONTRATO_EVENTOS_CANONICO.md)
-- Aplica sobre um banco que JÁ rodou Fase 1/2 (agent_events + pricing antigos).
-- create_all do app é ADITIVO-ONLY: NÃO altera tabela existente → esta migração
-- faz o ALTER de agent_events e recria pricing (forma nova).
--
-- Pré-requisitos: Postgres >= 13 (gen_random_uuid() no core; pg16 OK).
-- Rodar ANTES de subir a app v2. Idempotente (IF NOT EXISTS / backfill por NULL).
-- ============================================================================

BEGIN;

-- 1) agent_events: colunas do envelope canônico ---------------------------------
ALTER TABLE agent_events
  ADD COLUMN IF NOT EXISTS event_id        varchar(36),
  ADD COLUMN IF NOT EXISTS schema_version  integer NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS client          varchar(32),
  ADD COLUMN IF NOT EXISTS occurred_at     timestamptz,
  ADD COLUMN IF NOT EXISTS reasoning_tokens integer,
  ADD COLUMN IF NOT EXISTS cost_brl        numeric(12,6),
  ADD COLUMN IF NOT EXISTS usd_brl_rate    numeric(12,6),
  ADD COLUMN IF NOT EXISTS pricing_version varchar(32);

-- 2) Backfill das colunas que vão virar NOT NULL --------------------------------
UPDATE agent_events SET event_id = gen_random_uuid()::text WHERE event_id IS NULL;
UPDATE agent_events SET client = 'nick-motors'                     WHERE client IS NULL;
UPDATE agent_events SET occurred_at = created_at           WHERE occurred_at IS NULL;

-- 3) Constraints + índices ------------------------------------------------------
ALTER TABLE agent_events ALTER COLUMN event_id    SET NOT NULL;
ALTER TABLE agent_events ALTER COLUMN client      SET NOT NULL;
ALTER TABLE agent_events ALTER COLUMN occurred_at SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS ix_agent_events_event_id        ON agent_events(event_id);
CREATE INDEX        IF NOT EXISTS ix_agent_events_agent_occurred  ON agent_events(agent, occurred_at);
CREATE INDEX        IF NOT EXISTS ix_agent_events_contact_occurred ON agent_events(contact_id, occurred_at);
CREATE INDEX        IF NOT EXISTS ix_agent_events_type_occurred   ON agent_events(event_type, occurred_at);

-- 4) pricing: forma nova (model+kind, price_usd por 1M / por min) ----------------
--    Tabela é APENAS dado de seed (sem dado de negócio). DROP seguro — o boot da
--    app recria via create_all + seed_pricing() com os preços canônicos.
DROP TABLE IF EXISTS pricing;

COMMIT;

-- ============================================================================
-- VALIDAÇÃO pós-migração (rodar após subir a app v2):
--
--   SELECT count(*) FILTER (WHERE event_id IS NULL)  AS sem_event_id,
--          count(DISTINCT event_id) = count(*)       AS event_id_unico,
--          count(*) FILTER (WHERE client <> 'nick-motors')   AS client_errado
--   FROM agent_events;
--
--   SELECT model, kind, price_usd, usd_brl_rate, pricing_version FROM pricing ORDER BY 1,2;
--   -- esperado: gpt-4o(input 2.50/output 10), gpt-4o-mini(0.15/0.60),
--   --           whisper-1(audio_minute 0.006); rate 5.40; version 2026-06-17
-- ============================================================================
