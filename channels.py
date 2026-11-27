"""Gate wajib join 2 channel + pengingat otomatis saat user keluar."""

import logging
import time
from datetime import datetime

from aiogram import BaseMiddleware, Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import ChatMemberUpdated

import db
import ui
from config import (ADMIN_IDS, CHANNEL_LOG, CHANNEL_LOG_URL, CHANNEL_REGISTRY,
                    CHANNEL_REGISTRY_URL)

log = logging.getLogger("tarakapedia.channels")

CHANNELS = [
    ("📢 Channel Register", CHANNEL_REGISTRY, CHANNEL_REGISTRY_URL),
    ("📜 Channel Log", CHANNEL_LOG, CHANNEL_LOG_URL),
]

# Di Telegram, restricted tetap dianggap sudah gabung. Pending belum disetujui.
ALLOWED = {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR,
           ChatMemberStatus.CREATOR, ChatMemberStatus.RESTRICTED, "restricted"}
LEFT = {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED, "left", "kicked"}

SKIP_CALLBACKS = {"gate:check", "menu"}
SKIP_COMMANDS = ("/start", "/menu")
_last_prompt: dict[int, float] = {}
_warned: set[str] = set()


def _norm(chat: str | None) -> str:
    return (chat or "").lstrip("@").lower()


def _warn_once(chat: str, err: Exception):
    key = f"{chat}:{type(err).__name__}:{str(err)[:80]}"
    if key not in _warned:
        _warned.add(key)
        log.warning("Tidak bisa cek member di %s: %s. Pastikan bot jadi admin channel.", chat, err)


def _fresh(ts: str | None, max_age: int = 86400) -> bool:
    """Status join terakhir masih dipercaya selama 24 jam kalau API channel error."""
    if not ts:
        return False
    try:
        checked = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(tzinfo=db.WIB)
        return (datetime.now(db.WIB) - checked).total_seconds() < max_age
    except (TypeError, ValueError):
        return False


async def _fallback_if_unreadable(uid: int, label, chat, url, status="tidak bisa dicek"):
    """API error: percaya status joined yang masih fresh, selain itu tetap gate."""
    u = await db.get_user(uid)
    if u and u["channel_status"] == "joined" and _fresh(u["channel_checked_at"]):
        return None
    return (label, chat, url, status)


async def missing_channels(bot: Bot, uid: int) -> list[tuple[str, str, str, str]]:
    """Return channel yang belum terverifikasi. Error API → pakai status register terakhir."""
    missing = []
    for label, chat, url in CHANNELS:
        if not chat:
            continue
        try:
            member = await bot.get_chat_member(chat_id=chat, user_id=uid)
            status = str(getattr(member, "status", "")).lower()
            if status not in ALLOWED:
                missing.append((label, chat, url, status))
        except TelegramBadRequest as e:
            msg = str(e).lower()
            # User benar-benar tidak ada di channel, bedakan dari bot yang bukan admin.
            if "user not found" in msg or ("not a member" in msg and "bot" not in msg):
                missing.append((label, chat, url, "tidak ditemukan"))
            else:
                _warn_once(chat, e)
                fallback = await _fallback_if_unreadable(uid, label, chat, url)
                if fallback:
                    missing.append(fallback)
        except Exception as e:
            _warn_once(chat, e)
            fallback = await _fallback_if_unreadable(uid, label, chat, url)
            if fallback:
                missing.append(fallback)
    return missing


def join_markup(missing):
    missing_chats = {_norm(x[1]) for x in missing}
    rows = []
    for label, chat, url in CHANNELS:
        icon = "❌" if _norm(chat) in missing_chats else "✅"
        rows.append([(f"{icon} {label}", url)])
    rows.append([("✅ Saya sudah gabung", "gate:check")])
    return ui.kb(*rows)


def join_caption(missing) -> str:
    rows = []
    for label, chat, url in CHANNELS:
        left = any(_norm(x[1]) == _norm(chat) for x in missing)
        rows.append(f"{'❌' if left else '✅'} {label} — <a href=\"{url}\">{ui.esc(chat)}</a>")
    return (f"{ui.LINE}\n🔒 <b>WAJIB GABUNG 2 CHANNEL</b>\n{ui.LINE}\n\n"
            + "\n".join(rows)
            + "\n\nAnda belum bergabung atau baru saja keluar dari channel. "
              "Silakan bergabung, lalu tekan <b>✅ Saya sudah gabung</b>.\n\n"
              "Channel dipakai sebagai registrasi &amp; log transaksi supaya tidak ketinggalan info.")


async def gate(ev, bot: Bot | None = None, state=None, welcome: bool = False,
               quiet: bool = False) -> bool:
    """True kalau user digate (pesan join sudah dikirim)."""
    uid = getattr(getattr(ev, "from_user", None), "id", None)
    if uid is None or uid in ADMIN_IDS:
        return False
    bot = bot or ev.bot
    missing = await missing_channels(bot, uid)
    old = await db.set_channel_status(uid, "out" if missing else "joined")
    if not quiet and old != ("out" if missing else "joined"):
        u = await db.get_user(uid)
        who = ui.public_user(uid, u["name"] if u else None, u["username"] if u else None)
        if missing:
            await ui.log_channel(bot, f"⚠️ <b>REGISTER CHANNEL</b>\n👤 {who}\n"
                                      f"Keluar/belum join: {ui.esc(', '.join(x[1] for x in missing))}")
        elif old is not None:
            await ui.log_channel(bot, f"✅ <b>REGISTER TERVERIFIKASI</b>\n👤 {who}\n"
                                      f"Sudah gabung di 2 channel")
    if not missing:
        return False
    if welcome:
        name = getattr(getattr(ev, "from_user", None), "full_name", None)
        caption = (f"🎉 <b>Selamat datang, {ui.esc(name or 'Pengguna')}!</b>\n\n"
                   "Akun Tarakapedia Anda sudah dibuat. Selesaikan langkah berikut sebelum memesan.\n\n"
                   + join_caption(missing))
        await ui.welcome_card(ev, name or "Pengguna", caption, join_markup(missing))
    else:
        await ui.show(ev, join_caption(missing), join_markup(missing))
    return True


class GateMiddleware(BaseMiddleware):
    """Semua transaksi hanya diproses untuk user yang sudah join kedua channel."""

    async def __call__(self, handler, event, data):
        u = getattr(event, "from_user", None)
        if u is None or u.id in ADMIN_IDS:
            return await handler(event, data)
        if getattr(event, "data", None) in SKIP_CALLBACKS:
            return await handler(event, data)
        if (getattr(event, "text", "") or "").strip().startswith(SKIP_COMMANDS):
            return await handler(event, data)
        if await gate(event):
            return
        return await handler(event, data)


async def on_leave(ev: ChatMemberUpdated, bot: Bot):
    """Saat bot melihat user keluar channel, langsung ingatkan untuk gabung lagi."""
    uid = getattr(getattr(ev.new_chat_member, "user", None), "id", None)
    if uid is None or uid in ADMIN_IDS:
        return
    chat = "@" + ev.chat.username if getattr(ev.chat, "username", None) else str(ev.chat.id)
    if _norm(chat) not in {_norm(x[1]) for x in CHANNELS}:
        return
    old = str(getattr(ev.old_chat_member, "status", "")).lower()
    new = str(getattr(ev.new_chat_member, "status", "")).lower()
    if old not in ALLOWED or new not in LEFT:
        return
    now = time.monotonic()
    if now - _last_prompt.get(uid, 0) < 60:
        return
    _last_prompt[uid] = now
    matched = next((c for c in CHANNELS if _norm(c[1]) == _norm(chat)), CHANNELS[0])
    missing = [(matched[0], chat, matched[2], new)]
    try:
        await bot.send_message(uid, join_caption(missing), reply_markup=join_markup(missing),
                               disable_web_page_preview=True)
    except Exception:
        pass
