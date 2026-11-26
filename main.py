import asyncio
import logging

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

import db
import ui
from config import ADMIN_IDS, BOT_TOKEN, DB_PATH
from handlers import admin, user
from providers import provider

log = logging.getLogger("tarakapedia")


class Guard(BaseMiddleware):
    """Daftarkan user otomatis, cek banned & mode maintenance."""

    async def __call__(self, handler, event, data):
        u = event.from_user
        if u is None:
            return await handler(event, data)
        data["is_new"] = await db.upsert_user(u.id, u.full_name, u.username)
        if u.id not in ADMIN_IDS:
            row = await db.get_user(u.id)
            msg = None
            if row["banned"]:
                msg = "🚫 Akun Anda diblokir. Hubungi admin."
            elif await db.setting("maintenance") == "1":
                msg = "🛠 Bot sedang maintenance. Silakan coba beberapa saat lagi."
            if msg:
                if isinstance(event, CallbackQuery):
                    await event.answer(msg, show_alert=True)
                else:
                    await event.answer(msg)
                return
        return await handler(event, data)


async def worker(bot: Bot):
    """Sinkronisasi status order dengan provider tiap 20 detik."""
    while True:
        try:
            for o in await db.q("SELECT * FROM orders WHERE status IN ('Pending','Processing')"):
                st = await provider.status(o)
                if st == o["status"]:
                    continue
                c = await db.x("UPDATE orders SET status=? WHERE id=? AND status=?", (st, o["id"], o["status"]))
                if c.rowcount and st == "Completed":
                    try:
                        await bot.send_message(o["user_id"], f"✅ Pesanan <code>#{o['id']}</code> "
                                                             f"({ui.esc(o['service_name'])}) telah <b>selesai</b>!")
                    except Exception:
                        pass
        except Exception:
            log.exception("worker error")
        await asyncio.sleep(20)


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN belum diisi di file .env")
    await db.init(DB_PATH)
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.outer_middleware(Guard())
    dp.callback_query.outer_middleware(Guard())
    dp.include_router(admin.router)
    dp.include_router(user.router)  # user paling akhir (ada fallback)
    me = await bot.me()
    log.info("Bot @%s berjalan", me.username)
    task = asyncio.create_task(worker(bot))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        task.cancel()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
