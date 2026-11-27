"""Daftar Bot Commands Menu (Menu Button bawaan Telegram).

Bukan inline keyboard / reply keyboard: ini dikirim ke Telegram lewat
``set_my_commands`` supaya muncul di pojok kiri bawah dekat kolom ketik.
"""

import json
import logging
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (BotCommand, BotCommandScopeAllChatAdministrators,
                           BotCommandScopeAllGroupChats,
                           BotCommandScopeAllPrivateChats, BotCommandScopeChat,
                           BotCommandScopeDefault)

from config import ADMIN_IDS, BASE_DIR

log = logging.getLogger("tarakapedia")

PUBLIC_COMMANDS = [
    BotCommand(command="start", description="Daftar & buka menu"),
    BotCommand(command="menu", description="Buka menu utama"),
    BotCommand(command="layanan", description="Order layanan termurah"),
    BotCommand(command="deposit", description="Deposit QRIS"),
    BotCommand(command="pesanan", description="Lihat pesanan saya"),
    BotCommand(command="riwayat", description="Riwayat transaksi"),
    BotCommand(command="profil", description="Profil & saldo"),
    BotCommand(command="referral", description="Kode referral"),
    BotCommand(command="toko", description="Toko aplikasi"),
    BotCommand(command="misi", description="Misi special"),
    BotCommand(command="top", description="Papan top transaksi"),
]

# Sengaja dipisah: scope publik tidak pernah memuat daftar ini.
ADMIN_ONLY_COMMANDS = [
    BotCommand(command="admin", description="Buka panel admin"),
    BotCommand(command="users", description="Daftar semua user"),
]

ADMIN_COMMANDS = PUBLIC_COMMANDS + ADMIN_ONLY_COMMANDS

# Telegram menyimpan scope lama di server. Kalau ADMIN_IDS diubah, scope chat
# lama tidak hilang dengan sendirinya — jadi simpan ID yang pernah dipasang
# supaya bisa dihapus saat startup berikutnya.
STATE_PATH = BASE_DIR / "data" / "applied_admin_commands.json"


def _load_applied() -> set[int]:
    try:
        data = json.loads(STATE_PATH.read_text())
        return {int(x) for x in data}
    except (OSError, ValueError, TypeError):
        return set()


def _save_applied(ids: set[int]) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(sorted(ids)))
    except OSError as e:
        log.warning("Gagal menyimpan state command admin: %s", e)


async def setup(bot: Bot):
    """Pasang commands publik, admin per chat, dan hapus scope admin lama."""
    admins = set(ADMIN_IDS)
    applied = _load_applied()

    # Bersihkan scope lama yang sudah bukan admin lagi.
    stale = applied - admins
    for uid in stale:
        try:
            await bot.delete_my_commands(scope=BotCommandScopeChat(chat_id=uid))
        except TelegramBadRequest:
            pass
    # Scope umum lain tidak dipakai bot ini; kosongkan untuk berjaga-jaga.
    for scope in (BotCommandScopeDefault(), BotCommandScopeAllGroupChats(),
                  BotCommandScopeAllChatAdministrators()):
        try:
            await bot.delete_my_commands(scope=scope)
        except TelegramBadRequest:
            pass

    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeAllPrivateChats())

    ok: set[int] = set()
    for uid in admins:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=uid))
            ok.add(uid)
        except TelegramBadRequest as e:
            # Admin belum pernah chat / ID tidak valid — daftar publik tetap tampil.
            log.warning("Command admin gagal dipasang untuk chat %s: %s", uid, e)

    _save_applied(admins)
    log.info("Bot Commands Menu: publik=%d command, admin chat=%s, dihapus=%s",
             len(PUBLIC_COMMANDS), sorted(ok), sorted(stale))
