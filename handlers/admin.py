import asyncio
import re

from aiogram import F, Router
from aiogram.filters import BaseFilter, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message

import db
import ui
from config import ADMIN_IDS, DB_PATH
from ui import LINE, esc, kb, rp, show

router = Router()


class IsAdmin(BaseFilter):
    async def __call__(self, ev) -> bool:
        return bool(ev.from_user and ev.from_user.id in ADMIN_IDS)


router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class A(StatesGroup):
    find_user = State()
    bal = State()
    svc_add = State()
    svc_price = State()
    prd_add = State()
    stock_add = State()
    msn_add = State()
    set_edit = State()
    bc = State()


PANEL = [("⬅️ Panel Admin", "adm")]
CANCEL = kb([("❌ Batal", "adm")])


def toint(s: str) -> int:
    d = re.sub(r"\D", "", s or "")
    if not d:
        raise ValueError
    return int(d)


async def prompt(c, state, st, text, **data):
    await state.set_state(st)
    if data:
        await state.update_data(**data)
    await show(c, text, CANCEL)


# ---------- panel ----------
async def panel_text():
    s = await db.global_stats()
    return (f"{LINE}\n🛠 <b>PANEL ADMIN {esc(ui.BOT_NAME.upper())}</b>\n{LINE}\n\n"
            f"👥 User : <b>{ui.num(s['users'])}</b> (+{s['today_users']} hari ini)\n"
            f"🛒 Order : <b>{ui.num(s['orders'])}</b> • aktif {s['active_orders']}\n"
            f"💰 Omzet : <b>{rp(s['revenue'])}</b>\n"
            f"⏳ Deposit pending : <b>{s['pending_dep']}</b>")


def panel_kb():
    return kb(
        [("📊 Statistik", "adm:stats"), ("👥 Kelola User", "adm:usr")],
        [("🛒 Layanan", "adm:svc:0"), ("📱 Produk App", "adm:prd")],
        [("📦 Pesanan", "adm:ord"), ("💳 Deposit", "adm:dep")],
        [("🎯 Misi", "adm:msn"), ("⚙️ Pengaturan", "adm:set")],
        [("📢 Broadcast", "adm:bc"), ("💾 Backup DB", "adm:bak")],
        [("⬅️ Menu Utama", "menu")],
    )


@router.message(Command("admin"))
async def admin_cmd(m: Message, state: FSMContext):
    await state.clear()
    await m.answer(await panel_text(), reply_markup=panel_kb())


@router.callback_query(F.data == "adm")
async def admin_cb(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await show(c, await panel_text(), panel_kb())


@router.callback_query(F.data == "adm:stats")
async def stats(c: CallbackQuery):
    s = await db.global_stats()
    await show(c, f"{LINE}\n📊 <b>STATISTIK LENGKAP</b>\n{LINE}\n\n"
                  f"<b>Hari ini</b>\n├ User baru : {s['today_users']}\n├ Order : {s['today_orders']}\n└ Omzet : {rp(s['today_rev'])}\n\n"
                  f"<b>Total</b>\n├ User : {ui.num(s['users'])}\n├ Order : {ui.num(s['orders'])}\n├ Omzet : {rp(s['revenue'])}\n"
                  f"├ Total deposit : {rp(s['deposits'])}\n├ Saldo user beredar : {rp(s['balance'])}\n"
                  f"└ Uptime bot : {ui.uptime()}", kb([("🔄 Refresh", "adm:stats")], PANEL))


# ---------- user ----------
async def user_card(uid: int):
    u = await db.get_user(uid)
    if not u:
        return None, None
    refs = await db.referral_count(uid)
    t = (f"{LINE}\n👤 <b>USER</b> <code>{uid}</code>\n{LINE}\n\n├ Nama : {esc(u['name'] or '-')}\n"
         f"├ Username : {('@' + esc(u['username'])) if u['username'] else '-'}\n├ Saldo : <b>{rp(u['balance'])}</b>\n"
         f"├ Order : {u['total_order']} • belanja {rp(u['total_spent'])}\n├ Referral : {refs} • {rp(u['ref_earned'])}\n"
         f"├ Diundang oleh : {u['referred_by'] or '-'}\n├ Status : {'🚫 BANNED' if u['banned'] else '✅ Aktif'}\n"
         f"└ Bergabung : {u['joined_at']}")
    return t, kb([("➕ Saldo", f"adm:bal:+:{uid}"), ("➖ Saldo", f"adm:bal:-:{uid}")],
                 [("✅ Unban" if u["banned"] else "🚫 Ban", f"adm:ban:{uid}")], PANEL)


@router.callback_query(F.data == "adm:usr")
async def usr(c: CallbackQuery, state: FSMContext):
    await prompt(c, state, A.find_user, "👥 Kirim <b>ID Telegram</b> atau <b>@username</b> user:")


@router.message(A.find_user)
async def find_user(m: Message, state: FSMContext):
    s = (m.text or "").strip()
    row = (await db.get_user(int(s))) if s.isdigit() else await db.q1(
        "SELECT * FROM users WHERE LOWER(username)=?", (s.lstrip("@").lower(),))
    if not row:
        return await m.answer("⚠️ User tidak ditemukan. Kirim ulang atau /admin untuk keluar.")
    await state.clear()
    t, k = await user_card(row["id"])
    await m.answer(t, reply_markup=k)


@router.callback_query(F.data.startswith("adm:bal:"))
async def bal(c: CallbackQuery, state: FSMContext):
    _, _, sign, uid = c.data.split(":")
    await prompt(c, state, A.bal, f"💰 Kirim nominal untuk {'menambah' if sign == '+' else 'mengurangi'} saldo <code>{uid}</code>:",
                 sign=sign, uid=int(uid))


@router.message(A.bal)
async def bal_msg(m: Message, state: FSMContext):
    try:
        amt = toint(m.text)
    except ValueError:
        return await m.answer("⚠️ Nominal tidak valid.")
    d = await state.get_data()
    uid, sign = d["uid"], d["sign"]
    if sign == "+":
        await db.add_balance(uid, amt, "admin", "Penyesuaian admin")
    else:
        if not await db.debit(uid, amt, "admin", "Penyesuaian admin"):
            return await m.answer("⚠️ Saldo user tidak cukup.")
    await state.clear()
    try:
        await m.bot.send_message(uid, f"🛠 Saldo Anda {'bertambah' if sign == '+' else 'berkurang'} <b>{rp(amt)}</b> oleh admin.")
    except Exception:
        pass
    t, k = await user_card(uid)
    await m.answer("✅ Berhasil.\n\n" + t, reply_markup=k)


@router.callback_query(F.data.startswith("adm:ban:"))
async def ban(c: CallbackQuery):
    uid = int(c.data.split(":")[2])
    await db.x("UPDATE users SET banned = 1 - banned WHERE id=?", (uid,))
    t, k = await user_card(uid)
    await show(c, t, k)


# ---------- layanan ----------
@router.callback_query(F.data.startswith("adm:svc:"))
async def svc_list(c: CallbackQuery, state: FSMContext):
    await state.clear()
    page, per = int(c.data.split(":")[2]), 8
    rows = await db.q("SELECT * FROM services ORDER BY id")
    chunk = rows[page * per:(page + 1) * per]
    kr = [[(f"{'✅' if s['active'] else '⛔'} #{s['id']} {s['name'][:24]}", f"adm:sv:{s['id']}")] for s in chunk]
    nav = []
    if page > 0:
        nav.append(("◀️", f"adm:svc:{page - 1}"))
    if (page + 1) * per < len(rows):
        nav.append(("▶️", f"adm:svc:{page + 1}"))
    if nav:
        kr.append(nav)
    kr += [[("➕ Tambah Layanan", "adm:svadd")], PANEL]
    await show(c, f"{LINE}\n🛒 <b>KELOLA LAYANAN</b> ({len(rows)})\n{LINE}", kb(*kr))


@router.callback_query(F.data.startswith("adm:sv:"))
async def svc_detail(c: CallbackQuery):
    sid = int(c.data.split(":")[2])
    s = await db.q1("SELECT s.*, c.name cat FROM services s LEFT JOIN categories c ON c.id=s.category_id WHERE s.id=?", (sid,))
    if not s:
        return await c.answer("Tidak ditemukan.", show_alert=True)
    await show(c, f"📌 <b>#{s['id']} {esc(s['name'])}</b>\n\n├ Kategori : {esc(s['cat'] or '-')}\n"
                  f"├ Harga/1K : <b>{rp(s['price_per_1k'])}</b>\n├ Min/Max : {s['min_qty']} / {s['max_qty']}\n"
                  f"├ Status : {'✅ Aktif' if s['active'] else '⛔ Nonaktif'}\n└ {esc(s['description'] or '-')}",
               kb([("🔁 On/Off", f"adm:svt:{sid}"), ("💲 Ubah Harga", f"adm:svp:{sid}")],
                  [("🗑 Hapus", f"adm:svd:{sid}")], [("⬅️ Daftar", "adm:svc:0")]))


@router.callback_query(F.data.startswith("adm:svt:"))
async def svc_toggle(c: CallbackQuery):
    sid = int(c.data.split(":")[2])
    await db.x("UPDATE services SET active = 1 - active WHERE id=?", (sid,))
    await svc_detail(c)


@router.callback_query(F.data.startswith("adm:svd:"))
async def svc_delete(c: CallbackQuery):
    await db.x("DELETE FROM services WHERE id=?", (int(c.data.split(":")[2]),))
    await c.answer("Layanan dihapus.")
    await show(c, "🗑 Layanan dihapus.", kb([("⬅️ Daftar", "adm:svc:0")]))


@router.callback_query(F.data.startswith("adm:svp:"))
async def svc_price(c: CallbackQuery, state: FSMContext):
    sid = int(c.data.split(":")[2])
    await prompt(c, state, A.svc_price, f"💲 Kirim harga baru per 1000 untuk layanan #{sid}:", sid=sid)


@router.message(A.svc_price)
async def svc_price_msg(m: Message, state: FSMContext):
    try:
        p = toint(m.text)
    except ValueError:
        return await m.answer("⚠️ Angka tidak valid.")
    sid = (await state.get_data())["sid"]
    await db.x("UPDATE services SET price_per_1k=? WHERE id=?", (p, sid))
    await state.clear()
    await m.answer(f"✅ Harga layanan #{sid} jadi {rp(p)}/1K.", reply_markup=kb([("⬅️ Layanan", "adm:svc:0")]))


@router.callback_query(F.data == "adm:svadd")
async def svc_add(c: CallbackQuery, state: FSMContext):
    await prompt(c, state, A.svc_add,
                 "➕ <b>Tambah layanan</b> — satu baris per layanan:\n\n"
                 "<code>Kategori | Nama | Harga per 1K | Min | Max | Deskripsi</code>\n\n"
                 "Contoh:\n<code>Instagram | IG Followers Premium | 17000 | 100 | 10000 | Garansi 30 hari</code>")


@router.message(A.svc_add)
async def svc_add_msg(m: Message, state: FSMContext):
    ok, bad = 0, []
    for line in (m.text or "").splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in line.split("|")]
        try:
            cid = await db.get_or_create_category(p[0])
            await db.x("INSERT INTO services(category_id,name,price_per_1k,min_qty,max_qty,description) VALUES(?,?,?,?,?,?)",
                       (cid, p[1], toint(p[2]), toint(p[3]), toint(p[4]), p[5] if len(p) > 5 else ""))
            ok += 1
        except (ValueError, IndexError):
            bad.append(line)
    await state.clear()
    t = f"✅ {ok} layanan ditambahkan."
    if bad:
        t += f"\n⚠️ {len(bad)} baris gagal (format salah)."
    await m.answer(t, reply_markup=kb([("⬅️ Layanan", "adm:svc:0")]))


# ---------- produk ----------
@router.callback_query(F.data == "adm:prd")
async def prd_list(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ps = await db.q("SELECT p.*, (SELECT COUNT(*) FROM product_stock s WHERE s.product_id=p.id AND s.sold=0) stock FROM products p ORDER BY p.id")
    rows = [[(f"{'✅' if p['active'] else '⛔'} {p['name'][:22]} • stok {p['stock']}", f"adm:pr:{p['id']}")] for p in ps]
    rows += [[("➕ Tambah Produk", "adm:pradd")], PANEL]
    await show(c, f"{LINE}\n📱 <b>KELOLA PRODUK APP</b>\n{LINE}", kb(*rows))


@router.callback_query(F.data.startswith("adm:pr:"))
async def prd_detail(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = await db.q1("SELECT * FROM products WHERE id=?", (pid,))
    if not p:
        return await c.answer("Tidak ditemukan.", show_alert=True)
    st = await db.q1("SELECT SUM(sold=0) free, SUM(sold=1) sold FROM product_stock WHERE product_id=?", (pid,))
    await show(c, f"📦 <b>#{p['id']} {esc(p['name'])}</b>\n\n├ Harga : <b>{rp(p['price'])}</b>\n"
                  f"├ Stok : {st['free'] or 0} • Terjual : {st['sold'] or 0}\n"
                  f"├ Status : {'✅ Aktif' if p['active'] else '⛔ Nonaktif'}\n└ {esc(p['description'] or '-')}",
               kb([("➕ Tambah Stok", f"adm:prs:{pid}"), ("🔁 On/Off", f"adm:prt:{pid}")],
                  [("🗑 Hapus", f"adm:prd_del:{pid}")], [("⬅️ Daftar", "adm:prd")]))


@router.callback_query(F.data.startswith("adm:prt:"))
async def prd_toggle(c: CallbackQuery):
    await db.x("UPDATE products SET active = 1 - active WHERE id=?", (int(c.data.split(":")[2]),))
    await prd_detail(c)


@router.callback_query(F.data.startswith("adm:prd_del:"))
async def prd_delete(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    await db.x("DELETE FROM products WHERE id=?", (pid,))
    await db.x("DELETE FROM product_stock WHERE product_id=? AND sold=0", (pid,))
    await show(c, "🗑 Produk dihapus.", kb([("⬅️ Daftar", "adm:prd")]))


@router.callback_query(F.data == "adm:pradd")
async def prd_add(c: CallbackQuery, state: FSMContext):
    await prompt(c, state, A.prd_add, "➕ <b>Tambah produk</b>:\n\n<code>Nama | Harga | Deskripsi</code>\n\n"
                                      "Contoh:\n<code>Netflix 1 Bulan | 35000 | Garansi full</code>")


@router.message(A.prd_add)
async def prd_add_msg(m: Message, state: FSMContext):
    p = [x.strip() for x in (m.text or "").split("|")]
    try:
        cur = await db.x("INSERT INTO products(name,price,description) VALUES(?,?,?)",
                         (p[0], toint(p[1]), p[2] if len(p) > 2 else ""))
    except (ValueError, IndexError):
        return await m.answer("⚠️ Format salah. Coba lagi.")
    await state.clear()
    await m.answer("✅ Produk dibuat. Tambahkan stok sekarang:", reply_markup=kb([("➕ Tambah Stok", f"adm:prs:{cur.lastrowid}")], PANEL))


@router.callback_query(F.data.startswith("adm:prs:"))
async def stock_add(c: CallbackQuery, state: FSMContext):
    pid = int(c.data.split(":")[2])
    await prompt(c, state, A.stock_add, "➕ Kirim stok — <b>satu baris = satu item</b> (akun/link/kode):", pid=pid)


@router.message(A.stock_add)
async def stock_add_msg(m: Message, state: FSMContext):
    pid = (await state.get_data())["pid"]
    lines = [l.strip() for l in (m.text or "").splitlines() if l.strip()]
    for l in lines:
        await db.x("INSERT INTO product_stock(product_id,data) VALUES(?,?)", (pid, l))
    await state.clear()
    await m.answer(f"✅ {len(lines)} stok ditambahkan.", reply_markup=kb([("📦 Produk", f"adm:pr:{pid}")], PANEL))


# ---------- pesanan ----------
@router.callback_query(F.data == "adm:ord")
async def ord_list(c: CallbackQuery):
    rows = await db.q("SELECT * FROM orders ORDER BY id DESC LIMIT 10")
    kr = [[(f"{ui.STATUS_EMOJI.get(o['status'], '•')} #{o['id']} {o['service_name'][:20]} • {rp(o['price'])}", f"adm:od:{o['id']}")] for o in rows]
    kr += [[("🔄 Refresh", "adm:ord")], PANEL]
    await show(c, f"{LINE}\n📦 <b>PESANAN TERBARU</b>\n{LINE}", kb(*kr))


@router.callback_query(F.data.startswith("adm:od:"))
async def ord_detail_cb(c: CallbackQuery):
    await ord_detail(c, int(c.data.split(":")[2]))


async def ord_detail(c: CallbackQuery, oid: int):
    o = await db.q1("SELECT * FROM orders WHERE id=?", (oid,))
    if not o:
        return await c.answer("Tidak ditemukan.", show_alert=True)
    await show(c, f"📦 <b>Order #{o['id']}</b>\n\n├ User : <code>{o['user_id']}</code>\n├ Layanan : {esc(o['service_name'])}\n"
                  f"├ Target : <code>{esc(o['link'])}</code>\n├ Jumlah : {ui.num(o['quantity'])}\n├ Harga : {rp(o['price'])}\n"
                  f"├ Provider ID : {o['provider_order_id'] or '-'}\n├ Status : {ui.STATUS_EMOJI.get(o['status'], '')} {o['status']}\n"
                  f"└ {o['created_at']}",
               kb([("✅ Selesai", f"adm:os:{o['id']}:c"), ("⚙️ Proses", f"adm:os:{o['id']}:p")],
                  [("❌ Batalkan + Refund", f"adm:os:{o['id']}:x")], [("⬅️ Daftar", "adm:ord")]))


@router.callback_query(F.data.startswith("adm:os:"))
async def ord_status(c: CallbackQuery):
    _, _, oid, code = c.data.split(":")
    oid = int(oid)
    o = await db.q1("SELECT * FROM orders WHERE id=?", (oid,))
    if code == "x":
        if not await db.cancel_order(oid):
            return await c.answer("Order tidak bisa dibatalkan.", show_alert=True)
        msg = f"❌ Order <code>#{oid}</code> dibatalkan, saldo {rp(o['price'])} dikembalikan."
    else:
        new = "Completed" if code == "c" else "Processing"
        await db.x("UPDATE orders SET status=? WHERE id=? AND status NOT IN ('Canceled')", (new, oid))
        msg = f"{ui.STATUS_EMOJI[new]} Order <code>#{oid}</code> sekarang: <b>{ui.STATUS_ID[new]}</b>."
    try:
        await c.bot.send_message(o["user_id"], msg)
    except Exception:
        pass
    await ord_detail(c, oid)


# ---------- deposit ----------
@router.callback_query(F.data == "adm:dep")
async def dep_list(c: CallbackQuery):
    rows = await db.q("SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 10")
    kr = [[(f"#{d['id']} • {d['user_id']} • {rp(d['amount'])}", f"adm:dp:{d['id']}")] for d in rows]
    kr += [[("🔄 Refresh", "adm:dep")], PANEL]
    await show(c, f"{LINE}\n💳 <b>DEPOSIT PENDING</b> ({len(rows)})\n{LINE}", kb(*kr))


@router.callback_query(F.data.startswith("adm:dp:"))
async def dep_detail(c: CallbackQuery):
    d = await db.q1("SELECT * FROM deposits WHERE id=?", (int(c.data.split(":")[2]),))
    if not d:
        return await c.answer("Tidak ditemukan.", show_alert=True)
    await show(c, f"💳 <b>Deposit #{d['id']}</b>\n\n├ User : <code>{d['user_id']}</code>\n├ Nominal : <b>{rp(d['amount'])}</b>\n"
                  f"├ Metode : {d['method']}\n├ Ref : {d['ref']}\n├ Status : {d['status']}\n└ {d['created_at']}",
               kb([("✅ Setujui", f"adm:da:{d['id']}"), ("❌ Tolak", f"adm:dr:{d['id']}")], [("⬅️ Daftar", "adm:dep")]))


@router.callback_query(F.data.startswith("adm:da:"))
async def dep_approve(c: CallbackQuery):
    did = int(c.data.split(":")[2])
    res = await db.confirm_deposit(did)
    if not res:
        return await c.answer("Sudah diproses.", show_alert=True)
    d, ref, bonus = res
    try:
        await c.bot.send_message(d["user_id"], f"✅ Deposit <b>{rp(d['amount'])}</b> berhasil ditambahkan ke saldo.")
        if ref:
            await c.bot.send_message(ref, f"💸 Komisi referral <b>{rp(bonus)}</b> dari deposit downline.")
    except Exception:
        pass
    await show(c, f"✅ Deposit #{did} disetujui.", kb([("⬅️ Daftar", "adm:dep")]))


@router.callback_query(F.data.startswith("adm:dr:"))
async def dep_reject(c: CallbackQuery):
    did = int(c.data.split(":")[2])
    await db.x("UPDATE deposits SET status='rejected' WHERE id=? AND status='pending'", (did,))
    await show(c, f"❌ Deposit #{did} ditolak.", kb([("⬅️ Daftar", "adm:dep")]))


# ---------- misi ----------
@router.callback_query(F.data == "adm:msn")
async def msn_list(c: CallbackQuery, state: FSMContext):
    await state.clear()
    ms = await db.q("SELECT * FROM missions ORDER BY id")
    kr = [[(f"{'✅' if m['active'] else '⛔'} {m['title'][:22]} +{ui.num(m['reward'])}", f"adm:mt:{m['id']}"),
           ("🗑", f"adm:md:{m['id']}")] for m in ms]
    kr += [[("➕ Tambah Misi", "adm:msnadd")], PANEL]
    await show(c, f"{LINE}\n🎯 <b>KELOLA MISI</b>\n{LINE}\n\nKetuk nama untuk on/off, 🗑 untuk hapus.", kb(*kr))


@router.callback_query(F.data.startswith("adm:mt:"))
async def msn_toggle(c: CallbackQuery, state: FSMContext):
    await db.x("UPDATE missions SET active = 1 - active WHERE id=?", (int(c.data.split(":")[2]),))
    await msn_list(c, state)


@router.callback_query(F.data.startswith("adm:md:"))
async def msn_delete(c: CallbackQuery, state: FSMContext):
    await db.x("DELETE FROM missions WHERE id=?", (int(c.data.split(":")[2]),))
    await msn_list(c, state)


@router.callback_query(F.data == "adm:msnadd")
async def msn_add(c: CallbackQuery, state: FSMContext):
    await prompt(c, state, A.msn_add, "➕ <b>Tambah misi</b>:\n\n<code>Judul | tipe | target | hadiah</code>\n\n"
                                      "Tipe: <code>daily</code> (klaim harian), <code>orders</code> (jumlah order), "
                                      "<code>deposit</code> (total deposit Rp), <code>referral</code> (jumlah teman)\n\n"
                                      "Contoh:\n<code>Order 10 Kali | orders | 10 | 5000</code>")


@router.message(A.msn_add)
async def msn_add_msg(m: Message, state: FSMContext):
    p = [x.strip() for x in (m.text or "").split("|")]
    try:
        if p[1] not in ("daily", "orders", "deposit", "referral"):
            raise ValueError
        await db.x("INSERT INTO missions(title,type,target,reward) VALUES(?,?,?,?)",
                   (p[0], p[1], 1 if p[1] == "daily" else toint(p[2]), toint(p[3])))
    except (ValueError, IndexError):
        return await m.answer("⚠️ Format salah. Coba lagi.")
    await state.clear()
    await m.answer("✅ Misi ditambahkan.", reply_markup=kb([("🎯 Misi", "adm:msn")], PANEL))


# ---------- pengaturan ----------
SET_LABELS = {"ref_percent": "Komisi referral (%)", "ref_signup_bonus": "Bonus daftar referral (Rp)",
              "min_deposit": "Minimal deposit (Rp)", "announcement": "Pengumuman dashboard"}


async def settings_view(ev):
    mt = await db.setting("maintenance") == "1"
    t = f"{LINE}\n⚙️ <b>PENGATURAN</b>\n{LINE}\n\n🛠 Maintenance : <b>{'ON' if mt else 'OFF'}</b>\n"
    for k, lbl in SET_LABELS.items():
        t += f"├ {lbl} : <b>{esc(await db.setting(k) or '-')}</b>\n"
    rows = [[(f"🛠 Maintenance: {'matikan' if mt else 'aktifkan'}", "adm:setm")]]
    rows += [[(f"✏️ {lbl}", f"adm:sete:{k}")] for k, lbl in SET_LABELS.items()]
    rows.append(PANEL)
    await show(ev, t, kb(*rows))


@router.callback_query(F.data == "adm:set")
async def settings(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await settings_view(c)


@router.callback_query(F.data == "adm:setm")
async def set_maint(c: CallbackQuery):
    cur = await db.setting("maintenance")
    await db.set_setting("maintenance", "0" if cur == "1" else "1")
    await settings_view(c)


@router.callback_query(F.data.startswith("adm:sete:"))
async def set_edit(c: CallbackQuery, state: FSMContext):
    key = c.data.split(":")[2]
    extra = "\n(kirim <code>-</code> untuk mengosongkan)" if key == "announcement" else ""
    await prompt(c, state, A.set_edit, f"✏️ Kirim nilai baru untuk <b>{SET_LABELS[key]}</b>:{extra}", key=key)


@router.message(A.set_edit)
async def set_edit_msg(m: Message, state: FSMContext):
    key = (await state.get_data())["key"]
    val = (m.text or "").strip()
    if key == "announcement":
        val = "" if val == "-" else val[:500]
    else:
        try:
            val = str(toint(val))
        except ValueError:
            return await m.answer("⚠️ Harus angka.")
    await db.set_setting(key, val)
    await state.clear()
    await m.answer("✅ Tersimpan.", reply_markup=kb([("⚙️ Pengaturan", "adm:set")], PANEL))


# ---------- broadcast ----------
@router.callback_query(F.data == "adm:bc")
async def bc(c: CallbackQuery, state: FSMContext):
    await prompt(c, state, A.bc, "📢 Kirim pesan broadcast (boleh format HTML: <code>&lt;b&gt;tebal&lt;/b&gt;</code>):")


@router.message(A.bc)
async def bc_preview(m: Message, state: FSMContext):
    await state.update_data(text=m.html_text)
    await state.set_state(None)
    await m.answer(f"👀 <b>Preview:</b>\n\n{m.html_text}", reply_markup=kb([("🚀 Kirim ke Semua", "adm:bcgo")], [("❌ Batal", "adm")]))


@router.callback_query(F.data == "adm:bcgo")
async def bc_go(c: CallbackQuery, state: FSMContext):
    text = (await state.get_data()).get("text")
    if not text:
        return await c.answer("Tidak ada pesan.", show_alert=True)
    await state.clear()
    await show(c, "⏳ Mengirim broadcast...")
    users = await db.q("SELECT id FROM users WHERE banned=0")
    ok = fail = 0
    for u in users:
        try:
            await c.bot.send_message(u["id"], text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await c.message.answer(f"✅ Broadcast selesai.\nTerkirim: <b>{ok}</b> • Gagal: <b>{fail}</b>", reply_markup=kb(PANEL))


# ---------- backup ----------
@router.callback_query(F.data == "adm:bak")
async def backup(c: CallbackQuery):
    await db.checkpoint()
    await c.message.answer_document(FSInputFile(DB_PATH), caption=f"💾 Backup database {db.now()} WIB")
    await c.answer("Backup dikirim.")
