"""Verifica valor atual do custom field SAUDAÇÃO PRÉ-VENDAS no contato teste."""
from __future__ import annotations

import asyncio
import sys

from zoi_agent.config import settings
from zoi_agent.ghl import contacts as gc
from zoi_agent.ghl.client import close_client

DEFAULT_CID = "d9ILOnEyNkYhkIALa3wq"


async def main(cid: str) -> int:
    contact = await gc.get_contact(cid)
    saud = gc.read_custom_field_value(contact, settings.ghl_field_saudacao_prevendas)
    veic = gc.read_custom_field_value(contact, settings.ghl_field_veiculo_interesse)
    print(f"contato: {cid}")
    print(f"SAUDAÇÃO PRÉ-VENDAS: {saud!r}")
    print(f"Veículo de Interesse: {veic!r}")
    print(f"-> idempotente? {(saud or '').strip().upper() == 'SIM'}")
    await close_client()
    return 0


if __name__ == "__main__":
    cid = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CID
    sys.exit(asyncio.run(main(cid)))
