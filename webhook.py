"""Penerima webhook PixPayz (deposit.paid / deposit.expired).

Webhook dibalas 200 dengan cepat; proses database dilakukan langsung di sini
karena hanya satu UPDATE + notifikasi. Polling di main.py tetap ada sebagai
cadangan jika webhook belum bisa diakses dari internet.
"""
from __future__ import annotations

import logging

from aiohttp import web

import db
import ui
from config import PIXPAYZ_WEBHOOK_PATH, PIXPAYZ_WEBHOOK_PORT

log = logging.getLogger("tarakapedia.webhook")


async def handle(request: web.Request) -> web.Response:
    try:
        payload = await request.json()
    except Exception:
        return web.Response(status=400, text="invalid json")
    if not isinstance(payload, dict):
        return web.Response(status=400, text="invalid payload")
    data = payload.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    event = str(request.headers.get("X-Webhook-Event") or payload.get("event") or "").lower()
    status = str(data.get("status") or "").lower()
    invoice = str(data.get("reference") or data.get("id") or data.get("invoice_id")
                  or payload.get("invoice_id") or "")

    if invoice:
        if status == "paid" or event == "deposit.paid":
            result = await db.confirm_deposit_by_invoice(invoice)
            if result:
                await ui.deposit_paid_notice(request.app["bot"], result)
        elif status == "expired" or event == "deposit.expired":
            await db.expire_deposit_by_invoice(invoice)
    # Selalu balas 2xx agar PixPayz tidak retry, termasuk invoice yang sudah diproses.
    return web.Response(status=200, text="ok")


async def start(bot, port: int | None = None, path: str | None = None) -> web.AppRunner:
    app = web.Application()
    app["bot"] = bot
    app.router.add_post(path or PIXPAYZ_WEBHOOK_PATH, handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port or PIXPAYZ_WEBHOOK_PORT)
    await site.start()
    log.info("Webhook PixPayz aktif di 0.0.0.0:%s%s", port or PIXPAYZ_WEBHOOK_PORT,
             path or PIXPAYZ_WEBHOOK_PATH)
    return runner


async def stop(runner: web.AppRunner | None):
    if runner:
        await runner.cleanup()
