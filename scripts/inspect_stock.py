"""Dump 1º veículo do estoque + lista de chaves."""
from __future__ import annotations

import asyncio
import json

from zoi_agent.config import settings
from zoi_agent.ghl.client import close_client
from zoi_agent.ghl.custom_values import extract_value, get_custom_value


async def main() -> None:
    cv = await get_custom_value(settings.ghl_stock_custom_value_id)
    raw = extract_value(cv) or ""
    print(f"raw bytes: {len(raw)}")
    print(f"first 300 chars: {raw[:300]!r}")
    try:
        data = json.loads(raw)
    except Exception as e:
        print(f"JSON parse fail: {e}")
        await close_client()
        return
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for k in ("vehicles", "items", "data", "estoque", "veiculos"):
            if k in data and isinstance(data[k], list):
                items = data[k]
                print(f"items found under key: {k}")
                break
        else:
            print(f"top-level dict keys: {list(data.keys())}")
            items = []
    else:
        items = []
    print(f"total items: {len(items)}")
    if items:
        first = items[0]
        print(f"\n--- 1º item ---")
        print(json.dumps(first, indent=2, ensure_ascii=False)[:2000])
        if isinstance(first, dict):
            print(f"\n--- chaves ---\n{sorted(first.keys())}")
    await close_client()


if __name__ == "__main__":
    asyncio.run(main())
