"""Promosi otomatis ke group menampilkan harga layanan terkini.

Group tetap tidak memicu bot: modul ini hanya mengirim. Daftar harga diambil
langsung dari katalog, dirapikan per platform, lalu disisipkan ke materi
promosi. AI hanya memarafrase kalimat pembuka; tabel harga tidak disentuh.
"""

import logging
import random
import time
import zlib
from datetime import datetime

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

import ai_text
import db
import ui

log = logging.getLogger("tarakapedia.promo")

# Kalimat pembuka; tabel harga asli disisipkan lewat {catalog}.
_TEMPLATES = (
    ("harga", "💎 <b>Tarakapedia SMM Panel</b> — daftar harga jual layanan sosmed terbaru. "
              "Transparan, tanpa biaya tersembunyi, diproses otomatis.\n\n{catalog}"),
    ("pilih", "🔥 Cek harga Instagram, TikTok, Telegram, dan WhatsApp di Tarakapedia. "
              "Pilih layanan, kirim link, order langsung berjalan otomatis.\n\n{catalog}"),
    ("ig", "📸 Suntik Instagram jadi lebih hemat. Berikut contoh harga jual per seribu "
           "yang tersedia sekarang di <b>Tarakapedia</b>.\n\n{catalog}"),
    ("tiktok", "🎵 Suntik TikTok: view, like, followers, dan save dengan harga jelas di awal. "
               "Lihat daftar harganya di <b>Tarakapedia SMM Panel</b>.\n\n{catalog}"),
    ("wa_tg", "💬 WhatsApp channel member dan Telegram post view ikut tersedia. "
              "Ini contoh harga termurah di Tarakapedia.\n\n{catalog}"),
    ("murah", "⚡ Harga mulai puluhan rupiah per seribu untuk sejumlah layanan. "
              "Semua bisa dipesan langsung lewat bot.\n\n{catalog}"),
    ("deposit", "💳 Deposit QRIS otomatis di Tarakapedia: saldo masuk setelah pembayaran "
                "terverifikasi, lalu langsung dipakai untuk order.\n\n{catalog}"),
    ("cara", "🧾 Cara order: pilih layanan, masukkan jumlah dan link, bayar dari saldo, "
             "lalu pantau status. Harga tertera di bawah ini.\n\n{catalog}"),
    ("referral", "🎁 Komisi referral dibayar saat order teman selesai. Sambil lihat "
                 "harga layanan Tarakapedia berikut.\n\n{catalog}"),
    ("order", "📦 Order yang paling sering masuk: Instagram view, TikTok view, "
              "Telegram post view, WhatsApp channel member.\n\n{catalog}"),
    ("garansi", "🔁 Layanan bergaransi bisa diajukan refill dan statusnya diperbarui "
                "otomatis. Cek harga jualnya di bawah.\n\n{catalog}"),
    ("mulai", "✨ Baru mencoba Tarakapedia? Mulai dari yang termurah, lalu naik ke "
              "layanan lain sesuai kebutuhan.\n\n{catalog}"),
    ("channel", "📢 Layanan baru dan perubahan harga diumumkan di channel utama "
                "Tarakapedia. Ini harga jual terkini.\n\n{catalog}"),
    ("lengkap", "🌐 Instagram, TikTok, YouTube, Facebook, Telegram, WhatsApp — "
                "ratusan layanan dalam satu bot.\n\n{catalog}"),
    ("top", "🏆 Papan top transaksi Tarakapedia diurutkan dari total rupiah. "
            "Berikut harga layanan yang bisa dipesan.\n\n{catalog}"),
    ("daftar", "📊 Daftar harga Tarakapedia SMM Panel diperbarui otomatis dari katalog. "
               "Silakan pilih yang sesuai kebutuhan.\n\n{catalog}"),
)

_PRICE_CACHE_TTL = 1800
_price_cache = (0.0, "")

_CATALOG_GROUPS = (
    ("instagram", "📸", "INSTAGRAM", (
        ("View", ("view", "views")),
        ("Like", ("like", "likes")),
        ("Followers", ("followers", "follower", "follow")),
    )),
    ("tiktok", "🎵", "TIKTOK", (
        ("View", ("view", "views")),
        ("Like", ("like", "likes")),
        ("Followers", ("followers", "follower")),
        ("Save", ("save", "saves")),
    )),
    ("telegram", "✈️", "TELEGRAM", (
        ("Post view", ("post view", "post views")),
        ("Member", ("member", "members")),
    )),
    ("whatsapp", "💬", "WHATSAPP", (
        ("Channel member", ("channel", "member")),
    )),
)


async def cheap_catalog() -> str:
    """Tabel harga jual murah per platform, rapi & tanpa data internal."""
    global _price_cache
    now = time.monotonic()
    if _price_cache[0] and now - _price_cache[0] < _PRICE_CACHE_TTL:
        return _price_cache[1]
    rows = await db.sorted_services(await db.q("SELECT * FROM services WHERE active=1"))
    blocks = []
    for key, emoji, title, items in _CATALOG_GROUPS:
        platform_rows = [s for s in rows if db.platform_of(s.get("name") or "")[0] == key]
        picked = []
        for label, keywords in items:
            matches = []
            for s in platform_rows:
                name = str(s.get("name") or "").lower()
                if any(k in name for k in keywords) and s["_price"]:
                    matches.append(int(s["_price"]))
            if matches:
                picked.append((label, min(matches)))
        if not picked:
            continue
        picked.sort(key=lambda x: x[1])
        lines = []
        for i, (label, price) in enumerate(picked):
            branch = "└" if i == len(picked) - 1 else "├"
            dotted = label.ljust(18, ".")
            lines.append(f"{branch} {dotted} {ui.rp(price)}/1K")
        blocks.append(f"{emoji} <b>{title}</b>\n<code>" + "\n".join(lines) + "</code>")
    result = "\n\n".join(blocks) or "<i>Belum ada layanan aktif.</i>"
    _price_cache = (now, result)
    return result


def _message(index: int, catalog: str = "") -> str:
    """Versi template murni (juga dipakai sebagai fallback AI)."""
    intro = _TEMPLATES[index][1].replace("{catalog}", catalog)
    return intro + "\n\n" + ui.BOT_URL


def _base(index: int) -> str:
    """Kalimat pembuka saja, dipakai sebagai prompt paraphrase AI."""
    return _TEMPLATES[index][1].replace("{catalog}", "").strip()


class PromoEngine:
    """Satu promosi per siklus worker, bergilir, dengan jeda natural."""

    def __init__(self):
        self._order = list(range(len(_TEMPLATES)))
        random.shuffle(self._order)
        self._cursor = 0
        self._last_tag: dict[int, str] = {}

    def _pick(self, chat_id: int) -> int:
        previous = self._last_tag.get(chat_id)
        for step in range(len(self._order)):
            pos = (self._cursor + step) % len(self._order)
            index = self._order[pos]
            if _TEMPLATES[index][0] != previous:
                self._cursor = (pos + 1) % len(self._order)
                self._last_tag[chat_id] = _TEMPLATES[index][0]
                return index
        return self._cursor % len(_TEMPLATES)

    def next_message(self, chat_id: int, catalog: str = "") -> str:
        return _message(self._pick(chat_id), catalog)

    async def message_for(self, chat_id: int, catalog: str) -> str:
        """AI hanya mengubah pembuka; tabel harga & CTA tetap utuh."""
        index = self._pick(chat_id)
        intro = _base(index)
        if (await db.setting("promo_ai")) == "1":
            rewritten = await ai_text.variant(_TEMPLATES[index][0], intro)
            if rewritten:
                intro = rewritten
        return intro + "\n\n" + catalog + "\n\n" + ui.BOT_URL

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
        low = max(1, int(await db.setting("promo_min_gap") or 30))
        high = max(low, int(await db.setting("promo_max_gap") or 40))
        frm = int(await db.setting("promo_hour_from") or 8)
        to = int(await db.setting("promo_hour_to") or 21)
        limit = max(1, int(await db.setting("promo_daily_limit") or 20))
        return enabled, low, high, frm, to, limit

    async def tick(self, bot) -> int:
        """Kirim maksimal satu promosi per siklus agar tidak menjadi spam."""
        enabled, low, high, frm, to, limit = await self._settings()
        if not enabled:
            return 0
        now = datetime.now(db.WIB)
        if not (min(frm, to) <= now.hour <= max(frm, to)):
            return 0
        catalog = await cheap_catalog()
        for group in await db.promo_groups():
            chat_id = int(group["chat_id"])
            if int(group["sent_today"] or 0) >= limit:
                continue
            last = self._parse(group["last_sent_at"])
            if last:
                gap = self._gap_minutes(chat_id, db.today(), low, high) * 60
                if (now - last).total_seconds() < gap:
                    continue
            ok = await self._send(bot, chat_id, await self.message_for(chat_id, catalog))
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
        catalog = await cheap_catalog()
        ok = fail = 0
        for group in groups:
            gid = int(group["chat_id"])
            sent = await self._send(bot, gid, await self.message_for(gid, catalog))
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
        ("🤖 AI teks", "<b>Aktif</b>" if (await db.setting("promo_ai")) == "1" else "<b>Nonaktif</b>"),
    ]
    block = ui.tree(rows, head="📢 <b>PROMOSI HARGA LAYANAN</b>")
    note = ("<i>Group terdeteksi otomatis saat bot ditambahkan atau menerima aktivitas. "
            "Harga jual diambil langsung dari katalog, bukan teks rekaan.</i>")
    return block + "\n\n" + note
