# Deploy — Nick Motors Agent

Single-tenant. App FastAPI (`zoi_agent`) + Postgres, atrás de nginx + TLS.
Subdomínio placeholder: `nickmotors.appzoi.com.br` (ajuste pro seu DNS).

## Pré-requisitos
- VPS com Docker + Docker Compose, nginx, certbot.
- DNS A de `nickmotors.appzoi.com.br` → IP da VPS.
- `.env.prod` preenchido (copie de `.env.prod.example`).

## Passos

```bash
# 1. clone
git clone https://github.com/raul-behnke/Agente-Nick-Motors.git /opt/nick-motors
cd /opt/nick-motors/deploy

# 2. env de produção (NÃO commitar)
cp .env.prod.example .env.prod
# edite: OPENAI_API_KEY, GHL_PIT_TOKEN, WEBHOOK_SECRET (openssl rand -hex 32),
#        POSTGRES_PASSWORD. IDs GHL já vêm preenchidos (location/calendar/CVs/workflow).

# 3. sobe app + postgres
docker compose -f compose.prod.yml up -d --build
docker compose -f compose.prod.yml ps

# 4. (1ª vez) migration de telemetria
docker compose -f compose.prod.yml exec -T postgres \
  psql -U nick -d nick_agent < migrations/v2_canonical_envelope.sql

# 5. nginx + TLS
cp nginx-vhost.conf /etc/nginx/sites-available/nickmotors.appzoi.com.br.conf
ln -sf /etc/nginx/sites-available/nickmotors.appzoi.com.br.conf \
       /etc/nginx/sites-enabled/nickmotors.appzoi.com.br
certbot --nginx -d nickmotors.appzoi.com.br --non-interactive --agree-tos -m admin@appzoi.com.br
nginx -t && systemctl reload nginx

# 6. smoke
curl -fsSL https://nickmotors.appzoi.com.br/health
curl -fsSL https://nickmotors.appzoi.com.br/metrics | head
```

## Workflows GHL (apontar pro servidor)
Tag gate `agente-ia`. Endpoints (HMAC `?secret=<WEBHOOK_SECRET>`):
- **Greet** (contato criado c/ tag + `saudaçao inicial` ≠ sim) → `POST /sessions/{{contact.id}}/greet?secret=...`
- **Inbound** (mensagem recebida c/ tag) → `POST /webhook/inbound?secret=...`
- **Abandono** (opcional, inatividade) → `POST /sessions/{{contact.id}}/abandon?secret=...`
- Handoff: workflow `1b741458-895e-42b6-9225-d085d14a6d9e` (disparado pela app).

Testes: ngrok → `POST /webhook/inbound` (re-configurar URL no GHL a cada restart).
Produção: subdomínio fixo acima.

## Observabilidade
- `/metrics` (Prometheus): `zoi_turns_total`, `zoi_handoff_total`, `zoi_qualificados_total`,
  `zoi_llm_latency_seconds`, custo USD/BRL por turno (eventos `agent_events`).
- Grafana: importar `grafana/dashboard.json`.
- Componentes LLM no envelope: `updater | estoque_expert | nick | editor | whisper`.
