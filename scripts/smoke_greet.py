"""Smoke greet ao vivo. Pré-requisitos:
  1) Postgres rodando: `docker compose up -d`
  2) App rodando: `.venv/bin/python -m zoi_agent.main`
  3) Contato GHL com tag `agente-ia`.

Casos:
  C1 — sem Veículo de Interesse, sem SAUDAÇÃO=SIM (envia genérica)
  C2 — com Veículo de Interesse, sem SAUDAÇÃO=SIM (envia personalizada)
  C3 — SAUDAÇÃO=SIM (retorna skipped=True sem mandar mensagem)

O contato de teste padrão (d9ILOnEyNkYhkIALa3wq) já está em estado C3 —
saudação já enviada antes. Use-o pra validar idempotência sem disparar WA real.
"""
from __future__ import annotations

import sys

import httpx

from zoi_agent.config import settings

DEFAULT_CONTACT = "d9ILOnEyNkYhkIALa3wq"
BASE_URL = "http://localhost:8000"


def main(contact_id: str) -> int:
    url = f"{BASE_URL}/sessions/{contact_id}/greet"
    r = httpx.post(url, params={"secret": settings.webhook_secret}, timeout=30)
    print(f"status: {r.status_code}")
    print(f"body: {r.text}")
    return 0 if r.status_code == 200 else 1


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CONTACT
    sys.exit(main(cid))
