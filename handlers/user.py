import math
import re

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.enums import ChatType
from aiogram.types import CallbackQuery, ChatMemberUpdated, Message

import channels
import db
import limits
import ui
from config import ADMIN_IDS, BOT_NAME, MAX_ACTIVE_DEPOSITS
from payments import gateway
from providers import LABEL_FIELDS, needs_quantity, provider, type_fields
from ui import BACK, answer_cb, esc, kb, rp, show, tree

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
    if is_new and m.from_user.id not in ADMIN_IDS:
        ref_line = ""
        if a.startswith("ref_") and a[4:].isdigit():
            ref = await db.get_user(int(a[4:]))
            ref_line = f"\n🎁 Ref: {ui.public_user(int(a[4:]), ref['name'] if ref else None, ref['username'] if ref else None)}"
        await ui.log_new_member(m.bot, m.from_user.id, m.from_user.full_name,
                                m.from_user.username, ref_line)
    if await channels.gate(m, m.bot, welcome=is_new, quiet=is_new):
        return
    if a == "layanan":
        return await layanan_cmd(m, state)
    if a == "deposit":
        return await deposit_cmd(m, state)
    if a == "pesanan":
        return await pesanan_cmd(m)
    await _menu(m)


@router.message(Command("menu"))
async def menu_cmd(m: Message, state: FSMContext):
    if await channels.gate(m, m.bot, state):
        return
    await _menu(m, state)


@router.callback_query(F.data == "menu")
async def menu_cb(c: CallbackQuery, state: FSMContext):
    if await channels.gate(c, c.bot, state):
        return
    await _menu(c, state)


# Command aliases untuk Bot Commands Menu (bukan keyboard). GateMiddleware sudah
# memblokir perintah ini sampai user gabung ke dua channel.
@router.message(Command("layanan", "order"))
async def layanan_cmd(m: Message, state: FSMContext):
    await ord_cats(m, state)


@router.message(Command("deposit"))
async def deposit_cmd(m: Message, state: FSMContext):
    await dep_menu(m, state)


@router.message(Command("pesanan"))
async def pesanan_cmd(m: Message):
    await my_orders(m)


@router.message(Command("riwayat"))
async def riwayat_cmd(m: Message):
    await history(m)


@router.message(Command("profil"))
async def profil_cmd(m: Message):
    await profile(m)


@router.message(Command("referral"))
async def referral_cmd(m: Message):
    await referral(m)


@router.message(Command("toko"))
async def toko_cmd(m: Message):
    await shop(m)


@router.message(Command("misi"))
async def misi_cmd(m: Message):
    await missions(m)


async def _top_board(ev, period: str):
    if period not in ("all", "week", "month"):
        period = "all"
    block = await ui.top_spender_block(10, period)
    await show(ev, f"{block}\n\n<i>Urutan dari total transaksi rupiah terbesar.</i>", ui.top_kb(period))


@router.message(Command("top"))
async def top_cmd(m: Message):
    await _top_board(m, "all")


@router.callback_query(F.data.startswith("top:"))
async def top_orders_cb(c: CallbackQuery):
    await _top_board(c, c.data.split(":", 1)[1])


@router.callback_query(F.data == "misc")
async def misc_cb(c: CallbackQuery):
    await show(c, tree([
        "📱 Toko aplikasi &amp; produk digital",
        "👤 Profil, referral, dan misi",
        "🌐 Website resmi &amp; kontak admin",
    ], head="🧩 <b>MENU LAINNYA</b>"), ui.misc_kb(c.from_user.id))


@router.callback_query(F.data == "gate:check")
async def gate_check(c: CallbackQuery, state: FSMContext):
    if await channels.gate(c, c.bot, state):
        await ui.answer_cb(c, "Anda belum bergabung ke channel yang ditandai ❌. Silakan gabung terlebih dahulu.", True)
        return
    await ui.answer_cb(c, "✅ Terima kasih! Semua channel sudah terhubung.")
    await _menu(c, state)


@router.chat_member()
async def channel_left(ev: ChatMemberUpdated, bot: Bot):
    await channels.on_leave(ev, bot)


@router.my_chat_member()
async def bot_group_status(ev: ChatMemberUpdated, bot: Bot):
    """Catat group saat bot ditambahkan, nonaktifkan saat bot dikeluarkan."""
    if ev.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        return
    status = str(getattr(ev.new_chat_member, "status", "")).lower()
    if status in ("member", "administrator", "creator"):
        if await db.add_promo_group(ev.chat.id, ev.chat.title or ""):
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(
                        admin_id,
                        f"📣 Group <b>{esc(ev.chat.title or 'Tanpa nama')}</b> terdaftar untuk promosi. "
                        "Aktifkan di Panel Admin → Promosi Group.",
                    )
                except Exception:
                    pass
    elif status in ("left", "kicked"):
        await db.set_promo_group(ev.chat.id, False)


# ---------- deposit QRIS ----------
DEP_ICON = {"pending": "🕒", "success": "✅", "expired": "⌛", "failed": "❌", "rejected": "❌"}
DEP_TEXT = {"pending": "Menunggu bayar", "success": "Lunas", "expired": "Kedaluwarsa",
            "failed": "Gagal", "rejected": "Ditolak"}


async def _dep_limit(uid: int):
    limit = int(await db.setting("max_active_deposit") or MAX_ACTIVE_DEPOSITS)
    return limit, await db.active_deposits(uid)


def _dep_status(d) -> str:
    return f"{DEP_ICON.get(d['status'], '•')} {DEP_TEXT.get(d['status'], d['status'])}"


@router.callback_query(F.data == "dep")
async def dep_menu(c: CallbackQuery, state: FSMContext):
    await state.clear()
    limit, active = await _dep_limit(c.from_user.id)
    mn = int(await db.setting("min_deposit") or 0)
    t = tree([
        ("💳 Metode", "<b>QRIS Otomatis</b>"),
        ("🔻 Minimal", f"<b>{rp(mn)}</b>"),
        ("🧾 Invoice aktif", f"<b>{len(active)}/{limit}</b> {ui.bar(len(active), limit)}"),
        ("⚡ Status", "Dicek otomatis tiap 20 detik"),
    ], head="💰 <b>DEPOSIT SALDO</b>")
    rows = []
    if active:
        t += "\n🧾 <b>Invoice aktif</b> — ketuk untuk lihat QRIS / cek status:"
        rows += [[(f"🕒 #{d['id']} • {rp(d['amount'])}", f"dep:view:{d['id']}")] for d in active]
    if len(active) >= limit:
        t += f"\n\n⚠️ Batas <b>{limit} transaksi aktif</b> tercapai. Selesaikan atau tunggu invoice kedaluwarsa."
    else:
        amts = [10000, 25000, 50000, 100000, 250000, 500000]
        rows += [[(rp(a), f"dep:a:{a}") for a in amts[i:i + 2]] for i in range(0, len(amts), 2)]
        rows += [[("✏️ Nominal Lain", "dep:custom")]]
    rows += [[("📄 Riwayat Deposit", "dep:hist")], BACK]
    t += "\n\n💡 Invoice tidak bisa dibatalkan. Bayar kapan saja sebelum kedaluwarsa."
    await show(c, t, kb(*rows))


async def _show_invoice(ev, did: int):
    d = await db.q1("SELECT * FROM deposits WHERE id=? AND user_id=?", (did, ev.from_user.id))
    if not d:
        return await answer_cb(ev, "Tagihan tidak ditemukan.", True)
    caption = tree([
        ("💰 Nominal", f"<b>{rp(d['amount'])}</b>"),
        ("🕒 Status", f"<b>{_dep_status(d)}</b>"),
        ("🔖 Invoice", f"<code>{esc(d['invoice_id'] or d['ref'] or '-')}</code>"),
        ("📅 Dibuat", f"{esc(d['created_at'])} WIB"),
        ("⏳ Berlaku", esc(d['expired_at'] or '-')),
    ], head=f"🧾 <b>INVOICE #{d['id']}</b>")
    caption += ("\n\n📌 Scan QRIS di bawah ini. Setelah bayar, saldo masuk otomatis maks ~20 detik — "
                "atau tekan 🔄 Cek Status sekarang.")
    rows = []
    if d["payment_link"]:
        rows.append([("🧾 Halaman Bayar", d["payment_link"])])
    if d["status"] == "pending":
        rows.append([("🔄 Cek Status", f"dep:check:{did}")])
    rows += [[("📄 Riwayat Deposit", "dep:hist")], BACK]
    markup = kb(*rows)
    if d["qris_image"]:
        await ui.show_photo(ev, d["qris_image"], caption, markup)
    else:
        await show(ev, caption, markup)


async def _make_deposit(ev, uid: int, amount: int):
    mn = int(await db.setting("min_deposit") or 0)
    if amount < mn:
        return await show(ev, f"⚠️ Minimal deposit {rp(mn)}.", kb([("⬅️ Kembali", "dep")]))
    limit, active = await _dep_limit(uid)
    if len(active) >= limit:
        return await show(ev, f"⚠️ Maksimal <b>{limit} invoice aktif</b> per user.\n"
                              f"Selesaikan atau tunggu yang lama kedaluwarsa dulu.",
                          kb([("📄 Riwayat Deposit", "dep:hist")], BACK))
    try:
        info = await gateway.create(0, amount)
    except Exception as e:
        return await show(ev, f"⚠️ Gagal membuat invoice QRIS: {ui.safe_error(e, 160)}",
                          kb([("🔄 Coba Lagi", "dep")], BACK))
    did = await db.create_deposit(uid, amount, gateway.name, info["ref"], info)
    u = await db.get_user(uid)
    await ui.log_channel(ev.bot, tree([
        ("👤 User", ui.public_user(uid, u['name'] if u else None, u['username'] if u else None)),
        ("💰 Nominal", rp(amount)),
        ("💳 Metode", "QRIS Otomatis"),
    ], head=f"🧾 <b>INVOICE BARU</b> #{did}"))
    await _show_invoice(ev, did)


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


@router.callback_query(F.data.startswith("dep:view:"))
async def dep_view(c: CallbackQuery):
    await _show_invoice(c, int(c.data.split(":")[2]))


@router.callback_query(F.data.startswith("dep:check:"))
async def dep_check(c: CallbackQuery):
    did = int(c.data.split(":")[2])
    d = await db.q1("SELECT * FROM deposits WHERE id=? AND user_id=?", (did, c.from_user.id))
    if not d or d["status"] != "pending":
        return await answer_cb(c, "Tagihan ini sudah tidak aktif.", True)
    try:
        res = await gateway.check(d["invoice_id"] or d["ref"])
    except Exception as e:
        return await answer_cb(c, f"⚠️ Cek gagal: {ui.safe_error(e, 140)}", True)
    status = res["status"]
    if gateway.is_paid(status):
        result = await db.confirm_deposit_by_invoice(d["invoice_id"] or d["ref"])
        if result:
            await ui.deposit_paid_notice(c.bot, result)
            return await show(c, "✅ <b>Pembayaran terdeteksi!</b> Saldo sudah ditambahkan.",
                              kb([("🛒 Order Layanan", "ord")], BACK))
    if gateway.is_expired(status):
        await db.expire_deposit_by_invoice(d["invoice_id"] or d["ref"])
        return await show(c, "⌛ Invoice sudah kedaluwarsa. Silakan buat deposit baru.",
                          kb([("💰 Deposit", "dep")]))
    await answer_cb(c, "🕒 Masih menunggu pembayaran.", True)
    await _show_invoice(c, did)


@router.callback_query(F.data == "dep:hist")
async def dep_history(c: CallbackQuery):
    rows = await db.q("SELECT * FROM deposits WHERE user_id=? ORDER BY id DESC LIMIT 15", (c.from_user.id,))
    t = tree([("📊 Menampilkan", f"<b>{len(rows)}</b> deposit terakhir")],
             head="📄 <b>RIWAYAT DEPOSIT</b>")
    if rows:
        t += "\n\n"
        for d in rows:
            t += (f"{_dep_status(d)} <b>#{d['id']}</b> • {rp(d['amount'])}\n"
                  f"   <code>{esc(d['invoice_id'] or d['ref'] or '-')}</code> • <i>{esc(d['created_at'])}</i>\n"
                  f"   ──────────\n")
    else:
        t += "\n\nBelum ada deposit. Silakan isi saldo melalui tombol berikut 👇"
    buttons = [[(f"{DEP_ICON.get(d['status'], '•')} #{d['id']} • {rp(d['amount'])}", f"dep:view:{d['id']}")]
               for d in rows[:8]]
    buttons += [[("💰 Deposit Baru", "dep")], BACK]
    await show(c, t, kb(*buttons))


@router.callback_query(F.data.startswith("dep:pay:"))
async def dep_pay_stub(c: CallbackQuery, state: FSMContext):
    await answer_cb(c, "Mode demo sudah nonaktif. Silakan bayar melalui QRIS.", True)
    await dep_menu(c, state)


@router.callback_query(F.data.startswith("dep:cx:"))
async def dep_cancel_stub(c: CallbackQuery):
    await answer_cb(c, "Invoice QRIS tidak bisa dibatalkan.", True)

# ---------- order layanan (provider real) ----------
KUOTA_PENUH = ("⚠️ Maaf, kuota order layanan ini sedang penuh. "
               "Silakan coba jumlah lebih kecil atau ulangi beberapa saat lagi.")

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
    cukup = "✅ cukup" if u["balance"] >= price else "⚠️ belum cukup, silakan deposit"
    rows = [
        ("🏷 Layanan", f"<b>{esc(ui.clean_service_name(s['name'], 48))}</b>"),
        ("📋 Format", TYPE_LABELS.get(s['provider_type'], s['provider_type'])),
        ("🔗 Target", f"<code>{esc(d['link'])}</code>"),
    ]
    if d.get("qty"):
        rows.append(("🔢 Jumlah", f"<b>{ui.num(d['qty'])}</b>"))
    for k, v in (d.get("extra") or {}).items():
        rows.append((f"✍️ {esc(LABEL_FIELDS.get(k, k)).capitalize()}", f"<code>{esc(v[:160])}</code>"))
    rows += [
        ("💸 Harga", f"<b>{rp(price)}</b>"),
        ("🏦 Saldo", f"<b>{rp(u['balance'])}</b> — {cukup}"),
    ]
    t = tree(rows, head="🧾 <b>KONFIRMASI PESANAN</b>")
    t += "\n\nPastikan target sudah benar. Pesanan akan diproses otomatis setelah konfirmasi ⚡"
    await state.set_state(S.ord_confirm)
    await ev.answer(t, reply_markup=kb([("✅ Bayar & Pesan", "ord:ok"), ("❌ Batal", "menu")]))


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


GROUP_PER = 8   # 4 baris x 2 platform per halaman
CAT_PER = 6     # 3 baris x 2 sub-kategori per halaman
SVC_PER = 6

_FILTERS = ("", "mur", "cep", "ref")
_FILTER_NOTE = {
    "": "💸 Termurah dulu",
    "mur": "💸 Termurah dulu",
    "cep": "⚡ Tercepat dulu",
    "ref": "🛡 Hanya yang ada refill",
}


def _filter_row(ftype: str, make_cb) -> list:
    """Baris filter yang sama di semua daftar layanan."""
    return [(("↩️ Semua" if f == "" else db.FILTER_LABELS[f]), make_cb(f))
            for f in _FILTERS]


def _cat_cb(ftype: str, cid: int, page: int) -> str:
    return f"ord:f:{ftype}:{cid}:{page}" if ftype else f"ord:c:{cid}:{page}"


def _est_badge(s) -> str:
    badge = "🛡" if s["provider_refill"] else "⚡"
    minutes = db.avg_minutes(s["provider_avg"])
    if minutes >= 99999:
        return badge
    if minutes < 1:
        return f"{badge} ⏱<1m"
    return f"{badge} ⏱{int(minutes)}m" if minutes < 60 else f"{badge} ⏱{int(minutes // 60)}j"


async def _ord_groups(ev, page: int):
    """Halaman platform: Instagram, TikTok, YouTube, dll."""
    groups = await db.grouped_categories()
    if not groups:
        return await show(ev, "Belum ada layanan tersedia. Silakan hubungi admin.", kb(BACK))
    pages = max(1, math.ceil(len(groups) / GROUP_PER))
    page = max(0, min(page, pages - 1))
    chunk = groups[page * GROUP_PER:(page + 1) * GROUP_PER]
    # Satu platform per baris: teks pendek tapi harga & jumlah tetap terbaca di HP.
    rows = [[(f"{g['emoji']} {g['label'][:18]} • {rp(g['min_price'])} • {ui.num(g['count'])} layanan",
              f"ord:p:{g['key']}:0")] for g in chunk]
    rows.append([("📋 Semua Layanan", "ord:all::0")])
    nav = []
    if page > 0:
        nav.append(("◀️", f"ord:g:{page - 1}"))
    if page + 1 < pages:
        nav.append(("▶️", f"ord:g:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Menu", "menu")])
    t = tree([
        "📂 Dikelompokkan per platform",
        "🔎 Filter murah / cepat / refill tersedia di daftar layanan",
        f"📊 {len(groups)} platform • halaman {page + 1}/{pages}",
    ], head="🛒 <b>ORDER LAYANAN</b>")
    t += "\n\nSilakan pilih platform:"
    await show(ev, t, kb(*rows))


@router.callback_query(F.data == "ord")
async def ord_cats(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await _ord_groups(c, 0)


@router.callback_query(F.data.startswith("ord:g:"))
async def ord_groups_cb(c: CallbackQuery):
    await _ord_groups(c, int(c.data.split(":")[2]))


async def _ord_all(ev, ftype: str, page: int):
    """Semua layanan aktif dalam satu daftar, dengan filter yang sama."""
    ftype = ftype if ftype in db.FILTER_LABELS else ""
    svcs = await db.filter_services(await db.q("SELECT * FROM services WHERE active=1"), ftype)
    pages = max(1, math.ceil(len(svcs) / SVC_PER))
    page = max(0, min(page, pages - 1))
    chunk = svcs[page * SVC_PER:(page + 1) * SVC_PER]
    rows = []
    for n, s in enumerate(chunk, page * SVC_PER + 1):
        rows.append([(f"{n:02d}. {ui.clean_service_name(s['name'], 22)} • {rp(s['_price'])} {_est_badge(s)}",
                      f"ord:s:{s['id']}:all:{ftype}")])
    rows.append(_filter_row(ftype, lambda f: f"ord:all:{f}:0"))
    nav = []
    if page > 0:
        nav.append(("◀️", f"ord:all:{ftype}:{page - 1}"))
    if page + 1 < pages:
        nav.append(("▶️", f"ord:all:{ftype}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Platform", "ord:g:0")])
    t = tree([
        f"🔎 Filter: <b>{db.FILTER_LABELS[ftype] if ftype else 'Semua'}</b>",
        _FILTER_NOTE[ftype],
        f"📊 {ui.num(len(svcs))} layanan • halaman {page + 1}/{pages}",
    ], head="📋 <b>SEMUA LAYANAN</b>")
    if not svcs:
        t += "\n\nTidak ada layanan untuk filter ini. Pilih filter lain."
    else:
        t += "\n\nSilakan pilih layanan:"
    await show(ev, t, kb(*rows))


@router.callback_query(F.data.startswith("ord:all:"))
async def ord_all_cb(c: CallbackQuery):
    _, _, ftype, page = c.data.split(":")
    await _ord_all(c, ftype, int(page or 0))


@router.callback_query(F.data.startswith("ord:p:"))
async def ord_group_cb(c: CallbackQuery):
    _, _, key, page_s = c.data.split(":")
    page = int(page_s)
    group = next((g for g in await db.grouped_categories() if g["key"] == key), None)
    if not group:
        return await answer_cb(c, "Platform tidak tersedia.", True)
    cats = group["cats"]
    pages = max(1, math.ceil(len(cats) / CAT_PER))
    page = max(0, min(page, pages - 1))
    chunk = cats[page * CAT_PER:(page + 1) * CAT_PER]
    rows = [[(f"{x['emoji']} {x['name'][:24]} • {rp(x['min_price'])} • {ui.num(x['count'])} layanan",
              f"ord:c:{x['id']}:0")] for x in chunk]
    nav = []
    if page > 0:
        nav.append(("◀️", f"ord:p:{key}:{page - 1}"))
    if page + 1 < pages:
        nav.append(("▶️", f"ord:p:{key}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([("⬅️ Platform", "ord:g:0")])
    t = tree([
        f"📁 {len(cats)} kategori • {ui.num(group['count'])} layanan",
        f"💸 Termurah dulu • halaman {page + 1}/{pages}",
    ], head=f"{group['emoji']} <b>{esc(group['label'].upper())}</b>")
    t += "\n\nSilakan pilih kategori:"
    await show(c, t, kb(*rows))


async def _ord_cat(ev, cid: int, page: int, ftype: str = ""):
    ftype = ftype if ftype in db.FILTER_LABELS else ""
    cat = await db.q1("SELECT * FROM categories WHERE id=?", (cid,))
    if not cat:
        return await answer_cb(ev, "Kategori tidak tersedia.", True)
    key, emoji, label = db.platform_of(cat["name"])
    svcs = await db.filter_services(
        await db.q("SELECT * FROM services WHERE category_id=? AND active=1", (cid,)), ftype)
    pages = max(1, math.ceil(len(svcs) / SVC_PER))
    page = max(0, min(page, pages - 1))
    chunk = svcs[page * SVC_PER:(page + 1) * SVC_PER]
    rows = []
    for n, s in enumerate(chunk, page * SVC_PER + 1):
        rows.append([(f"{n:02d}. {ui.clean_service_name(s['name'], 22)} • {rp(s['_price'])} {_est_badge(s)}",
                      f"ord:s:{s['id']}:cat:{ftype}:{cid}")])
    rows.append(_filter_row(ftype, lambda f: f"ord:f:{f}:{cid}:0"))
    nav = []
    if page > 0:
        nav.append(("◀️", _cat_cb(ftype, cid, page - 1)))
    if page + 1 < pages:
        nav.append(("▶️", _cat_cb(ftype, cid, page + 1)))
    if nav:
        rows.append(nav)
    rows.append([("📋 Semua", f"ord:all:{ftype}:0")])
    rows.append([("⬅️ Platform", f"ord:p:{key}:0")])
    t = tree([
        f"🏷 {emoji} {esc(label)}",
        f"🔎 Filter: <b>{db.FILTER_LABELS[ftype] if ftype else 'Semua'}</b>",
        _FILTER_NOTE[ftype],
        f"📊 {ui.num(len(svcs))} layanan • halaman {page + 1}/{pages}",
    ], head=f"{cat['emoji']} <b>{esc(cat['name'].upper())}</b>")
    if not svcs:
        t += "\n\nTidak ada layanan untuk filter ini. Pilih filter lain."
    else:
        t += "\n\nSilakan pilih layanan:"
    await show(ev, t, kb(*rows))


@router.callback_query(F.data.startswith("ord:c:"))
async def ord_cat(c: CallbackQuery):
    _, _, cid, page = c.data.split(":")
    await _ord_cat(c, int(cid), int(page))


@router.callback_query(F.data.startswith("ord:f:"))
async def ord_filter(c: CallbackQuery):
    _, _, ftype, cid, page = c.data.split(":")
    await _ord_cat(c, int(cid), int(page), ftype)


@router.callback_query(F.data.startswith("ord:s:"))
async def ord_service(c: CallbackQuery):
    parts = c.data.split(":")
    s = await db.q1("SELECT * FROM services WHERE id=? AND active=1", (int(parts[2]),))
    if not s:
        return await answer_cb(c, "Layanan tidak tersedia.", True)
    ftype = parts[4] if len(parts) > 4 and parts[4] in db.FILTER_LABELS else ""
    if len(parts) > 3 and parts[3] == "all":
        back = f"ord:all:{ftype}:0"
    else:
        back = _cat_cb(ftype, s["category_id"], 0)
    estimasi = str(s["provider_avg"] or "").strip()[:90] or "Proses cepat, otomatis"
    desc = ui.clean_desc(s["description"])
    if desc and desc.lower() != str(s["name"]).strip().lower():
        spesifikasi = "\n".join(f"• {esc(line)}" for line in desc.splitlines()[:6])
    else:
        spesifikasi = "• Layanan diproses otomatis oleh provider."
    t = tree([
        ("📋 Format", TYPE_LABELS.get(s['provider_type'], s['provider_type'])),
        ("💸 Harga", f"<b>{rp(await db.effective_price(s))}</b> / 1.000"),
        ("🔢 Min/Max", f"{ui.num(s['min_qty'])} / {ui.num(s['max_qty'])}"),
        ("🛡 Garansi", "✅ Ada refill" if s['provider_refill'] else "❌ Tanpa refill"),
        ("⏱ Estimasi", f"<i>{esc(estimasi)}</i>"),
    ], head=f"📌 <b>{esc(ui.clean_service_name(s['name'], 48))}</b>")
    t += (f"\n\n📝 <b>Spesifikasi layanan:</b>\n{spesifikasi}\n\n"
          f"💡 Tagihan menyesuaikan jumlah/baris yang Anda kirim.")
    await show(c, t,
               kb([("🛒 Pesan Sekarang", f"ord:go:{s['id']}")], [("⬅️ Kembali", back)]))


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
    if not await limits.can_cover(s, int(digits)):
        return await m.answer(KUOTA_PENUH)
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
        return await show(c, "⚠️ Layanan ini belum tersedia. Silakan hubungi admin.", kb(BACK))
    extra = d.get("extra") or {}
    qty = d.get("qty")
    price = await _harga(d, s)
    if not await limits.can_cover(s, await _billable(d, s)):
        await state.clear()
        return await show(c, KUOTA_PENUH, kb(BACK))
    oid = await db.create_order(c.from_user.id, s, d["link"], qty or 0, price, extra)
    if oid is None:
        await state.clear()
        return await show(c, "⚠️ <b>Saldo tidak cukup.</b> Silakan deposit dulu.",
                          kb([("💰 Deposit Saldo", "dep")], BACK))
    await state.clear()
    try:
        pid = await provider.order(int(s["provider_id"]), d["link"], quantity=qty,
                                   ptype=s["provider_type"], **extra)
    except Exception:
        await db.cancel_order(oid)
        await ui.log_channel(c.bot, tree([
            ("👤 User", ui.public_user(c.from_user.id)),
            ("💸 Nominal", rp(price)),
            ("📌 Alasan", "Gagal diproses, saldo dikembalikan"),
        ], head=f"↩️ <b>REFUND ORDER</b> #{oid}"))
        return await show(c, "⚠️ Pesanan belum dapat diproses. Saldo Anda dikembalikan.", kb(BACK))
    await db.x("UPDATE orders SET provider_order_id=? WHERE id=?", (pid, oid))
    u = await db.get_user(c.from_user.id)
    await show(c, tree([
        ("🆔 Order ID", f"<code>#{oid}</code>"),
        ("🏷 Layanan", esc(ui.clean_service_name(s['name'], 48))),
        ("💸 Harga", rp(price)),
        ("💰 Sisa Saldo", f"<b>{rp(u['balance'])}</b>"),
    ], head="✅ <b>Pesanan Berhasil Dibuat!</b>"), kb([("📦 Pesanan Saya", "myord")], BACK))
    await ui.notify_admins(c.bot, f"🛒 Order baru <code>#{oid}</code> dari <code>{c.from_user.id}</code>\n"
                                  f"{esc(s['name'])} • {rp(price)} • provider <code>{esc(pid)}</code>")
    await ui.log_channel(c.bot, tree([
        ("👤 User", ui.public_user(c.from_user.id, u['name'] if u else None, u['username'] if u else None)),
        ("📦 Layanan", esc(ui.clean_service_name(s['name'], 48))),
        ("💸 Harga", rp(price)),
    ], head=f"🛒 <b>ORDER BARU</b> #{oid}"))


# ---------- toko aplikasi ----------
@router.callback_query(F.data == "shop")
async def shop(c: CallbackQuery):
    ps = await db.q("SELECT p.*, (SELECT COUNT(*) FROM product_stock s WHERE s.product_id=p.id AND s.sold=0) stock "
                    "FROM products p WHERE p.active=1 ORDER BY p.id")
    if not ps:
        return await show(c, "Belum ada produk.", kb(BACK))
    rows = [[(f"{p['name'][:26]} • {rp(p['price'])}", f"shop:p:{p['id']}")] for p in ps]
    rows += [[("🗂 Pembelian Saya", "shop:my")], BACK]
    t = tree([("📦 Produk tersedia", f"<b>{len(ps)}</b>")], head="📱 <b>TOKO APLIKASI</b>")
    t += "\n\nSilakan pilih produk digital:"
    await show(c, t, kb(*rows))


@router.callback_query(F.data.startswith("shop:p:"))
async def shop_product(c: CallbackQuery):
    pid = int(c.data.split(":")[2])
    p = await db.q1("SELECT * FROM products WHERE id=? AND active=1", (pid,))
    if not p:
        return await c.answer("Produk tidak tersedia.", show_alert=True)
    stock = (await db.q1("SELECT COUNT(*) n FROM product_stock WHERE product_id=? AND sold=0", (pid,)))["n"]
    rows = [[("🛒 Beli Sekarang", f"shop:buy:{pid}")]] if stock else []
    rows.append([("⬅️ Kembali", "shop")])
    await show(c, tree([
        ("💸 Harga", f"<b>{rp(p['price'])}</b>"),
        ("📦 Stok", f"<b>{stock}</b>"),
        ("📝 Deskripsi", esc(p['description'] or '-')),
    ], head=f"📦 <b>{esc(p['name'])}</b>"), kb(*rows))


@router.callback_query(F.data.startswith("shop:buy:"))
async def shop_buy(c: CallbackQuery):
    ok, data, p = await db.buy_product(c.from_user.id, int(c.data.split(":")[2]))
    if not ok:
        rows = [[("💰 Deposit Saldo", "dep")]] if "Saldo" in data else []
        return await show(c, f"⚠️ {data}", kb(*rows, [("⬅️ Toko", "shop")]))
    u = await db.get_user(c.from_user.id)
    t = tree([
        ("📦 Produk", esc(p['name'])),
        ("💸 Harga", rp(p['price'])),
        ("💰 Sisa Saldo", f"<b>{rp(u['balance'])}</b>"),
    ], head="✅ <b>Pembelian Berhasil!</b>")
    t += f"\n\n🔐 <b>Data produk:</b>\n<code>{esc(data)}</code>"
    await show(c, t, kb([("📱 Toko", "shop")], BACK))
    await ui.notify_admins(c.bot, f"📱 Pembelian <b>{esc(p['name'])}</b> oleh <code>{c.from_user.id}</code> ({rp(p['price'])})")
    await ui.log_channel(c.bot, tree([
        ("👤 User", ui.public_user(c.from_user.id, u['name'] if u else None, u['username'] if u else None)),
        ("📦 Produk", esc(p['name'])),
        ("💸 Harga", rp(p['price'])),
    ], head="📱 <b>PEMBELIAN</b>"))


@router.callback_query(F.data == "shop:my")
async def shop_my(c: CallbackQuery):
    rows = await db.q("SELECT * FROM purchases WHERE user_id=? ORDER BY id DESC LIMIT 5", (c.from_user.id,))
    t = tree([("📊 Menampilkan", f"<b>{len(rows)}</b> pembelian terakhir")],
             head="🗂 <b>PEMBELIAN SAYA</b>")
    t += "\n\n"
    t += "\n\n".join(f"📦 <b>{esc(r['name'])}</b> • {rp(r['price'])}\n<code>{esc(r['data'])}</code>\n<i>{r['created_at']}</i>"
                     for r in rows) or "Belum ada pembelian."
    await show(c, t, kb([("⬅️ Toko", "shop")]))


# ---------- pesanan / riwayat / profil ----------
@router.callback_query(F.data == "myord")
async def my_orders(c: CallbackQuery):
    rows = await db.q("SELECT o.*, COALESCE(s.provider_refill,0) pr FROM orders o "
                      "LEFT JOIN services s ON s.id=o.service_id "
                      "WHERE o.user_id=? ORDER BY o.id DESC LIMIT 10", (c.from_user.id,))
    t = tree([("📊 Menampilkan", f"<b>{len(rows)}</b> pesanan terakhir")],
             head="📦 <b>PESANAN SAYA</b>") + "\n\n"
    kr = []
    for o in rows:
        t += (f"{ui.STATUS_EMOJI.get(o['status'], '•')} <b>#{o['id']}</b> • {esc(o['service_name'])}\n"
              f"   💸 {rp(o['price'])} • 🔢 {ui.num(o['quantity']) or '-'} • "
              f"{ui.STATUS_ID.get(o['status'], o['status'])}\n")
        if o["refill_id"]:
            t += f"   🔁 Refill : <b>{esc(o['refill_status'] or 'Menunggu')}</b>\n"
        t += f"   <i>{esc(o['created_at'])}</i>\n   ──────────\n"
        if o["provider_order_id"] and o["pr"]:
            label = f"📊 Cek Refill #{o['id']}" if o["refill_id"] else f"🔁 Refill #{o['id']}"
            kr.append([(label, f"ord:refill:{o['id']}")])
    if not rows:
        t += "Belum ada pesanan. Silakan cari layanan termurah melalui menu Order 👇"
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
            msg = f"📊 Status refill: {st}"
        else:
            rid = await provider.refill(o["provider_order_id"])
            await db.x("UPDATE orders SET refill_id=?, refill_status='Pending', checked_at=? WHERE id=?",
                       (rid, db.now(), oid))
            msg = "✅ Refill diajukan. Silakan cek statusnya melalui tombol ini."
    except Exception:
        msg = "⚠️ Refill belum dapat diproses. Silakan ulangi beberapa saat lagi."
    await answer_cb(c, msg, True)
    await my_orders(c)


@router.callback_query(F.data == "hist")
async def history(c: CallbackQuery):
    rows = await db.q("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 15", (c.from_user.id,))
    icons = {"deposit": "💰", "order": "🛒", "purchase": "📱", "refund": "↩️", "referral": "🎁", "mission": "🎯", "admin": "🛠"}
    t = tree([("📊 Menampilkan", f"<b>{len(rows)}</b> transaksi terakhir")],
             head="🧾 <b>RIWAYAT TRANSAKSI</b>")
    t += "\n\n"
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
    st = {"joined": "✅ Terverifikasi", "out": "❌ Perlu gabung lagi"}.get(u["channel_status"], "⏳ Belum dicek")
    await show(c, tree([
        ("🙋 Nama", f"<b>{esc(u['name'] or '-')}</b>"),
        ("🆔 ID", f"<code>{u['id']}</code>"),
        ("💰 Saldo", f"<b>{rp(u['balance'])}</b>"),
        ("📦 Total Order", f"<b>{ui.num(u['total_order'])}</b>"),
        ("💳 Total Belanja", f"<b>{rp(u['total_spent'])}</b>"),
        ("🎁 Referral", f"<b>{refs}</b> teman • {rp(u['ref_earned'])}"),
        ("🔒 Channel", f"<b>{st}</b>"),
        ("📅 Bergabung", f"{esc(u['joined_at'])} WIB"),
    ], head="👤 <b>PROFIL SAYA</b>"),
               kb([("💰 Deposit", "dep"), ("🧾 Riwayat", "hist")], BACK))


# ---------- referral ----------
@router.callback_query(F.data == "ref")
async def referral(c: CallbackQuery):
    me = await c.bot.me()
    u = await db.get_user(c.from_user.id)
    refs = await db.referral_count(u["id"])
    pct = min(50, max(0, int(await db.setting("ref_percent") or 0)))
    bonus = int(await db.setting("ref_signup_bonus") or 0)
    days = max(0, int(await db.setting("ref_days") or 0))
    masa = f"{days} hari" if days else "tanpa batas"
    link = f"https://t.me/{me.username}?start=ref_{u['id']}"
    t = tree([
        ("🎁 Bonus daftar", f"<b>{rp(bonus)}</b>{' (nonaktif)' if bonus <= 0 else ''}"),
        ("💸 Komisi order", f"<b>{pct}%</b> setelah order teman selesai"),
    ], head="🎁 <b>PROGRAM REFERRAL</b>")
    t += (f"\n\nAjak teman &amp; dapatkan hadiah di atas.\n\n"
          f"⏳ Komisi berlaku <b>{masa}</b> sejak teman gabung lewat link Anda. "
          f"Dihitung dari keuntungan order, jadi tetap aman &amp; saling menguntungkan.\n\n"
          f"🔗 <b>Link Anda:</b>\n<code>{link}</code>")
    t += "\n\n" + tree([
        ("📈 Teman diundang", f"<b>{refs}</b>"),
        ("💰 Total pendapatan", f"<b>{rp(u['ref_earned'])}</b>"),
    ], head="📊 <b>STATISTIK REFERRAL</b>")
    await show(c, t,
               kb([("📤 Bagikan Link", f"https://t.me/share/url?url={link}&text=Order%20sosmed%20murah%20di%20{BOT_NAME}")], BACK))


# ---------- misi ----------
@router.callback_query(F.data == "msn")
async def missions(c: CallbackQuery):
    ms = await db.q("SELECT * FROM missions WHERE active=1 ORDER BY id")
    t = tree([("🎯 Misi aktif", f"<b>{len(ms)}</b>")], head="🎯 <b>MISI SPECIAL</b>") + "\n\n"
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
        await ui.log_channel(c.bot, tree([
            ("👤 User", ui.public_user(c.from_user.id)),
            ("🏆 Misi", esc(info)),
            ("💰 Hadiah", f"+{rp(reward)}"),
        ], head="🎯 <b>MISI DIKLAIM</b>"))
    await missions(c)


# ---------- fallback ----------
@router.message(StateFilter(None))
async def fallback(m: Message):
    cmd = (m.text or "").strip().split(maxsplit=1)[0].split("@")[0].lower()
    if cmd in ("/admin", "/users"):
        return await m.answer("⛔ Perintah ini khusus admin.")
    await m.answer("Selamat datang 👋 Berikut menu utama: deposit, order termurah, dan cek pesanan.",
                   reply_markup=ui.main_kb(m.from_user.id))
