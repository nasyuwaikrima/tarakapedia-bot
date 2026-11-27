"""Promosi otomatis ke group dengan pola natural dan aman dari spam.

Group tetap tidak memicu bot: modul ini hanya mengirim. Jeda diacak, jam
aktif dibatasi, kuota harian dibatasi, dan materi promosi bergilir supaya
pesan tidak terasa berulang.
"""

import logging
import random
import time
import zlib
from datetime import datetime

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import db
import ui

log = logging.getLogger("tarakapedia.promo")

# Materi menonjolkan merek & layanan, tetap profesional dan tanpa identitas pihak ketiga.
_TEMPLATES = (
    ("harga", "🔥 <b>TARAKAPEDIA SMM PANEL</b> — suntik sosmed dengan harga bersahabat.\n\n"
              "Contoh harga mulai:\n{prices}\n\nOrder diproses otomatis 24/7. Cek katalog: {bot}"),
    ("ig", "📸 <b>Tarakapedia SMM Panel</b> menyiapkan ratusan layanan Instagram: followers, "
           "likes, story view, dan reels view. Pilih yang cocok, kirim link, sistem proses otomatis.\n\n{bot}"),
    ("tiktok", "🎵 Suntik TikTok juga tersedia: followers, likes, view, dan save. "
               "<b>Tarakapedia SMM Panel</b> menampilkan harga jelas di awal tanpa biaya tersembunyi.\n\n{bot}"),
    ("wa_tg", "💬 WhatsApp channel member, Telegram post view, IG view, TikTok view — semuanya "
              "ada di <b>Tarakapedia SMM Panel</b>. Contoh order yang paling sering masuk.\n\nCek harga: {bot}"),
    ("murah", "⚡ Harga mulai puluhan rupiah per 1K untuk sejumlah layanan Instagram dan TikTok.\n\n"
              "{prices}\n\nSemua tersedia di <b>Tarakapedia SMM Panel</b>: {bot}"),
    ("deposit", "💳 <b>Tarakapedia SMM Panel</b> menyediakan deposit QRIS otomatis. Saldo masuk "
                "begitu pembayaran terverifikasi, tanpa konfirmasi manual.\n\nMulai dari {bot}"),
    ("proses", "🛒 Order di Tarakapedia diproses otomatis: pilih layanan, kirim link, lalu pantau "
               "status lewat menu Pesanan Saya. Ratusan pilihan sosmed tersedia.\n\n{bot}"),
    ("referral", "🎁 Ajak teman ke <b>Tarakapedia SMM Panel</b>, dapatkan komisi dari transaksi "
                 "yang selesai. Kode referral tersedia di menu Referral.\n\n{bot}"),
    ("order", "📦 Contoh order yang rutin masuk: Instagram view, TikTok view, Telegram post view, "
              "dan WhatsApp channel member. Semua bisa dipesan langsung di bot.\n\n{bot}"),
    ("mulai", "✨ Baru mencoba? Buka menu Layanan Termurah, pilih layanan, lalu kirim link sesuai "
              "instruksi. <b>Tarakapedia SMM Panel</b> siap memproses otomatis.\n\n{bot}"),
    ("channel", "📢 Info layanan dan pembaruan harga <b>Tarakapedia</b> diumumkan di channel utama. "
                "Bergabung agar tidak ketinggalan pilihan terbaru.\n\n{bot}"),
    ("lengkap", "🌐 Instagram, TikTok, YouTube, Facebook, Telegram, WhatsApp, dan masih banyak lagi. "
                "Satu bot untuk kebutuhan sosmed: <b>Tarakapedia SMM Panel</b>.\n\n{bot}"),
)

_PRICE_CACHE_TTL = 1800
_price_cache = (0.0, "")

_PLATFORM_LABELS = (
    ("instagram", "📸", "Instagram view"),
    ("tiktok", "🎵", "TikTok view"),
    ("telegram", "✈️", "Telegram post view"),
    ("whatsapp", "💬", "WhatsApp channel member"),
)


async def cheap_products() -> str:
    """Contoh harga jual termurah per platform (tanpa modal/ID provider)."""
    global _price_cache
    now = time.monotonic()
    if _price_cache[0] and now - _price_cache[0] < _PRICE_CACHE_TTL:
        return _price_cache[1]
    rows = await db.sorted_services(await db.q("SELECT * FROM services WHERE active=1"))
    lines = []
    for key, emoji, label in _PLATFORM_LABELS:
        prices = [int(s["_price"]) for s in rows
                  if db.platform_of(s.get("name") or "")[0] == key and s["_price"]]
        if prices:
            lines.append(f"{emoji} {label} — <b>{ui.rp(min(prices))}</b>/1K")
    result = "\n".join(lines)
    _price_cache = (now, result)
    return result


def _message(index: int, prices: str = "") -> str:
    tag, text = _TEMPLATES[index]
    return text.format(bot=ui.BOT_URL, prices=prices)


class PromoEngine:
    """Satu promosi per siklus worker, bergilir, dengan jeda natural."""

    def __init__(self):
        self._order = list(range(len(_TEMPLATES)))
        random.shuffle(self._order)
        self._cursor = 0
        self._last_tag: dict[int, str] = {}

    def next_message(self, chat_id: int, prices: str = "") -> str:
        previous = self._last_tag.get(chat_id)
        for step in range(len(self._order)):
            pos = (self._cursor + step) % len(self._order)
            index = self._order[pos]
            if _TEMPLATES[index][0] != previous:
                self._cursor = (pos + 1) % len(self._order)
                self._last_tag[chat_id] = _TEMPLATES[index][0]
                return _message(index, prices)
        return _message(self._cursor % len(_TEMPLATES), prices)

    @staticmethod
    def _gap_minutes(chat_id: int, day: str, low: int, high: int) -> int:
        if high <= low:
            return max(1, low)
        seed = zlib.crc32(f"{chat_id}:{day}".encode())
        return low + seed % (high - low + 1)

    @staticmethod
    def _parse(value):
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=db.WIB)
        except (TypeError, ValueError):
            return None

    async def _settings(self):
        enabled = (await db.setting("promo_enabled")) == "1"
        low = max(1, int(await db.setting("promo_min_gap") or 120))
        high = max(low, int(await db.setting("promo_max_gap") or 300))
        frm = int(await db.setting("promo_hour_from") or 8)
        to = int(await db.setting("promo_hour_to") or 21)
        limit = max(1, int(await db.setting("promo_daily_limit") or 4))
        return enabled, low, high, frm, to, limit

    async def tick(self, bot) -> int:
        """Kirim maksimal satu promosi per siklus agar tidak menjadi spam."""
        enabled, low, high, frm, to, limit = await self._settings()
        if not enabled:
            return 0
        now = datetime.now(db.WIB)
        if not (min(frm, to) <= now.hour <= max(frm, to)):
            return 0
        prices = await cheap_products()
        for group in await db.promo_groups():
            chat_id = int(group["chat_id"])
            if int(group["sent_today"] or 0) >= limit:
                continue
            last = self._parse(group["last_sent_at"])
            if last:
                gap = self._gap_minutes(chat_id, db.today(), low, high) * 60
                if (now - last).total_seconds() < gap:
                    continue
            ok = await self._send(bot, chat_id, self.next_message(chat_id, prices))
            if ok:
                await db.mark_promo_sent(chat_id)
                return 1
        return 0

    async def _send(self, bot, chat_id: int, text: str) -> bool:
        try:
            await bot.send_message(chat_id, text, reply_markup=ui.channel_markup(),
                                   disable_web_page_preview=True)
            return True
        except (TelegramForbiddenError, TelegramBadRequest) as e:
            detail = str(e).lower()
            if any(x in detail for x in ("bot is not a member", "chat not found",
                                          "forbidden", "kicked", "not a member")):
                await db.set_promo_group(chat_id, False)
                log.warning("Promosi group %s dinonaktifkan: bot tidak bisa mengirim", chat_id)
            else:
                log.warning("Promosi group %s gagal: %s", chat_id, e)
            return False
        except Exception as e:
            log.warning("Promosi group %s gagal: %s", chat_id, e)
            return False

    async def send_test(self, bot, chat_id: int | None = None) -> tuple[int, int]:
        """Kirim satu promosi sekarang (pilihan admin), tetap tercatat di kuota."""
        groups = await db.promo_groups()
        if chat_id is not None:
            groups = [g for g in groups if int(g["chat_id"]) == int(chat_id)]
        prices = await cheap_products()
        ok = fail = 0
        for group in groups:
            gid = int(group["chat_id"])
            sent = await self._send(bot, gid, self.next_message(gid, prices))
            if sent:
                await db.mark_promo_sent(gid)
                ok += 1
            else:
                fail += 1
        return ok, fail


promo = PromoEngine()


async def status_block() -> str:
    """Ringkasan konfigurasi promosi untuk panel admin."""
    enabled, low, high, frm, to, limit = await promo._settings()
    groups = await db.promo_groups(active_only=False)
    active = sum(1 for g in groups if g["active"])
    rows = [
        ("📣 Status", "<b>Aktif</b>" if enabled else "<b>Nonaktif</b>"),
        ("👥 Group", f"<b>{active}</b> aktif dari {len(groups)} terdeteksi"),
        ("⏱ Jeda", f"<b>{low}–{high}</b> menit (diacak)"),
        ("🕒 Jam aktif", f"<b>{frm:02d}.00–{to:02d}.00</b> WIB"),
        ("🧾 Kuota", f"<b>{limit}</b> pesan per group per hari"),
    ]
    block = ui.tree(rows, head="📢 <b>PROMOSI GROUP</b>")
    note = ("<i>Group terdeteksi otomatis saat bot ditambahkan atau menerima aktivitas. "
            "Status aktif/nonaktif diatur lewat tombol di bawah.</i>")
    return block + "\n\n" + note
