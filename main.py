import asyncio
import logging
import time

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery

import db
import ui
from config import ADMIN_IDS, BOT_TOKEN, DB_PATH, PIXPAYZ_POLL_SECONDS
from handlers import admin, user
from payments import gateway
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


async def sync_catalog() -> int:
    if not provider.configured or await db.setting("auto_sync") != "1":
        return 0
    fav = await db.setting("service_fav") == "1"
    items = await provider.services(service_fav=fav)
    result = await db.sync_services(items)
    return result["total"]


async def poll_invoices(bot: Bot, offset: int = 0) -> int:
    """Cek invoice QRIS pending ke PixPayz (maks 20 per siklus, bergilir)."""
    rows = await db.q("SELECT * FROM deposits WHERE status='pending' AND invoice_id IS NOT NULL "
                      "AND invoice_id!='' ORDER BY id")
    if not rows:
        return 0
    for d in rows[offset:offset + 20]:
        invoice = d["invoice_id"]
        try:
            res = await gateway.check(invoice)
        except Exception:
            continue  # gagal sementara; siklus berikutnya mencoba lagi
        if gateway.is_paid(res["status"]):
            result = await db.confirm_deposit_by_invoice(invoice)
            if result:
                await ui.deposit_paid_notice(bot, result)
        elif gateway.is_expired(res["status"]):
            await db.expire_deposit_by_invoice(invoice)
    return (offset + 20) % len(rows)


async def worker(bot: Bot):
    """Sinkronisasi status order, refill, invoice QRIS, dan refresh katalog."""
    last_sync = time.monotonic()
    last_dep_poll = 0.0
    poll_offset = 0
    while True:
        try:
            if gateway.configured and time.monotonic() - last_dep_poll >= PIXPAYZ_POLL_SECONDS:
                try:
                    poll_offset = await poll_invoices(bot, poll_offset)
                except Exception:
                    log.exception("invoice poll error")
                last_dep_poll = time.monotonic()

            if provider.configured:
                active = await db.q("SELECT * FROM orders WHERE status IN ('Pending','Processing') "
                                    "AND provider_order_id IS NOT NULL AND provider_order_id!=''")
                ids = list(dict.fromkeys(o["provider_order_id"] for o in active))
                for i in range(0, len(ids), 50):
                    states = await provider.order_status(ids[i:i + 50])
                    for o in active:
                        st = states.get(str(o["provider_order_id"]))
                        if not st or st == o["status"]:
                            continue
                        c = await db.x("UPDATE orders SET status=?, checked_at=? WHERE id=? AND status=?",
                                       (st, db.now(), o["id"], o["status"]))
                        if c.rowcount and st == "Completed":
                            try:
                                await bot.send_message(o["user_id"], f"✅ Pesanan <code>#{o['id']}</code> "
                                                                     f"({ui.esc(o['service_name'])}) telah selesai!")
                            except Exception:
                                pass

                refills = await db.q("SELECT * FROM orders WHERE refill_id IS NOT NULL "
                                     "AND refill_status NOT IN ('Completed','Canceled')")
                for r in refills:
                    st = await provider.refill_status(r["refill_id"])
                    if st == r["refill_status"]:
                        continue
                    await db.x("UPDATE orders SET refill_status=?, checked_at=? WHERE id=?",
                               (st, db.now(), r["id"]))
                    try:
                        await bot.send_message(r["user_id"], f"🔁 Refill order <code>#{r['id']}</code>: <b>{ui.esc(st)}</b>")
                    except Exception:
                        pass

                if time.monotonic() - last_sync > 1800:
                    n = await sync_catalog()
                    if n:
                        log.info("Katalog provider disinkronisasi: %d layanan", n)
                    last_sync = time.monotonic()
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
    if provider.configured:
        try:
            n = await sync_catalog()
            log.info("Sinkron awal katalog: %d layanan", n)
        except Exception:
            log.warning("Gagal sinkron katalog saat start", exc_info=True)
    else:
        log.warning("Kredensial MedanPedia kosong — order real akan ditolak sampai .env diisi")
    if not gateway.configured:
        log.warning("API key PixPayz kosong — deposit QRIS belum bisa dibuat")
    me = await bot.me()
    log.info("Bot @%s berjalan", me.username)
    task = asyncio.create_task(worker(bot))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await gateway.close()
        await provider.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
