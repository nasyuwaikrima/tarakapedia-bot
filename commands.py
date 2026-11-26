"""Daftar Bot Commands Menu (Menu Button bawaan Telegram).

Bukan inline keyboard / reply keyboard: ini dikirim ke Telegram lewat
``set_my_commands`` supaya muncul di pojok kiri bawah dekat kolom ketik.
"""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (BotCommand, BotCommandScopeAllPrivateChats,
                           BotCommandScopeChat)

from config import ADMIN_IDS

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

ADMIN_COMMANDS = PUBLIC_COMMANDS + [
    BotCommand(command="admin", description="Buka panel admin"),
    BotCommand(command="users", description="Daftar semua user"),
]


async def setup(bot: Bot):
    """Pasang commands publik, lalu timpa dengan commands admin per chat admin."""
    await bot.set_my_commands(PUBLIC_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    for uid in ADMIN_IDS:
        try:
            await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=uid))
        except TelegramBadRequest:
            # Admin belum pernah chat ke bot — tidak masalah, daftar default tetap tampil.
            pass
