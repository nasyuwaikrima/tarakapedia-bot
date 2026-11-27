"""Gateway pembayaran QRIS (identitas penyedia disamarkan di seluruh pesan).

Endpoint (GET, query param apikey):
  /api/profile        -> profil & saldo merchant
  /api/createinvoice  -> buat invoice QRIS
  /api/checkinvoice   -> cek status invoice

Batas API: 2 request/detik. Semua request lewat satu rate limiter global.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import aiohttp

from config import (PIXPAYZ_API_KEY, PIXPAYZ_BASE_URL, PIXPAYZ_MIN_INTERVAL,
                    PIXPAYZ_TIMEOUT)


class GatewayError(Exception):
    """Gagal komunikasi/validasi dari gateway QRIS."""


PAID = {"paid", "success", "completed"}
EXPIRED = {"expired", "failed", "canceled", "cancelled"}


class PixPayzGateway:
    name = "QRIS"
    demo = False

    def __init__(self, api_key=None, base_url=None, timeout=None, min_interval=None):
        self.api_key = str(api_key if api_key is not None else PIXPAYZ_API_KEY)
        self.base_url = (base_url or PIXPAYZ_BASE_URL).rstrip("/")
        self.timeout = timeout or PIXPAYZ_TIMEOUT
        self.min_interval = min_interval or PIXPAYZ_MIN_INTERVAL
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._last = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    async def _session_get(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"Accept": "application/json"},
            )
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def _get(self, endpoint: str, **params: Any) -> dict:
        if not self.configured:
            raise GatewayError("Kredensial gateway QRIS belum diisi di file .env")
        session = await self._session_get()
        query = {"apikey": self.api_key, **{k: v for k, v in params.items() if v is not None}}
        # Satu lock untuk seluruh proses: jeda antar request menjaga < 2 req/detik.
        async with self._lock:
            for attempt in range(3):
                wait = self.min_interval - (time.monotonic() - self._last)
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last = time.monotonic()
                try:
                    async with session.get(f"{self.base_url}{endpoint}", params=query) as r:
                        if r.status == 429:
                            await asyncio.sleep(1 + attempt)
                            continue
                        raw = await r.text()
                except aiohttp.ClientError as e:
                    raise GatewayError(f"Koneksi gateway QRIS gagal: {e}") from e
                if r.status != 200:
                    raise GatewayError(f"Gateway QRIS merespons HTTP {r.status}: {raw[:120]}")
                try:
                    js = json.loads(raw)
                except json.JSONDecodeError as e:
                    raise GatewayError("Respons gateway QRIS bukan JSON valid") from e
                if not isinstance(js, dict):
                    raise GatewayError("Format respons gateway QRIS tidak dikenal")
                if js.get("success") is False:
                    raise GatewayError(str(js.get("message") or "Gateway QRIS menolak permintaan"))
                return js
        raise GatewayError("Gateway QRIS terus memberi 429 (terlalu banyak request)")

    async def profile(self) -> dict:
        js = await self._get("/api/profile")
        return {
            "username": js.get("username", ""),
            "email": js.get("email", ""),
            "balance": int(js.get("balance") or 0),
            "pending_balance": int(js.get("pending_balance") or 0),
        }

    async def create(self, deposit_id: int, amount: int) -> dict:
        js = await self._get("/api/createinvoice", amount=int(amount))
        invoice_id = js.get("invoice_id") or js.get("id")
        if not invoice_id:
            raise GatewayError("Gateway QRIS tidak mengembalikan invoice_id")
        return {
            "ref": str(invoice_id),
            "invoice_id": str(invoice_id),
            "qris_image": str(js.get("qris_image") or ""),
            "payment_link": str(js.get("payment_link") or ""),
            "expired_at": str(js.get("expired_at") or ""),
            "amount": int(js.get("amount") or amount),
            "fee": int(js.get("fee") or 0),
            "total": int(js.get("total") or amount),
        }

    async def check(self, invoice_id: str) -> dict:
        js = await self._get("/api/checkinvoice", id=invoice_id)
        return {"status": str(js.get("status") or "").strip().lower(), "raw": js}

    @staticmethod
    def is_paid(status: str) -> bool:
        return str(status).strip().lower() in PAID

    @staticmethod
    def is_expired(status: str) -> bool:
        return str(status).strip().lower() in EXPIRED


gateway = PixPayzGateway()
