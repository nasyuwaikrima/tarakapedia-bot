import math
import re

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import db
import ui
from config import BOT_NAME
from payments import gateway
from providers import LABEL_FIELDS, needs_quantity, provider, type_fields
from ui import BACK, LINE, answer_cb, esc, kb, rp, show

router = Router()


class S(StatesGroup):
    dep_custom = State()
    ord_link = State()
    ord_qty = State()
    ord_extra = State()
    ord_confirm = State()


async def _menu(ev, state: FSMContext | None = None):
    if state:
        await state.clear()
    uid = ev.from_user.id
    await ui.show_menu(ev, await ui.menu_caption(uid), ui.main_kb(uid))


# ---------- start / menu ----------
@router.message(CommandStart())
async def start(m: Message, command: CommandObject, state: FSMContext, is_new: bool = False):
    await state.clear()
    a = command.args or ""
    if is_new and a.startswith("ref_") and a[4:].isdigit():
        ref = int(a[4:])
        bonus = await db.set_referrer(m.from_user.id, ref)
        if bonus is not None:
            try:
                await m.bot.send_message(
                    ref, f"🎉 <b>Referral baru!</b>\n{esc(m.from_user.full_name)} bergabung lewat link Anda.\n"
                         f"💰 Bonus: <b>{rp(bonus)}</b>")
            except Exception:
                pass
    await _menu(m)


@router.message(Command("menu"))
async def menu_cmd(m: Message, state: FSMContext):
    await _menu(m, state)


@router.callback_query(F.data == "menu")
async def menu_cb(c: CallbackQuery, state: FSMContext):
    await _menu(c, state)


# ---------- deposit ----------
@router.callback_query(F.data == "dep")
async def dep_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    mn = int(await db.setting("min_deposit") or 0)
    amts = [10000, 25000, 50000, 100000, 250000, 500000]
    rows = [[(rp(a), f"dep:a:{a}") for a in amts[i:i + 2]] for i in range(0, len(amts), 2)]
    rows += [[("✏️ Nominal Lain", "dep:custom")], BACK]
    await show(c, f"{LINE}\n💰 <b>DEPOSIT SALDO</b>\n{LINE}\n\nMinimal deposit: <b>{rp(mn)}</b>\n"
                  f"Metode: <b>{gateway.name}</b>\n\nPilih nominal deposit:", kb(*rows))


async def _make_deposit(ev, uid: int, amount: int):
    mn = int(await db.setting("min_deposit") or 0)
    if amount < mn:
        return await show(ev, f"⚠️ Minimal deposit {rp(mn)}.", kb([("⬅️ Kembali", "dep")]))
    did = await db.create_deposit(uid, amount, gateway.name)
    info = await gateway.create(did, amount)
    await db.x("UPDATE deposits SET ref=? WHERE id=?", (info["ref"], did))
    rows = []
    if gateway.demo:
        rows.append([("✅ Bayar (Demo)", f"dep:pay:{did}")])
    rows.append([("❌ Batalkan", f"dep:cx:{did}")])
    await show(ev, f"{LINE}\n🧾 <b>TAGIHAN DEPOSIT</b>\n{LINE}\n\n"
                   f"├ ID : <code>#{did}</code>\n├ Ref : <code>{info['ref']}</code>\n"
                   f"├ Nominal : <b>{rp(amount)}</b>\n└ Status : 🕒 Menunggu pembayaran\n\n{info['instructions']}",
               kb(*rows))


@router.callback_query(F.data.startswith("dep:a:"))
async def dep_amount(c: CallbackQuery):
    await _make_deposit(c, c.from_user.id, int(c.data.split(":")[2]))


@router.callback_query(F.data == "dep:custom")
async def dep_custom(c: CallbackQuery, state: FSMContext):
    await state.set_state(S.dep_custom)
    await show(c, "✏️ Kirim nominal deposit (angka saja), contoh: <code>75000</code>", kb([("❌ Batal", "dep")]))


@router.message(S.dep_custom)
async def dep_custom_msg(m: Message, state: FSMContext):
    digits = re.sub(r"\D", "", m.text or "")
    if not digits or int(digits) > 10_000_000:
        return await m.answer("⚠️ Nominal tidak valid (maks Rp 10.000.000). Coba lagi.")
    await state.clear()
    await _make_deposit(m, m.from_user.id, int(digits))


@router.callback_query(F.data.startswith("dep:pay:"))
async def dep_pay(c: CallbackQuery):
    if not gateway.demo:
        return await c.answer("Tidak tersedia.", show_alert=True)
    did = int(c.data.split(":")[2])
    d = await db.q1("SELECT * FROM deposits WHERE id=? AND user_id=?", (did, c.from_user.id))
    if not d:
        return await c.answer("Tagihan tidak ditemukan.", show_alert=True)
    res = await db.confirm_deposit(did)
    if not res:
        return await c.answer("Tagihan sudah diproses.", show_alert=True)
    d, ref, bonus = res
    u = await db.get_user(c.from_user.id)
    await show(c, f"✅ <b>Deposit Berhasil!</b>\n\n├ Nominal : <b>{rp(d['amount'])}</b>\n└ Saldo : <b>{rp(u['balance'])}</b>",
               kb([("🛒 Order Layanan", "ord")], BACK))
    if ref:
        try:
            await c.bot.send_message(ref, f"💸 Komisi referral <b>{rp(bonus)}</b> dari deposit downline Anda.")
        except Exception:
            pass
    await ui.notify_admins(c.bot, f"💰 Deposit demo #{did} dari <code>{c.from_user.id}</code>: {rp(d['amount'])}")


@router.callback_query(F.data.startswith("dep:cx:"))
async def dep_cancel(c: CallbackQuery):
    did = int(c.data.split(":")[2])
    await db.x("UPDATE deposits SET status='canceled' WHERE id=? AND user_id=? AND status='pending'",
               (did, c.from_user.id))
    await show(c, "❌ Tagihan dibatalkan.", kb(BACK))


# ---------- order layanan (provider real) ----------
TYPE_LABELS = {
    "default": "Default", "package": "Paket", "custom_comment": "Komentar Custom",
    "comment_likes": "Like Komentar", "mention_list": "Mention List",
    "mention_hashtag": "Mention Hashtag", "mention_follower": "Mention Followers",
    "mention_media": "Mention Media Likers", "poll": "Poll",
    "comment_reply": "Balasan Komentar", "comment_live": "Komentar Live",
}

SAMPLES = {
    "comments": "komentar pertama\nkomentar kedua",
    "usernames": "user_satu\nuser_dua",
    "hashtag": "instagood",
    "username": "sebastianwirajaya11",
    "media": "https://www.instagram.com/p/xxxxx/",
}


async def _billable(d: dict, s) -> int:
    """Satuan tagihan: jumlah, jumlah baris komentar/username, atau 1 paket."""
    qty = int(d.get("qty") or 0)
    if qty:
        return qty
    extra = d.get("extra") or {}
    for key in ("comments", "usernames"):
        if extra.get(key):
            return max(1, len([line for line in extra[key].splitlines() if line.strip()]))
    return 1000 if s["provider_type"] == "package" else 1


async def _harga(d: dict, s) -> int:
    return math.ceil(await db.effective_price(s) * await _billable(d, s) / 1000)


async def _konfirmasi(ev, state: FSMContext, s, d: dict):
    price = await _harga(d, s)
    u = await db.get_user(ev.from_user.id)
    t = (f"{LINE}\n🧾 <b>KONFIRMASI PESANAN</b>\n{LINE}\n\n"
         f"├ Layanan : <b>{esc(s['name'])}</b>\n"
         f"├ Tipe : {TYPE_LABELS.get(s['provider_type'], s['provider_type'])}\n"
         f"├ Target : <code>{esc(d['link'])}</code>\n")
    if d.get("qty"):
        t += f"├ Jumlah : <b>{ui.num(d['qty'])}</b>\n"
    for k, v in (d.get("extra") or {}).items():
        t += f"├ {esc(LABEL_FIELDS.get(k, k)).capitalize()} : <code>{esc(v[:160])}</code>\n"
    t += f"├ Harga : <b>{rp(price)}</b>\n└ Saldo Anda : {rp(u['balance'])}"
    await state.set_state(S.ord_confirm)
    await ev.answer(t, reply_markup=kb([("✅ Konfirmasi", "ord:ok"), ("❌ Batal", "menu")]))


async def _lanjut(ev, state: FSMContext, s, d: dict):
    """Langkah berikutnya mengikuti tipe layanan provider."""
    fields = type_fields(s["provider_type"])
    if needs_quantity(s["provider_type"]) and not d.get("qty"):
        await state.set_state(S.ord_qty)
        return await ev.answer(f"🔢 Kirim <b>jumlah</b> (min {ui.num(s['min_qty'])} — maks {ui.num(s['max_qty'])}):")
    if fields and not (d.get("extra") or {}).get(fields[0]):
        await state.set_state(S.ord_extra)
        sample = SAMPLES.get(fields[0])
        hint = f"\nContoh:\n<code>{esc(sample)}</code>" if sample else ""
        return await ev.answer(f"✍️ Kirim <b>{esc(LABEL_FIELDS.get(fields[0], fields[0]))}</b>.{hint}")
    await _konfirmasi(ev, state, s, d)


@router.callback_query(F.data == "ord")
async def ord_cats(c: CallbackQuery, state: FSMContext):
    await state.clear()
    cats = await db.q("SELECT c.* FROM categories c WHERE EXISTS "
                      "(SELECT 1 FROM services s WHERE s.category_id=c.id AND s.active=1) ORDER BY c.id")
    if not cats:
        return await show(c, "Belum ada layanan tersedia. Admin bisa sinkron lewat Panel Admin → Provider API.",
                          kb(BACK))
    rows = [[(f"{x['emoji']} {x['name']}", f"ord:c:{x['id']}:0") for x in cats[i:i + 2]]
            for i in range(0, len(cats), 2)]
    rows.append(BACK)
    await show(c, f"{LINE}\n🛒 <b>ORDER LAYANAN</b>\n{LINE}\n\nPilih kategori layanan:", kb(*rows))


@router.callback_query(F.data.startswith("ord:c:"))
async def ord_cat(c: CallbackQuery):
    _, _, cid, page = c.data.split(":")
    cid, page, per = int(cid), int(page), 6
    cat = await db.q1("SELECT * FROM categories WHERE id=?", (cid,))
    svcs = await db.q("SELECT * FROM services WHERE category_id=? AND active=1 ORDER BY id", (cid,))
    chunk = svcs[page * per:(page + 1) * per]
    rows = []
    for s in chunk:
        rows.append([(f"{s['name'][:26]} • {rp(await db.effective_price(s))}/1K", f"ord:s:{s['id']}")])
    nav = []
    if page > 0:
        nav.append(("◀️", f"ord:c:{cid}:{page - 1}"))
    if (page + 1) * per < len(svcs):
        nav.append(("▶️", f"ord:c:{cid}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Kategori", "ord")])
    await show(c, f"{LINE}\n{cat['emoji']} <b>{esc(cat['name'].upper())}</b>\n{LINE}\n\nPilih layanan:", kb(*rows))


@router.callback_query(F.data.startswith("ord:s:"))
async def ord_service(c: CallbackQuery):
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (int(c.data.split(":")[2]),))
    if not s:
        return await answer_cb(c, "Layanan tidak tersedia.", True)
    await show(c, f"{LINE}\n📌 <b>{esc(s['name'])}</b>\n{LINE}\n\n"
                  f"├ Tipe : {TYPE_LABELS.get(s['provider_type'], s['provider_type'])}\n"
                  f"├ Harga : <b>{rp(await db.effective_price(s))}</b> / 1000\n"
                  f"├ Min : {ui.num(s['min_qty'])} • Max : {ui.num(s['max_qty'])}\n"
                  f"├ Garansi : {'✅ Refill' if s['provider_refill'] else '❌ Tanpa refill'}\n"
                  f"└ {esc(s['description'] or s['provider_avg'] or 'Proses otomatis')}",
               kb([("🛒 Pesan Sekarang", f"ord:go:{s['id']}")], [("⬅️ Kembali", f"ord:c:{s['category_id']}:0")]))


@router.callback_query(F.data.startswith("ord:go:"))
async def ord_go(c: CallbackQuery, state: FSMContext):
    sid = int(c.data.split(":")[2])
    await state.set_state(S.ord_link)
    await state.update_data(sid=sid, extra={})
    await show(c, "🔗 Kirim <b>link / username target</b> pesanan Anda:", kb([("❌ Batal", "menu")]))


@router.message(S.ord_link)
async def ord_link(m: Message, state: FSMContext):
    link = (m.text or "").strip()
    if len(link) < 3 or len(link) > 300:
        return await m.answer("⚠️ Link tidak valid, kirim ulang.")
    d = await state.get_data()
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (d.get("sid"),))
    if not s:
        return await _menu(m, state)
    d["link"] = link
    await state.update_data(link=link)
    await _lanjut(m, state, s, d)


@router.message(S.ord_qty)
async def ord_qty(m: Message, state: FSMContext):
    d = await state.get_data()
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (d.get("sid"),))
    if not s:
        return await _menu(m, state)
    digits = re.sub(r"\D", "", m.text or "")
    if not digits or not (s["min_qty"] <= int(digits) <= s["max_qty"]):
        return await m.answer(f"⚠️ Jumlah harus {ui.num(s['min_qty'])} — {ui.num(s['max_qty'])}.")
    d["qty"] = int(digits)
    await state.update_data(qty=d["qty"])
    await _lanjut(m, state, s, d)


@router.message(S.ord_extra)
async def ord_extra(m: Message, state: FSMContext):
    d = await state.get_data()
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (d.get("sid"),))
    if not s:
        return await _menu(m, state)
    fields = type_fields(s["provider_type"])
    val = (m.text or "").strip()
    if fields[0] in ("comments", "usernames") and not [x for x in val.splitlines() if x.strip()]:
        return await m.answer("⚠️ Isi minimal satu baris. Coba lagi.")
    extra = dict(d.get("extra") or {})
    extra[fields[0]] = val[:3000]
    d["extra"] = extra
    await state.update_data(extra=extra)
    await _lanjut(m, state, s, d)


@router.callback_query(F.data == "ord:ok", StateFilter(S.ord_confirm))
async def ord_ok(c: CallbackQuery, state: FSMContext):
    d = await state.get_data()
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (d.get("sid"),))
    if not s:
        return await _menu(c, state)
    if not s["provider_id"]:
        await state.clear()
        return await show(c, "⚠️ Layanan ini belum terhubung ke provider. Hubungi admin.", kb(BACK))
    extra = d.get("extra") or {}
    qty = d.get("qty")
    price = await _harga(d, s)
    oid = await db.create_order(c.from_user.id, s, d["link"], qty or 0, price, extra)
    if oid is None:
        await state.clear()
        return await show(c, "⚠️ <b>Saldo tidak cukup.</b> Silakan deposit dulu.",
                          kb([("💰 Deposit Saldo", "dep")], BACK))
    await state.clear()
    try:
        pid = await provider.order(int(s["provider_id"]), d["link"], quantity=qty,
                                   ptype=s["provider_type"], **extra)
    except Exception as e:
        await db.cancel_order(oid)
        return await show(c, f"⚠️ Provider gagal: {esc(str(e)[:150])}.\nSaldo Anda dikembalikan.", kb(BACK))
    await db.x("UPDATE orders SET provider_order_id=? WHERE id=?", (pid, oid))
    u = await db.get_user(c.from_user.id)
    await show(c, f"✅ <b>Pesanan Berhasil Dibuat!</b>\n\n├ Order ID : <code>#{oid}</code>\n"
                  f"├ ID Provider : <code>{esc(pid)}</code>\n"
                  f"├ Layanan : {esc(s['name'])}\n├ Harga : {rp(price)}\n"
                  f"└ Sisa Saldo : <b>{rp(u['balance'])}</b>", kb([("📦 Pesanan Saya", "myord")], BACK))
    await ui.notify_admins(c.bot, f"🛒 Order baru <code>#{oid}</code> dari <code>{c.from_user.id}</code>\n"
                                  f"{esc(s['name'])} • {rp(price)} • provider <code>{esc(pid)}</code>")


# ---------- toko aplikasi ----------
@router.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    ps = await db.q("SELECT p.*, (SELECT COUNT(*) FROM product_stock s WHERE s.product_id=p.id AND s.sold=0) stock "
                    "FROM products p WHERE p.active=1 ORDER BY p.id")
    if not ps:
        return await show(c, "Belum ada produk.", kb(BACK))
    rows = [[(f"{p['name'][:26]} • {rp(p['price'])}", f"shop:p:{p['id']}")] for p in ps]
    rows += [[("🗂 Pembelian Saya", "shop:my")], BACK]
    await show(c, f"{LINE}\n📱 <b>TOKO APLIKASI</b>\n{LINE}\n\nPilih produk digital:", kb(*rows))


@router.callback_query(F.data.startswith("shop:p:"))
async def shop_product(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = await db.q1("SELECT * FROM products WHERE id=? AND active=1", (pid,))
    if not p:
        return await c.answer("Produk tidak tersedia.", show_alert=True)
    stock = (await db.q1("SELECT COUNT(*) n FROM product_stock WHERE product_id=? AND sold=0", (pid,)))["n"]
    rows = [[("🛒 Beli Sekarang", f"shop:buy:{pid}")]] if stock else []
    rows.append([("⬅️ Kembali", "shop")])
    await show(c, f"{LINE}\n📦 <b>{esc(p['name'])}</b>\n{LINE}\n\n├ Harga : <b>{rp(p['price'])}</b>\n"
                  f"├ Stok : <b>{stock}</b>\n└ {esc(p['description'] or '-')}", kb(*rows))


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(c: CallbackQuery):
    ok, data, p = await db.buy_product(c.from_user.id, int(c.data.split(":")[2]))
    if not ok:
        rows = [[("💰 Deposit Saldo", "dep")]] if "Saldo" in data else []
        return await show(c, f"⚠️ {data}", kb(*rows, [("⬅️ Toko", "shop")]))
    u = await db.get_user(c.from_user.id)
    await show(c, f"✅ <b>Pembelian Berhasil!</b>\n\n📦 {esc(p['name'])}\n💸 {rp(p['price'])}\n\n"
                  f"🔐 <b>Data produk:</b>\n<code>{esc(data)}</code>\n\nSisa saldo: <b>{rp(u['balance'])}</b>",
               kb([("📱 Toko", "shop")], BACK))
    await ui.notify_admins(c.bot, f"📱 Pembelian <b>{esc(p['name'])}</b> oleh <code>{c.from_user.id}</code> ({rp(p['price'])})")


@router.callback_query(F.data == "shop:my")
async def shop_my(c: CallbackQuery):
    rows = await db.q("SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 5", (c.from_user.id,))
    t = f"{LINE}\n🗂 <b>PEMBELIAN SAYA</b>\n{LINE}\n\n"
    t += "\n\n".join(f"📦 <b>{esc(r['name'])}</b> • {rp(r['price'])}\n<code>{esc(r['data'])}</code>\n<i>{r['created_at']}</i>"
                     for r in rows) or "Belum ada pembelian."
    await show(c, t, kb([("⬅️ Toko", "shop")]))


# ---------- pesanan / riwayat / profil ----------
@router.callback_query(F.data == "myord")
async def my_orders(c: CallbackQuery):
    rows = await db.q("SELECT o.*, COALESCE(s.provider_refill,0) pr FROM orders o "
                      "LEFT JOIN services s ON s.id=o.service_id "
                      "WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (c.from_user.id,))
    t = f"{LINE}\n📦 <b>PESANAN SAYA</b>\n{LINE}\n\n"
    kr = []
    for o in rows:
        t += (f"{ui.STATUS_EMOJI.get(o['status'], '•')} <b>#{o['id']}</b> {esc(o['service_name'])}\n"
              f"   {ui.num(o['quantity']) or '-'} • {rp(o['price'])} • {ui.STATUS_ID.get(o['status'], o['status'])}\n")
        if o["provider_order_id"]:
            t += f"   Provider: <code>{esc(o['provider_order_id'])}</code>\n"
        if o["refill_id"]:
            t += f"   Refill: <code>{esc(o['refill_id'])}</code> • {esc(o['refill_status'] or 'Menunggu')}\n"
        t += f"   <i>{o['created_at']}</i>\n\n"
        if o["provider_order_id"] and o["pr"]:
            label = f"📊 Cek Refill #{o['id']}" if o["refill_id"] else f"🔁 Refill #{o['id']}"
            kr.append([(label, f"ord:refill:{o['id']}")])
    if not rows:
        t += "Belum ada pesanan."
    kr += [[("🔄 Refresh", "myord")], BACK]
    await show(c, t, kb(*kr))


@router.callback_query(F.data.startswith("ord:refill:"))
async def ord_refill(c: CallbackQuery):
    oid = int(c.data.split(":")[2])
    o = await db.q1("SELECT * FROM orders WHERE id=? AND user_id=?", (oid, c.from_user.id))
    if not o or not o["provider_order_id"]:
        return await answer_cb(c, "Order tidak ditemukan.", True)
    try:
        if o["refill_id"]:
            st = await provider.refill_status(o["refill_id"])
            await db.x("UPDATE orders SET refill_status=?, checked_at=? WHERE id=?", (st, db.now(), oid))
            msg = f"📊 Refill <code>{esc(o['refill_id'])}</code>: <b>{esc(st)}</b>"
        else:
            rid = await provider.refill(o["provider_order_id"])
            await db.x("UPDATE orders SET refill_id=?, refill_status='Pending', checked_at=? WHERE id=?",
                       (rid, db.now(), oid))
            msg = f"✅ Refill diajukan • ID <code>{esc(rid)}</code>"
    except Exception as e:
        msg = f"⚠️ Gagal: {esc(str(e)[:150])}"
    await answer_cb(c, msg, True)
    await my_orders(c)


@router.callback_query(F.data == "hist")
async def history(c: CallbackQuery):
    rows = await db.q("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 15", (c.from_user.id,))
    icons = {"deposit": "💰", "order": "🛒", "purchase": "📱", "refund": "↩️", "referral": "🎁", "mission": "🎯", "admin": "🛠"}
    t = f"{LINE}\n🧾 <b>RIWAYAT TRANSAKSI</b>\n{LINE}\n\n"
    if rows:
        t += "\n".join(f"{icons.get(r['type'], '•')} {'+' if r['amount'] > 0 else '-'}{rp(abs(r['amount']))} "
                       f"— {esc(r['note'] or r['type'])}\n   <i>{r['created_at']}</i>" for r in rows)
    else:
        t += "Belum ada transaksi."
    await show(c, t, kb(BACK))


@router.callback_query(F.data == "prof")
async def profile(c: CallbackQuery):
    u = await db.get_user(c.from_user.id)
    refs = await db.referral_count(u["id"])
    await show(c, f"{LINE}\n👤 <b>PROFIL SAYA</b>\n{LINE}\n\n├ Nama : <b>{esc(u['name'] or '-')}</b>\n"
                  f"├ ID : <code>{u['id']}</code>\n├ Saldo : <b>{rp(u['balance'])}</b>\n"
                  f"├ Total Order : {ui.num(u['total_order'])}\n├ Total Belanja : {rp(u['total_spent'])}\n"
                  f"├ Referral : {refs} teman • {rp(u['ref_earned'])}\n└ Bergabung : {u['joined_at']} WIB",
               kb([("💰 Deposit", "dep"), ("🧾 Riwayat", "hist")], BACK))


# ---------- referral ----------
@router.callback_query(F.data == "ref")
async def referral(c: CallbackQuery):
    me = await c.bot.me()
    u = await db.get_user(c.from_user.id)
    refs = await db.referral_count(u["id"])
    pct = await db.setting("ref_percent")
    bonus = int(await db.setting("ref_signup_bonus") or 0)
    link = f"https://t.me/{me.username}?start=ref_{u['id']}"
    await show(c, f"{LINE}\n🎁 <b>PROGRAM REFERRAL</b>\n{LINE}\n\n"
                  f"Ajak teman &amp; dapatkan:\n├ Bonus daftar : <b>{rp(bonus)}</b>\n└ Komisi deposit : <b>{pct}%</b> seumur hidup\n\n"
                  f"🔗 Link Anda:\n<code>{link}</code>\n\n"
                  f"📈 Teman diundang : <b>{refs}</b>\n💰 Total pendapatan : <b>{rp(u['ref_earned'])}</b>",
               kb([("📤 Bagikan Link", f"https://t.me/share/url?url={link}&text=Order%20sosmed%20murah%20di%20{BOT_NAME}")], BACK))


# ---------- misi ----------
@router.callback_query(F.data == "msn")
async def missions(c: CallbackQuery):
    ms = await db.q("SELECT * FROM missions WHERE active=1 ORDER BY id")
    t = f"{LINE}\n🎯 <b>MISI SPECIAL</b>\n{LINE}\n\n"
    rows = []
    for m in ms:
        prog, claimed = await db.mission_state(c.from_user.id, m)
        done = prog >= m["target"]
        if m["type"] == "deposit":
            pt = f"{rp(min(prog, m['target']))} / {rp(m['target'])}"
        else:
            pt = f"{min(prog, m['target'])} / {m['target']}"
        state = "✅ Diklaim" if claimed else ("🎉 Siap diklaim" if done else "⏳ Berjalan")
        t += f"<b>{esc(m['title'])}</b>\n{ui.bar(prog, m['target'])} {pt}\n🎁 {rp(m['reward'])} • {state}\n\n"
        if done and not claimed:
            rows.append([(f"🎁 Klaim: {m['title'][:24]} (+{rp(m['reward'])})", f"msn:claim:{m['id']}")])
    if not ms:
        t += "Belum ada misi aktif."
    rows.append(BACK)
    await show(c, t, kb(*rows))


@router.callback_query(F.data.startswith("msn:claim:"))
async def claim(c: CallbackQuery):
    ok, info, reward = await db.claim_mission(c.from_user.id, int(c.data.split(":")[2]))
    if not ok:
        await c.answer(info, show_alert=True)
    else:
        await c.answer(f"🎉 +{rp(reward)} masuk ke saldo!", show_alert=True)
    await missions(c)


# ---------- fallback ----------
@router.message(StateFilter(None))
async def fallback(m: Message):
    await m.answer("Gunakan menu di bawah 👇", reply_markup=ui.main_kb(m.from_user.id))
