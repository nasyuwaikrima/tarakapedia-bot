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

import ai_text
import db
import ui

log = logging.getLogger("tarakapedia.promo")

# Materi menonjolkan merek & layanan, tetap profesional dan tanpa identitas pihak ketiga.
_TEMPLATES = (
    ("detail", "┌ 🏷 <b>TARAKAPEDIA SMM PANEL</b>\n"
               "├ 📦 Layanan : ratusan pilihan sosmed\n"
               "├ 🌐 Platform : IG, TikTok, YouTube, Facebook, Telegram, WhatsApp\n"
               "├ 💰 Harga jual : mulai puluhan rupiah per 1K\n"
               "├ ⚡ Proses : otomatis 24/7, status bisa dipantau\n"
               "├ 🔁 Garansi : refill pada layanan bergaransi\n"
               "├ 💳 Deposit : QRIS otomatis tanpa konfirmasi manual\n"
               "├ 🎁 Referral : komisi saat order teman selesai\n"
               "└ 📢 Info : channel utama &amp; log aktivitas\n\n"
               "{prices}\n\nBuka katalog: {bot}"),
    ("harga", "🔥 <b>TARAKAPEDIA SMM PANEL</b> — suntik sosmed dengan harga bersahabat.\n\n"
              "Contoh harga mulai:\n{prices}\n\nOrder diproses otomatis 24/7. Cek katalog: {bot}"),
    ("cara", "🧾 <b>CARA ORDER DI TARAKAPEDIA</b>\n"
              "┌ 1️⃣ Buka bot, pilih menu Layanan Termurah\n"
              "├ 2️⃣ Pilih platform, kategori, lalu layanan\n"
              "├ 3️⃣ Masukkan jumlah &amp; link sesuai instruksi\n"
              "├ 4️⃣ Bayar dari saldo (QRIS otomatis bila perlu)\n"
              "└ 5️⃣ Pantau status lewat menu Pesanan Saya\n\n"
              "Semua berjalan otomatis. Mulai dari {bot}"),
    ("ig", "📸 <b>Tarakapedia SMM Panel</b> menyediakan ratusan layanan Instagram: followers, likes, "
           "story view, reels view, dan comment. Harga jual transparan di katalog, order diproses "
           "otomatis 24/7, status bisa dipantau, dan layanan bergaransi bisa diajukan refill.\n\n"
           "Cek pilihannya: {bot}"),
    ("tiktok", "🎵 Suntik TikTok di <b>Tarakapedia SMM Panel</b>: followers, likes, view, dan save "
               "dengan harga jelas di awal. Pilih layanan, kirim link, sistem memproses otomatis. "
               "Saldo, riwayat, dan status order selalu bisa dicek langsung di bot.\n\n{bot}"),
    ("wa_tg", "💬 WhatsApp channel member, Telegram member dan post view, IG view, TikTok view — "
              "semuanya ada di <b>Tarakapedia SMM Panel</b>. Harga mulai puluhan rupiah per 1K, "
              "deposit QRIS otomatis, order berjalan tanpa perlu menunggu manual.\n\nCek harga: {bot}"),
    ("murah", "⚡ Harga mulai puluhan rupiah per 1K untuk sejumlah layanan Instagram dan TikTok.\n\n"
              "{prices}\n\nSemua tersedia di <b>Tarakapedia SMM Panel</b>, diproses otomatis, "
              "dengan riwayat transaksi yang rapi: {bot}"),
    ("deposit", "💳 <b>Tarakapedia SMM Panel</b> memakai deposit QRIS otomatis. Buat invoice, bayar, "
                "saldo masuk setelah terverifikasi. Invoice bisa dilihat ulang kapan saja, saldo "
                "langsung dipakai untuk order, dan tidak perlu konfirmasi manual.\n\nMulai dari {bot}"),
    ("proses", "🛒 Order di Tarakapedia berjalan otomatis: pilih layanan, tentukan jumlah, kirim link, "
               "lalu bayar dari saldo. Status berubah sendiri saat selesai, riwayat tersimpan rapi, "
               "dan refill bisa diajukan untuk layanan bergaransi.\n\nBuka katalog: {bot}"),
    ("referral", "🎁 Program referral <b>Tarakapedia SMM Panel</b>: ajak teman, dapatkan komisi dari "
                 "margin order yang selesai. Komisi dibayar sekali, berlaku 7 hari sejak teman daftar, "
                 "dan kode referral tersedia di menu Referral.\n\nCek sekarang: {bot}"),
    ("order", "📦 Contoh order yang rutin masuk: Instagram view, TikTok view, Telegram post view, dan "
              "WhatsApp channel member. Semua bisa dipesan langsung dengan harga jual tertera, "
              "tanpa biaya tersembunyi.\n\nLihat daftar layanan: {bot}"),
    ("garansi", "🔁 Setiap order di <b>Tarakapedia SMM Panel</b> tercatat rapi. Layanan bergaransi bisa "
                "diajukan refill, statusnya diperbarui otomatis, dan riwayat transaksi tetap bisa "
                "dicek kapan saja lewat menu Riwayat.\n\nLihat layanan: {bot}"),
    ("mulai", "✨ Baru mencoba Tarakapedia? Buka menu Layanan Termurah, pilih platform dan layanan, "
              "masukkan jumlah serta link, lalu bayar dari saldo. Deposit QRIS otomatis tersedia bila "
              "saldo belum cukup.\n\nMulai sekarang: {bot}"),
    ("channel", "📢 <b>Tarakapedia</b> mengumumkan layanan baru dan perubahan harga di channel utama. "
                "Channel aktivitas menampilkan bukti transaksi otomatis tanpa mention, kontak, atau "
                "ID user. Gabung agar tidak ketinggalan pembaruan.\n\nBuka bot: {bot}"),
    ("lengkap", "🌐 Instagram, TikTok, YouTube, Facebook, Telegram, WhatsApp, dan masih banyak lagi. "
                "Ratusan layanan dengan harga jual jelas, deposit QRIS otomatis, proses 24/7, "
                "garansi refill, dan komisi referral. Satu bot untuk kebutuhan sosmed: "
                "<b>Tarakapedia SMM Panel</b>.\n\n{bot}"),
    ("top", "🏆 Papan top transaksi <b>Tarakapedia</b> diperbarui tiap minggu dan diurutkan dari total "
            "rupiah yang dibelanjakan. Ikut serta lewat bot: deposit otomatis, order diproses 24/7, "
            "saldo serta riwayat selalu transparan.\n\nCek papan: {bot}"),
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


def _base(index: int) -> str:
    """Materi tanpa data dinamis, dipakai sebagai prompt paraphrase AI."""
    return _TEMPLATES[index][1].replace("{prices}", "").replace("{bot}", "").strip()


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

    def next_message(self, chat_id: int, prices: str = "") -> str:
        """Versi template murni (juga dipakai sebagai fallback)."""
        return _message(self._pick(chat_id), prices)

    async def message_for(self, chat_id: int, prices: str) -> str:
        """Hybrid: paraphrase AI tervalidasi + data harga asli + CTA bot."""
        index = self._pick(chat_id)
        fallback = _message(index, prices)
        if (await db.setting("promo_ai")) != "1":
            return fallback
        rewritten = await ai_text.variant(_TEMPLATES[index][0], _base(index))
        if not rewritten:
            return fallback
        parts = [rewritten]
        if "{prices}" in _TEMPLATES[index][1] and prices:
            parts.append(prices)
        parts.append(ui.BOT_URL)
        return "\n\n".join(parts)

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
            ok = await self._send(bot, chat_id, await self.message_for(chat_id, prices))
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
            sent = await self._send(bot, gid, await self.message_for(gid, prices))
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
    block = ui.tree(rows, head="📢 <b>PROMOSI GROUP</b>")
    note = ("<i>Group terdeteksi otomatis saat bot ditambahkan atau menerima aktivitas. "
            "Status aktif/nonaktif diatur lewat tombol di bawah.</i>")
    return block + "\n\n" + note
