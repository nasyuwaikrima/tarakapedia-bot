"""Client API MedanPedia (panel SMM).

Semua request memakai JSON body lewat POST. Kredensial dibaca dari .env dan
TIDAK pernah dikirim ke tampilan user. Harga provider hanya dipakai sebagai
"modal" di sisi admin.

Endpoint yang dipakai:
  /services       -> daftar layanan (+ service_fav)
  /profile        -> saldo provider (khusus admin)
  /order          -> order sesuai tipe layanan
  /status         -> cek status order
  /refill         -> ajukan refill
  /refill_status  -> cek status refill
"""
from __future__ import annotations

import json
from typing import Any

import aiohttp

from config import (MEDANPEDIA_API_ID, MEDANPEDIA_API_KEY, MEDANPEDIA_BASE_URL,
                    MEDANPEDIA_TIMEOUT)


class ProviderError(Exception):
    """Gagal komunikasi/validasi dari API provider."""


# Field tambahan yang wajib dikirim untuk tiap tipe layanan.
TYPE_FIELDS: dict[str, tuple[str, ...]] = {
    "default": (),
    "package": (),
    "custom_comment": ("comments",),
    "comment_likes": (),
    "mention_list": ("usernames",),
    "mention_hashtag": ("hashtag",),
    "mention_follower": ("username",),
    "mention_media": ("media",),
    "poll": (),
    "comment_reply": ("comments",),
    "comment_live": (),
}

LABEL_FIELDS = {
    "comments": "daftar komentar (satu per baris)",
    "usernames": "daftar username (satu per baris)",
    "hashtag": "hashtag (tanpa/ dengan #)",
    "username": "username/link sumber followers",
    "media": "link media sumber likers",
}

NO_QUANTITY = {"package", "custom_comment", "mention_list"}

STATUS_MAP = {
    "pending": "Pending", "waiting": "Pending", "queue": "Pending",
    "processing": "Processing", "inprogress": "Processing", "partial": "Processing",
    "completed": "Completed", "complete": "Completed", "success": "Completed",
    "finished": "Completed", "canceled": "Canceled", "cancelled": "Canceled",
    "refunded": "Canceled", "failed": "Canceled",
}


def normalize_type(raw: Any) -> str:
    t = str(raw or "default").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "custom_comments": "custom_comment", "customcomments": "custom_comment",
        "mention_hastag": "mention_hashtag", "mentions_hashtag": "mention_hashtag",
        "mentions_custom_list": "mention_list", "mention_custom_list": "mention_list",
        "mentions_user_followers": "mention_follower", "mentions_media_likers": "mention_media",
        "commentlikes": "comment_likes", "commentreply": "comment_reply",
    }
    return aliases.get(t, t if t in TYPE_FIELDS else "default")


def type_fields(ptype: str) -> tuple[str, ...]:
    return TYPE_FIELDS.get(normalize_type(ptype), ())


def needs_quantity(ptype: str) -> bool:
    return normalize_type(ptype) not in NO_QUANTITY


def normalize_status(raw: Any) -> str:
    key = str(raw or "").strip().lower()
    return STATUS_MAP.get(key, str(raw).strip() or "Processing")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _pick(data: Any, keys: tuple[str, ...]):
    if isinstance(data, dict):
        for k in keys:
            if data.get(k) not in (None, ""):
                return data[k]
    return None


class MedanPediaProvider:
    name = "medanpedia"

    def __init__(self, api_id=None, api_key=None, base_url=None, timeout=None):
        self.api_id = str(api_id if api_id is not None else MEDANPEDIA_API_ID)
        self.api_key = str(api_key if api_key is not None else MEDANPEDIA_API_KEY)
        self.base_url = (base_url or MEDANPEDIA_BASE_URL).rstrip("/")
        self.timeout = timeout or MEDANPEDIA_TIMEOUT
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_id and self.api_id.isdigit() and self.api_key)

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

    async def post(self, endpoint: str, **params: Any) -> dict:
        if not self.configured:
            raise ProviderError("Kredensial MedanPedia belum diisi di file .env")
        payload = {"api_id": self.api_id, "api_key": self.api_key}
        payload.update({k: v for k, v in params.items() if v is not None})
        session = await self._session_get()
        try:
            async with session.post(f"{self.base_url}/{endpoint.lstrip('/')}", data=payload) as r:
                raw = await r.text()
        except aiohttp.ClientError as e:
            raise ProviderError(f"Koneksi ke provider gagal: {e}") from e
        if r.status != 200:
            raise ProviderError(f"Provider merespons HTTP {r.status}: {raw[:120]}")
        try:
            js = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ProviderError("Respons provider bukan JSON valid") from e
        if not isinstance(js, dict):
            raise ProviderError("Format respons provider tidak dikenal")
        ok = js.get("status")
        valid = (ok is True or (isinstance(ok, (int, float)) and ok == 1)
                 or (isinstance(ok, str) and ok.strip().lower() in {"true", "1", "ok", "success"}))
        if not valid and js.get("data") is None:
            raise ProviderError(str(js.get("msg") or js.get("message") or "Provider menolak permintaan"))
        return js

    # ---------- katalog & saldo ----------
    async def services(self, service_fav: bool = False) -> list[dict]:
        js = await self.post("services", service_fav=1 if service_fav else 0)
        data = js.get("data") or []
        if isinstance(data, dict):
            data = _pick(data, ("services", "data", "list")) or []
        if not isinstance(data, list):
            return []
        items = []
        for row in data:
            if not isinstance(row, dict):
                continue
            sid = _as_int(_pick(row, ("id", "service", "service_id")))
            if not sid:
                continue
            items.append({
                "id": sid,
                "name": str(_pick(row, ("name", "service_name")) or f"Layanan {sid}"),
                "type": normalize_type(_pick(row, ("type",))),
                "category": str(_pick(row, ("category", "group")) or "Lainnya"),
                "price": _as_int(_pick(row, ("price", "price_per_1k"))),
                "min": _as_int(_pick(row, ("min", "min_qty"))),
                "max": _as_int(_pick(row, ("max", "max_qty"))),
                "refill": int(bool(_pick(row, ("refill", "refillable")))),
                "average_time": str(_pick(row, ("average_time", "avg_time")) or ""),
                "description": str(_pick(row, ("description", "desc")) or ""),
            })
        return items

    async def profile(self) -> dict:
        """Saldo provider = modal. Hanya dipanggil dari handler admin."""
        try:
            js = await self.post("profile")
        except ProviderError:
            js = await self.post("balance")
        data = js.get("data") or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        if not isinstance(data, dict):
            data = {}
        balance = _as_int(_pick(data, ("balance", "saldo", "credit")) or _pick(js, ("balance", "saldo")))
        return {"balance": balance, "raw": data}

    # ---------- order ----------
    async def order(self, service: int, target: str, quantity: int | None = None,
                    ptype: str = "default", **extra: Any) -> str:
        ptype = normalize_type(ptype)
        payload: dict[str, Any] = {"service": int(service), "target": str(target)}
        if needs_quantity(ptype):
            if not quantity or quantity <= 0:
                raise ProviderError("Jumlah pesanan tidak valid untuk tipe layanan ini")
            payload["quantity"] = int(quantity)
        for field in type_fields(ptype):
            value = extra.get(field)
            if value in (None, ""):
                raise ProviderError(f"Field {field} wajib untuk layanan {ptype}")
            payload[field] = str(value).replace("\r\n", "\n")
        js = await self.post("order", **payload)
        data = js.get("data")
        oid = _pick(data, ("order", "id_order", "order_id", "id")) or _pick(js, ("order", "id_order", "order_id"))
        if oid is None and isinstance(data, (str, int)):
            oid = data
        if not oid:
            raise ProviderError("Provider tidak mengembalikan ID pesanan")
        return str(oid)

    async def order_status(self, order_ids: list[str]) -> dict[str, str]:
        ids = [str(i) for i in order_ids if i]
        if not ids:
            return {}
        js = await self.post("status", orders=",".join(ids))
        data = js.get("data") or {}
        out: dict[str, str] = {}
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict):
                    out[str(key)] = normalize_status(_pick(val, ("status", "state", "description")))
                else:
                    out[str(key)] = normalize_status(val)
        elif isinstance(data, list):
            for row in data:
                if isinstance(row, dict):
                    oid = _pick(row, ("order", "id_order", "order_id", "id"))
                    if oid:
                        out[str(oid)] = normalize_status(_pick(row, ("status", "state")))
        return out

    async def refill(self, order_id: str) -> str:
        js = await self.post("refill", id_order=str(order_id))
        data = js.get("data")
        rid = _pick(data, ("refill", "id_refill", "refill_id", "id", "order")) or _pick(js, ("refill", "id_refill"))
        if rid is None and isinstance(data, (str, int)):
            rid = data
        if not rid:
            raise ProviderError("Provider tidak mengembalikan ID refill")
        return str(rid)

    async def refill_status(self, refill_id: str) -> str:
        js = await self.post("refill_status", id_refill=str(refill_id))
        data = js.get("data")
        if isinstance(data, dict):
            return normalize_status(_pick(data, ("status", "state", "description")))
        return normalize_status(data)


provider = MedanPediaProvider()
