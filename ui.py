import html
import time

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InputMediaPhoto
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from config import (ADMIN_CONTACT_URL, ADMIN_IDS, BOT_NAME, CHANNEL_LOG, CHANNEL_LOG_URL,
                    CHANNEL_REGISTRY_URL, CUSTOM_MENU_PHOTO, MENU_PHOTO, WEBSITE_URL)

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


def user_link(uid: int, name: str | None = None, username: str | None = None) -> str:
    """Mention user yang bisa diklik di channel log."""
    label = name or (f"@{username}" if username else f"ID {uid}")
    return f'<a href="tg://user?id={int(uid)}">{esc(label)[:60]}</a>'


async def log_channel(bot, text: str):
    """Kirim log transaksi ke channel. Gagal kirim tidak boleh menggagalkan transaksi."""
    if not CHANNEL_LOG:
        return
    footer = f"\n\n🔗 Gabung: {CHANNEL_REGISTRY_URL}" if CHANNEL_REGISTRY_URL else ""
    try:
        await bot.send_message(CHANNEL_LOG, text + footer, disable_web_page_preview=True)
    except Exception:
        pass


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
    """Menu utama: alur deposit → order → cek hasil, semua tombol terkelompok."""
    rows = [
        [("💰 Deposit QRIS", "dep"), ("🛒 Order Termurah", "ord")],
        [("📦 Pesanan Saya", "myord"), ("🧾 Riwayat", "hist")],
        [("📱 Toko App", "shop"), ("👤 Profil Saya", "prof")],
        [("🎁 Kode Referral", "ref"), ("🎯 Misi Special", "msn")],
        [("🏆 Top Order", "top")],
        [("📢 Channel Kami", CHANNEL_REGISTRY_URL), ("📜 Log Transaksi", CHANNEL_LOG_URL)],
        [("🌐 Website", WEBSITE_URL), ("💬 Hubungi Admin", ADMIN_CONTACT_URL)],
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


async def top_order_block(limit: int = 3) -> str:
    """Papan peringkat top order dengan username yang bisa diklik."""
    rows = await db.top_orders(limit)
    if not rows:
        return ""
    medals = ("🥇", "🥈", "🥉")
    lines = []
    for i, r in enumerate(rows):
        rank = medals[i] if i < len(medals) else f"{i + 1}."
        label = f"@{r['username']}" if r["username"] else (r["name"] or f"ID {r['id']}")
        lines.append(f"{rank} {user_link(r['id'], label, r['username'])} • <b>{num(r['total_order'])}</b> order")
    return "🏆 <b>TOP ORDER</b>\n" + "\n".join(lines)


async def menu_caption(uid: int) -> str:
    u = await db.get_user(uid)
    s = await db.global_stats()
    t = (f"{LINE}\n💎 <b>{esc(BOT_NAME.upper())} · SMM PANEL</b>\n{LINE}\n\n"
         f"Hai kak {esc(u['name'] or 'kaw')} 👋 selamat datang kembali!\n\n"
         f"┌ 💰 Saldo  : <b>{rp(u['balance'])}</b>\n"
         f"├ 📦 Order  : <b>{num(u['total_order'])}</b> kali\n"
         f"└ 👥 Member : <b>{num(s['users'])}</b> orang\n\n")
    top = await top_order_block(3)
    if top:
        t += top + "\n\n"
    t += ("⚡ Pesanan diproses otomatis 24/7\n"
          "💸 Deposit QRIS — cek lunas tanpa ribet\n"
          "🎁 Ajak teman, dapat komisi referral\n\n"
          "Silakan pilih menu di bawah ya, kak 👇")
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
    who = user_link(d["user_id"], u["name"] if u else None, u["username"] if u else None)
    await notify_admins(bot, f"💰 Deposit QRIS #{d['id']} dari <code>{d['user_id']}</code>: {rp(d['amount'])}")
    await log_channel(bot, f"✅ <b>DEPOSIT LUNAS</b> #{d['id']}\n👤 {who}\n💰 {rp(d['amount'])}\n"
                           f"🏦 Saldo sekarang: <b>{rp(u['balance'] if u else 0)}</b>")


async def referral_paid_notice(bot, oid: int, bonus: int, ref_id: int):
    """Komisi referral hanya dikirim saat order benar-benar selesai."""
    if not bonus or not ref_id:
        return
    try:
        await bot.send_message(ref_id, f"💸 Komisi referral <b>{rp(bonus)}</b> dari order "
                                       f"<code>#{oid}</code> yang sudah selesai. Makasih ya!")
    except Exception:
        pass
    await log_channel(bot, f"🎁 <b>KOMISI REFERRAL</b> #{oid}\n"
                           f"👤 <code>{ref_id}</code> • {rp(bonus)} dari margin order selesai")


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
