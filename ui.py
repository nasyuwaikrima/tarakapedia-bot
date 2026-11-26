import html
import time

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from config import (ADMIN_CONTACT_URL, ADMIN_IDS, BOT_NAME, CUSTOM_MENU_PHOTO,
                    MENU_PHOTO, WEBSITE_URL)

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
    rows = [
        [("💰 Deposit Saldo", "dep"), ("🛒 Order Layanan", "ord")],
        [("📱 Toko Aplikasi", "shop"), ("📦 Pesanan Saya", "myord")],
        [("🧾 Riwayat", "hist"), ("👤 Profil Saya", "prof")],
        [("🎁 Kode Referral", "ref"), ("🎯 Misi Special", "msn")],
        [("🛍 Order di Website", WEBSITE_URL)],
        [("📞 Hubungi Admin", ADMIN_CONTACT_URL)],
    ]
    if uid in ADMIN_IDS:
        rows.append([("🛠 Panel Admin", "adm")])
    return kb(*rows)


async def answer_cb(c: CallbackQuery, text: str | None = None, alert: bool = False):
    try:
        await c.answer(text, show_alert=alert)
    except Exception:
        pass


async def show(ev, text: str, markup=None):
    """Edit pesan jika dari tombol, kirim baru jika dari pesan biasa."""
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.edit_text(text, reply_markup=markup, disable_web_page_preview=True)
        except TelegramBadRequest as e:
            if "not modified" not in str(e):
                await ev.message.answer(text, reply_markup=markup, disable_web_page_preview=True)
        await answer_cb(ev)
    else:
        await ev.answer(text, reply_markup=markup, disable_web_page_preview=True)


def menu_photo():
    """Foto unggahan admin mengalahkan foto bawaan."""
    return CUSTOM_MENU_PHOTO if CUSTOM_MENU_PHOTO.exists() else MENU_PHOTO


async def show_menu(ev, caption: str, markup=None):
    """Menu utama dikirim sebagai foto + caption; fallback ke teks bila foto tidak ada."""
    photo = menu_photo()
    if not photo.exists():
        return await show(ev, caption, markup)
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.delete()
        except TelegramBadRequest:
            pass
        await ev.message.answer_photo(FSInputFile(photo), caption=caption[:1000], reply_markup=markup)
        await answer_cb(ev)
    else:
        await ev.answer_photo(FSInputFile(photo), caption=caption[:1000], reply_markup=markup)


async def menu_caption(uid: int) -> str:
    u = await db.get_user(uid)
    s = await db.global_stats()
    t = (f"{LINE}\n💎 <b>{esc(BOT_NAME.upper())} · SMM PANEL</b>\n{LINE}\n\n"
         f"Halo kak {esc(u['name'] or 'kaw')} 👋\n"
         f"💰 Saldo : <b>{rp(u['balance'])}</b>\n"
         f"📦 Order : <b>{num(u['total_order'])}</b> kali\n"
         f"👥 Member : <b>{num(s['users'])}</b> orang\n\n"
         f"Pilih menu di bawah ya — order diproses otomatis 🔥")
    ann = await db.setting("announcement")
    if ann:
        t += f"\n\n📢 {esc(ann[:180])}"
    return t


async def show_photo(ev, photo, caption: str, markup=None):
    """Kirim foto dari URL/path dengan fallback teks jika Telegram gagal fetch."""
    if isinstance(ev, CallbackQuery):
        try:
            await ev.message.delete()
        except TelegramBadRequest:
            pass
        try:
            await ev.message.answer_photo(photo=photo, caption=caption[:1000], reply_markup=markup)
        except TelegramBadRequest:
            await ev.message.answer(caption, reply_markup=markup, disable_web_page_preview=True)
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
    d, ref, bonus = result
    u = await db.get_user(d["user_id"])
    try:
        await bot.send_message(d["user_id"],
                               f"✅ <b>Deposit Berhasil!</b>\n\n├ Nominal : <b>{rp(d['amount'])}</b>\n"
                               f"└ Saldo : <b>{rp(u['balance'])}</b>",
                               reply_markup=kb([("🛒 Order Layanan", "ord")], BACK))
    except Exception:
        pass
    if ref:
        try:
            await bot.send_message(ref, f"💸 Komisi referral <b>{rp(bonus)}</b> dari deposit downline Anda.")
        except Exception:
            pass
    await notify_admins(bot, f"💰 Deposit QRIS #{d['id']} dari <code>{d['user_id']}</code>: {rp(d['amount'])}")


async def notify_admins(bot, text: str):
    for a in ADMIN_IDS:
        try:
            await bot.send_message(a, text)
        except Exception:
            pass


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
    t += f"\n{LINE}\n🚀 <i>Silakan pilih menu transaksi di bawah, sistem memproses otomatis dan cepat!</i>"
    return t
