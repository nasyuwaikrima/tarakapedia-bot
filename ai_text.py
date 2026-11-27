"""Paraphrase gratis untuk teks promosi, dengan validasi ketat.

Memakai endpoint teks Pollinations (tanpa API key). Hasil AI tidak pernah
dipakai mentah: angka, tautan, identitas pihak ketiga, dan sapaan informal
ditolak, lalu nilai harga asli disuntikkan kembali dari database oleh promo.py.
"""

import asyncio
import logging
import os
import re
import time

import aiohttp

log = logging.getLogger("tarakapedia.ai_text")

URL = os.getenv("AI_TEXT_URL", "https://text.pollinations.ai/openai").strip()
MODEL = os.getenv("AI_TEXT_MODEL", "openai").strip()
TIMEOUT = float(os.getenv("AI_TEXT_TIMEOUT", "15") or 15)
TTL = 6 * 3600       # satu variasi per materi, dipakai ulang 6 jam
FAIL_TTL = 10 * 60  # jeda sebelum mencoba lagi setelah gagal
MIN_CALL_GAP = 50   # batas gratis Pollinations: sekitar 1 balasan / 45 detik per IP

_cache: dict[str, tuple[float, str | None]] = {}
_last_call = 0.0
_lock = asyncio.Lock()

_INFORMAL = re.compile(r"\b(bang|kak|kakak|kamu|yuk|nih|kok|dong)\b|\b ya\b", re.IGNORECASE)
_BRANDS = re.compile(r"pixpayz|medanpedia|api\s*key|apikey|provider", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
_URL = re.compile(r"https?://\S+")


def _clean(raw: str) -> str | None:
    """Terima hanya paraphrase aman; tolak angka/harga/tautan rekaan."""
    text = _TAG.sub("", str(raw or ""))
    text = _URL.sub("", text)
    text = re.sub(r"24\s*/\s*7", "", text)
    if re.search(r"\d", text):
        return None
    if _BRANDS.search(text) or _INFORMAL.search(text):
        return None
    if "Tarakapedia" not in text:
        return None
    text = " ".join(text.split())
    if not (140 <= len(text) <= 700):
        return None
    return text


async def _fetch(base: str) -> str | None:
    """Ambil satu paraphrase dari layanan AI gratis."""
    prompt = (
        "Tulis ulang teks promosi berikut menjadi satu versi baru yang natural, "
        "profesional, dan persuasif untuk grup Telegram. Gunakan bahasa Indonesia. "
        "Sertakan kata Tarakapedia. Jangan pakai angka, harga, tautan, mention, "
        "nama penyedia, atau sapaan akrab seperti bang, kak, kamu. "
        "Panjang 200 sampai 600 karakter. Teks asli:\n\n" + base
    )
    payload = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 400,
    }
    timeout = aiohttp.ClientTimeout(total=TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(URL, json=payload) as r:
            if r.status != 200:
                raise RuntimeError(f"HTTP {r.status}")
            data = await r.json(content_type=None)
    choices = data.get("choices") or []
    if not choices:
        return None
    content = (choices[0].get("message") or {}).get("content") or ""
    return _clean(content)


async def variant(tag: str, base: str) -> str | None:
    """Paraphrase yang di-cache per materi. Gagal → None (fallback template)."""
    now = time.monotonic()
    hit = _cache.get(tag)
    if hit and now - hit[0] < (TTL if hit[1] else FAIL_TTL):
        return hit[1]
    async with _lock:
        global _last_call
        hit = _cache.get(tag)
        if hit and now - hit[0] < (TTL if hit[1] else FAIL_TTL):
            return hit[1]
        if now - _last_call < MIN_CALL_GAP:
            return None
        _last_call = now
        try:
            result = await _fetch(base)
        except Exception as e:
            log.warning("AI paraphrase gagal (%s): %r", tag, e)
            result = None
        _cache[tag] = (now, result)
        return result
