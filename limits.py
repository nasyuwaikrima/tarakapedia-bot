"""Batas order mengikuti saldo provider.

Saldo provider dan harga modal adalah information admin: modul ini hanya
mengembalikan keputusan boleh/tidak, tidak pernah angka saldo ke user.
"""
from __future__ import annotations

import math
import time

import providers

CACHE_SECONDS = 300
_cache = {"balance": None, "at": 0.0}


async def get_balance(force: bool = False) -> int | None:
    """Saldo provider, di-cache 5 menit. None = belum bisa dicek."""
    now = time.monotonic()
    if not force and _cache["balance"] is not None and now - _cache["at"] < CACHE_SECONDS:
        return _cache["balance"]
    try:
        info = await providers.provider.profile()
        balance = max(0, int(info.get("balance") or 0))
    except Exception:
        return _cache["balance"]  # pakai data terakhir; provider yang akan menolak jika kurang
    _cache["balance"] = balance
    _cache["at"] = now
    return balance


async def can_cover(service, billable: int) -> bool:
    """True kalau modal order masih muat di saldo provider."""
    modal = int(service["provider_price"] or 0)
    billable = int(billable or 0)
    if modal <= 0 or billable <= 0:
        return True
    cost = math.ceil(modal * billable / 1000)
    if cost <= 0:
        return True
    balance = await get_balance()
    if balance is None:
        return True
    return balance >= cost
