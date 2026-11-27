import asyncio
import html
import logging
import os
import re
import time

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import logcard
from config import (ADMIN_CONTACT_URL, ADMIN_IDS, BOT_NAME, CHANNEL_LOG, CHANNEL_LOG_URL,
                    CHANNEL_REGISTRY, CHANNEL_REGISTRY_URL, CUSTOM_MENU_PHOTO, MENU_PHOTO,
                    WEBSITE_URL)

log = logging.getLogger("tarakapedia.ui")
BOT_URL = f"https://t.me/{os.getenv('BOT_USERNAME', 'tarakapedia_bot').strip().lstrip('@')}"
START = time.time()
esc = html.escape
LINE = "━━━━━━━━━━━━━━━━━━━━"
BACK = [("⬅️ Kembali", "menu")]

STATUS_EMOJI = {"Pending": "🕒", "Processing": "⚙️", "Completed": "✅", "Canceled": "❌"}
STATUS_ID = {"Pending": "Menunggu", "Processing": "Diproses", "Completed": "Selesai", "Canceled": "Dibatalkan"}


def rp(n) -> str:
    return "Rp " + f"{int(n):,}".replace(",", ".")


def num(n) -> str:
    return f"{int(n):,}".replace(",", ".")


def clean_desc(text: str | None, limit: int = 320) -> str:
    """Bersihkan deskripsi provider jadi poin rapi untuk caption Telegram."""
    raw = str(text or "")
    raw = re.sub(r"(?i)<br\s*/?>|</?p\b[^>]*>|</?div\b[^>]*>|</?li\b[^>]*>|</?ul\b[^>]*>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html.unescape(raw).replace("\r", "\n")
    lines, seen = [], set()
    for part in raw.split("\n"):
        line = re.sub(r"\s+", " ", part).strip(" •–-\u00a0")
        key = line.lower()
        if not line or key in seen:
            continue
        seen.add(key)
        lines.append(line[:90])
        if sum(len(x) + 1 for x in lines) >= limit:
            break
    return "\n".join(lines)


def user_link(uid: int, name: str | None = None, username: str | None = None) -> str:
    """Mention user yang bisa diklik (khusus pesan privat, bukan log channel)."""
    label = name or (f"@{username}" if username else f"ID {uid}")
    return f'<a href="tg://user?id={int(uid)}">{esc(label)[:60]}</a>'


def public_user(uid: int, name: str | None = None, username: str | None = None) -> str:
    """Identitas untuk log publik: username polos, tanpa mention atau ID."""
    if username:
        return esc(f"@{username}")[:50]
    return esc((name or "Pengguna").strip())[:50]


def channel_markup(include_main: bool = True, include_log: bool = False):
    """Tombol aksi untuk pesan channel: bot, channel utama, dan log aktivitas."""
    rows = [[("🛒 Lihat Layanan", f"{BOT_URL}?start=layanan"),
             ("💰 Deposit", f"{BOT_URL}?start=deposit")]]
    if include_main and CHANNEL_REGISTRY_URL:
        rows.append([("📢 Channel Utama", CHANNEL_REGISTRY_URL)])
    if include_log and CHANNEL_LOG_URL:
        rows.append([("📜 Log Aktivitas", CHANNEL_LOG_URL)])
    return kb(*rows)


async def log_channel(bot, text: str, card_title: str | None = None):
    """Kirim log transaksi ke channel sebagai kartu dashboard + caption.

    Gambar dibuat otomatis per transaksi. Bila generate/kirim foto gagal, log
    tetap terkirim sebagai teks agar transaksi tidak terdampak.
    """
    if not CHANNEL_LOG:
        return
    caption = text + (f"\n\n🔗 Channel Utama: {CHANNEL_REGISTRY_URL}" if CHANNEL_REGISTRY_URL else "")
    try:
        await bot.send_photo(CHANNEL_LOG, photo=logcard.photo(text, card_title),
                             caption=caption[:1000], reply_markup=channel_markup())
        return
    except Exception as e:
        log.warning("Gagal kirim kartu log ke channel: %s", e)
    try:
        await bot.send_message(CHANNEL_LOG, caption, reply_markup=channel_markup(),
                               disable_web_page_preview=True)
    except Exception as e:
        log.warning("Gagal kirim log teks ke channel: %s", e)


async def info_channel(bot, text: str, card_title: str | None = None):
    """Kirim info layanan/perubahan ke channel utama, bukan channel log."""
    if not CHANNEL_REGISTRY:
        return
    caption = text + (f"\n\n📜 Log Aktivitas: {CHANNEL_LOG_URL}" if CHANNEL_LOG_URL else "")
    try:
        await bot.send_photo(CHANNEL_REGISTRY, photo=logcard.photo(text, card_title),
                             caption=caption[:1000],
                             reply_markup=channel_markup(include_main=False, include_log=True))
        return
    except Exception as e:
        log.warning("Gagal kirim kartu info ke channel utama: %s", e)
    try:
        await bot.send_message(CHANNEL_REGISTRY, caption,
                               reply_markup=channel_markup(include_main=False, include_log=True),
                               disable_web_page_preview=True)
    except Exception as e:
        log.warning("Gagal kirim info teks ke channel utama: %s", e)


async def log_new_member(bot, uid: int, name: str | None, username: str | None,
                         ref_line: str = ""):
    """Kirim poster welcome user baru ke channel log tanpa mention/ID."""
    if not CHANNEL_LOG:
        return
    who = public_user(uid, name, username)
    caption = f"🆕 <b>MEMBER BARU</b>\n👤 {who}{ref_line}"
    if CHANNEL_REGISTRY_URL:
        caption += f"\n\n🔗 Channel Utama: {CHANNEL_REGISTRY_URL}"
    try:
        await bot.send_photo(CHANNEL_LOG, photo=logcard.welcome_photo(who),
                             caption=caption[:1000], reply_markup=channel_markup())
        return
    except Exception as e:
        log.warning("Gagal kirim poster member baru ke channel: %s", e)
    try:
        await bot.send_message(CHANNEL_LOG, caption, reply_markup=channel_markup(),
                               disable_web_page_preview=True)
    except Exception as e:
        log.warning("Gagal kirim log member baru ke channel: %s", e)


async def welcome_card(ev, name: str, caption: str, markup=None):
    """Kirim kartu sambutan bergambar untuk user baru."""
    try:
        await ev.answer_photo(photo=logcard.welcome_photo(name), caption=caption[:1000],
                              reply_markup=markup)
        return
    except Exception as e:
        log.warning("Gagal kirim kartu welcome: %s", e)
    try:
        await ev.answer(caption, reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        log.warning("Gagal kirim welcome teks: %s", e)


def bar(v, t, w=10) -> str:
    f = w if not t else max(0, min(w, int(w * v / t)))
    return "▰" * f + "▱" * (w - f)


def kb(*rows):
    b = InlineKeyboardBuilder()
    for row in rows:
        b.row(*[InlineKeyboardButton(text=t, url=d) if d.startswith("http")
                else InlineKeyboardButton(text=t, callback_data=d) for t, d in row])
    return b.as_markup()


def main_kb(uid: int | None = None):
    """Menu utama: baris 2 tombol & 1 tombol dirapatkan agar rapi di layar."""
    rows = [
        [("💰 Deposit QRIS", "dep"), ("🛒 Order Termurah", "ord")],
        [("📦 Pesanan Saya", "myord"), ("🧾 Riwayat", "hist")],
        [("🏆 Top Transaksi", "top:all")],
        [("🧩 Lainnya", "misc")],
        [("📢 Channel Kami", CHANNEL_REGISTRY_URL), ("📜 Log Transaksi", CHANNEL_LOG_URL)],
    ]
    return kb(*rows)


def misc_kb(uid: int | None = None):
    """Menu lanjutan: toko, profil, referral, misi, website, admin."""
    rows = [
        [("📱 Toko App", "shop"), ("👤 Profil Saya", "prof")],
        [("🎁 Kode Referral", "ref"), ("🎯 Misi Special", "msn")],
        [("🌐 Website", WEBSITE_URL), ("💬 Hubungi Admin", ADMIN_CONTACT_URL)],
    ]
    if uid in ADMIN_IDS:
        rows.append([("🛠 Panel Admin", "adm")])
    return kb(*rows, BACK)


def top_kb(active: str = "all"):
    """Pilihan periode papan peringkat."""
    opts = [("all", "🏆 Semua"), ("week", "📅 Mingguan"), ("month", "🗓 Bulanan")]
    rows = [[(("✅ " if k == active else "") + label, f"top:{k}") for k, label in opts]]
    return kb(*rows, BACK)


async def answer_cb(c: CallbackQuery, text: str | None = None, alert: bool = False):
    try:
        await c.answer(text, show_alert=alert)
    except Exception:
        pass


async def show(ev, text: str, markup=None):
    """Edit pesan yang sama (termasuk caption foto) — jangan kirim pesan baru dari tombol."""
    if isinstance(ev, CallbackQuery):
        m = ev.message
        try:
            if getattr(m, "photo", None):
                await m.edit_caption(caption=text[:1000], reply_markup=markup)
            else:
                await m.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await m.answer(text, reply_markup=markup, disable_web_page_preview=True)
        await answer_cb(ev)
    else:
        await ev.answer(text, reply_markup=markup, disable_web_page_preview=True)


def menu_photo():
    """Foto unggahan admin mengalahkan foto bawaan."""
    return CUSTOM_MENU_PHOTO if CUSTOM_MENU_PHOTO.exists() else MENU_PHOTO


async def show_menu(ev, caption: str, markup=None):
    """Menu foto + caption. Dari tombol: edit pesan yang sama, bukan delete + kirim ulang."""
    photo = menu_photo()
    if not photo.exists():
        return await show(ev, caption, markup)
    if isinstance(ev, CallbackQuery):
        m = ev.message
        try:
            await m.edit_media(media=InputMediaPhoto(media=FSInputFile(photo), caption=caption[:1000]),
                               reply_markup=markup)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                try:
                    if getattr(m, "photo", None):
                        await m.edit_caption(caption=caption[:1000], reply_markup=markup)
                    else:
                        await m.edit_text(caption, reply_markup=markup, disable_web_page_preview=True)
                except TelegramBadRequest as e2:
                    if "not modified" not in str(e2):
                        await m.answer_photo(FSInputFile(photo), caption=caption[:1000], reply_markup=markup)
        await answer_cb(ev)
    else:
        await ev.answer_photo(FSInputFile(photo), caption=caption[:1000], reply_markup=markup)


async def top_spender_block(limit: int = 3, period: str = "all") -> str:
    """Papan peringkat transaksi rupiah dengan username yang bisa diklik."""
    rows = await db.top_spenders(limit, period)
    title = {
        "all": "🏆 <b>TOP TRANSAKSI</b>",
        "week": "📅 <b>TOP MINGGUAN</b>\n⏳ 7 hari terakhir",
        "month": "🗓 <b>TOP BULANAN</b>\n⏳ 30 hari terakhir",
    }.get(period, "🏆 <b>TOP TRANSAKSI</b>")
    if not rows:
        return f"{title}\nBelum ada transaksi. Jadilah yang pertama! 🚀"
    medals = ("🥇", "🥈", "🥉")
    lines = []
    for i, r in enumerate(rows):
        rank = medals[i] if i < len(medals) else f"{i + 1}."
        label = f"@{r['username']}" if r["username"] else (r["name"] or f"ID {r['id']}")
        lines.append(f"{rank} {user_link(r['id'], label, r['username'])} • <b>{rp(r['total_spent'])}</b>")
    return title + "\n" + "\n".join(lines)


async def menu_caption(uid: int) -> str:
    u = await db.get_user(uid)
    s = await db.global_stats()
    t = (f"{LINE}\n💎 <b>{esc(BOT_NAME.upper())} · SMM PANEL</b>\n{LINE}\n\n"
         f"Selamat datang kembali, {esc(u['name'] or 'Pengguna')} 👋\n\n"
         f"┌ 💰 Saldo  : <b>{rp(u['balance'])}</b>\n"
         f"├ 📦 Order  : <b>{num(u['total_order'])}</b> kali\n"
         f"└ 👥 Member : <b>{num(s['users'])}</b> orang\n\n")
    t += await top_spender_block(3) + "\n\n"
    t += ("⚡ Pesanan diproses otomatis 24/7\n"
          "💸 Deposit QRIS dengan konfirmasi otomatis\n"
          "🎁 Program referral dengan komisi margin order\n\n"
          "Silakan pilih menu berikut 👇")
    ann = await db.setting("announcement")
    if ann:
        t += f"\n\n📢 <b>Info:</b> {esc(ann[:140])}"
    return t


async def show_photo(ev, photo, caption: str, markup=None):
    """Foto QRIS/invoice. Dari tombol: ganti media pesan yang sama agar tidak spam."""
    if isinstance(ev, CallbackQuery):
        m = ev.message
        try:
            await m.edit_media(media=InputMediaPhoto(media=photo, caption=caption[:1000]),
                               reply_markup=markup)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                try:
                    await m.answer_photo(photo=photo, caption=caption[:1000], reply_markup=markup)
                except TelegramBadRequest:
                    await m.answer(caption, reply_markup=markup, disable_web_page_preview=True)
        await answer_cb(ev)
    else:
        try:
            await ev.answer_photo(photo=photo, caption=caption[:1000], reply_markup=markup)
        except TelegramBadRequest:
            await ev.answer(caption, reply_markup=markup, disable_web_page_preview=True)


async def deposit_paid_notice(bot, result):
    """Notifikasi deposit lunas — dipakai tombol cek manual dan polling."""
    if not result:
        return
    d, _ref, _bonus = result  # komisi dipindah ke order sukses, bukan deposit
    u = await db.get_user(d["user_id"])
    try:
        await bot.send_message(d["user_id"],
                               f"✅ <b>Deposit Berhasil!</b>\n\n├ Nominal : <b>{rp(d['amount'])}</b>\n"
                               f"└ Saldo : <b>{rp(u['balance'])}</b>",
                               reply_markup=kb([("🛒 Order Layanan", "ord")], BACK))
    except Exception:
        pass
    who = public_user(d["user_id"], u["name"] if u else None, u["username"] if u else None)
    await notify_admins(bot, f"💰 Deposit QRIS #{d['id']} dari <code>{d['user_id']}</code>: {rp(d['amount'])}")
    await log_channel(bot, f"✅ <b>DEPOSIT LUNAS</b> #{d['id']}\n👤 {who}\n💰 {rp(d['amount'])}\n"
                           f"🏦 Saldo sekarang: <b>{rp(u['balance'] if u else 0)}</b>")


async def referral_paid_notice(bot, oid: int, bonus: int, ref_id: int):
    """Komisi referral hanya dikirim saat order benar-benar selesai."""
    if not bonus or not ref_id:
        return
    try:
        await bot.send_message(ref_id, f"💸 Komisi referral <b>{rp(bonus)}</b> dari order "
                                       f"<code>#{oid}</code> yang sudah selesai. Terima kasih.")
    except Exception:
        pass
    ref = await db.get_user(ref_id)
    await log_channel(bot, f"🎁 <b>KOMISI REFERRAL</b> #{oid}\n"
                           f"👤 {public_user(ref_id, ref['name'] if ref else None, ref['username'] if ref else None)}"
                           f" • {rp(bonus)} dari margin order selesai")


async def notify_admins(bot, text: str):
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text)
        except Exception:
            pass


async def catalog_update_notice(bot, info: dict, broadcast: bool = True) -> tuple[int, int]:
    """Umumkan layanan baru / perubahan harga ke channel utama dan semua user.

    `info` berasal dari db.sync_services() atau aksi admin. Hanya harga jual
    yang ditampilkan — modal dan ID provider tidak pernah ikut terkirim.
    """
    new_count = int(info.get("new_count", len(info.get("new_items") or [])))
    changed_count = int(info.get("changed_count", len(info.get("price_changes") or [])))
    if not new_count and not changed_count:
        return 0, 0

    title = str(info.get("title") or "PEMBARUAN KATALOG")
    lines = [f"📢 <b>{esc(title)}</b>"]
    if new_count:
        lines.append(f"🆕 Layanan baru : <b>{num(new_count)}</b>")
    if changed_count:
        lines.append(f"💲 Perubahan harga : <b>{num(changed_count)}</b>")
    for x in (info.get("new_items") or [])[:4]:
        lines.append(f"• {esc(str(x['name'])[:40])} • {rp(x['price'])}")
    for x in (info.get("price_changes") or [])[:4]:
        lines.append(f"• {esc(str(x['name'])[:28])} : {rp(x['old'])} menjadi {rp(x['new'])}")
    caption = "\n".join(lines) + "\n\n🛒 Cek layanan terbaru lewat tombol di bawah."

    await info_channel(bot, caption, card_title=title)
    if not broadcast:
        return 0, 0

    markup = kb([("🛒 Lihat Layanan", "ord")])
    ok = fail = 0
    for u in await db.q("SELECT id FROM users WHERE banned=0"):
        try:
            await bot.send_message(u["id"], caption, reply_markup=markup)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    return ok, fail


def uptime() -> str:
    up = int(time.time() - START)
    d, r = divmod(up, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"


async def dashboard(uid: int) -> str:
    u = await db.get_user(uid)
    s = await db.global_stats()
    uname = "@" + esc(u["username"]) if u["username"] else "-"
    t = (
        f"{LINE}\n💎 <b>{esc(BOT_NAME.upper())} SMM PANEL</b>\n"
        f"<i>Layanan sosmed &amp; aplikasi premium — cepat, otomatis, terpercaya</i>\n{LINE}\n\n"
        f"📊 <b>STATISTIK PROFIL</b>\n"
        f"├ Nama : <b>{esc(u['name'] or '-')}</b>\n"
        f"├ Username : {uname}\n"
        f"├ ID Tele : <code>{uid}</code>\n"
        f"├ Saldo : <b>{rp(u['balance'])}</b>\n"
        f"├ Total Order : <b>{num(u['total_order'])}</b>\n"
        f"└ Bergabung : {u['joined_at']} WIB\n\n"
        f"⭐ <b>TRUST STATISTICS</b>\n"
        f"├ Member Bot : <b>{num(s['users'])}</b>\n"
        f"├ Order via Bot : <b>{num(s['orders'])}</b>\n"
        f"└ Total Transaksi : <b>{rp(s['revenue'])}</b>\n\n"
        f"🤖 <b>INFORMASI BOT</b>\n"
        f"├ Status : ONLINE 24/7\n"
        f"└ Uptime : {uptime()}\n"
    )
    ann = await db.setting("announcement")
    if ann:
        t += f"\n📢 <b>Pengumuman</b>\n{esc(ann)}\n"
    t += f"\n{LINE}\n🚀 <i>Silakan pilih menu transaksi berikut. Sistem memproses pesanan secara otomatis.</i>"
    return t
