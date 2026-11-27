import json
import math
import os
import re
from datetime import datetime, timezone, timedelta

import aiosqlite

WIB = timezone(timedelta(hours=7))
_db: aiosqlite.Connection | None = None


def now() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")


def today() -> str:
    return datetime.now(WIB).strftime("%Y-%m-%d")


SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, name TEXT, username TEXT,
  balance INTEGER DEFAULT 0, total_order INTEGER DEFAULT 0, total_spent INTEGER DEFAULT 0,
  banned INTEGER DEFAULT 0, referred_by INTEGER, referred_at TEXT,
  ref_earned INTEGER DEFAULT 0, joined_at TEXT,
  channel_status TEXT DEFAULT 'pending', channel_checked_at TEXT, channel_joined_at TEXT);
CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, emoji TEXT DEFAULT '📁');
CREATE TABLE IF NOT EXISTS services(
  id INTEGER PRIMARY KEY AUTOINCREMENT, category_id INTEGER, name TEXT,
  price_per_1k INTEGER, min_qty INTEGER, max_qty INTEGER, description TEXT DEFAULT '', active INTEGER DEFAULT 1,
  provider_id INTEGER UNIQUE, provider_type TEXT DEFAULT 'default',
  provider_price INTEGER DEFAULT 0, provider_min INTEGER DEFAULT 0, provider_max INTEGER DEFAULT 0,
  provider_refill INTEGER DEFAULT 0, provider_avg TEXT DEFAULT '', auto_price INTEGER DEFAULT 1,
  synced_at TEXT, source TEXT DEFAULT 'manual');
CREATE TABLE IF NOT EXISTS orders(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, service_id INTEGER, service_name TEXT,
  link TEXT, quantity INTEGER, price INTEGER, status TEXT DEFAULT 'Pending',
  provider_order_id TEXT, created_at TEXT,
  provider_id INTEGER, provider_type TEXT DEFAULT 'default', extra TEXT DEFAULT '',
  provider_price INTEGER DEFAULT 0,
  refill_id TEXT, refill_status TEXT, checked_at TEXT,
  ref_bonus INTEGER DEFAULT 0, ref_bonus_user INTEGER);
CREATE TABLE IF NOT EXISTS deposits(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, method TEXT,
  ref TEXT, status TEXT DEFAULT 'pending', created_at TEXT,
  invoice_id TEXT, qris_image TEXT DEFAULT '', payment_link TEXT DEFAULT '',
  expired_at TEXT, paid_at TEXT);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER, description TEXT DEFAULT '', active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS product_stock(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, data TEXT, sold INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_id INTEGER, name TEXT,
  price INTEGER, data TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS transactions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, amount INTEGER, note TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS missions(
  id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, type TEXT, target INTEGER, reward INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS mission_claims(
  user_id INTEGER, mission_id INTEGER, period TEXT, PRIMARY KEY(user_id, mission_id, period));
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_tx_user ON transactions(user_id);
"""

DEFAULT_SETTINGS = {
    "maintenance": "0",
    "ref_percent": "20",     # % dari margin order yang sukses, bukan dari deposit
    "ref_days": "7",          # komisi hanya untuk order dalam N hari sejak teman daftar
    "ref_signup_bonus": "0", # default 0 supaya tidak rugi di awal (bisa diatur admin)
    "min_deposit": "10000",
    "announcement": "",
    "markup_percent": "25",   # margin minimum atas modal provider
    "markup_flat": "0",       # margin tetap (Rp) per 1000
    "auto_sync": "1",         # tarik layanan otomatis saat bot start
    "service_fav": "0",       # hanya ambil layanan favorit provider
    "max_active_deposit": "3",  # batas invoice aktif per user
}

SERVICE_COLUMNS = {
    "provider_id": "INTEGER", "provider_type": "TEXT DEFAULT 'default'",
    "provider_price": "INTEGER DEFAULT 0", "provider_min": "INTEGER DEFAULT 0",
    "provider_max": "INTEGER DEFAULT 0", "provider_refill": "INTEGER DEFAULT 0",
    "provider_avg": "TEXT DEFAULT ''", "auto_price": "INTEGER DEFAULT 1",
    "synced_at": "TEXT", "source": "TEXT DEFAULT 'manual'",
}
ORDER_COLUMNS = {
    "provider_id": "INTEGER", "provider_type": "TEXT DEFAULT 'default'",
    "extra": "TEXT DEFAULT ''", "refill_id": "TEXT", "refill_status": "TEXT",
    "checked_at": "TEXT", "provider_price": "INTEGER DEFAULT 0",
    "ref_bonus": "INTEGER DEFAULT 0", "ref_bonus_user": "INTEGER",
}
DEPOSIT_COLUMNS = {
    "invoice_id": "TEXT", "qris_image": "TEXT DEFAULT ''",
    "payment_link": "TEXT DEFAULT ''", "expired_at": "TEXT", "paid_at": "TEXT",
}
USER_COLUMNS = {
    "channel_status": "TEXT DEFAULT 'pending'",
    "channel_checked_at": "TEXT", "channel_joined_at": "TEXT",
    "referred_at": "TEXT",
}


async def _migrate():
    """Tambah kolom baru ke database lama tanpa menghapus data."""
    for table, columns in (("services", SERVICE_COLUMNS), ("orders", ORDER_COLUMNS),
                           ("deposits", DEPOSIT_COLUMNS), ("users", USER_COLUMNS)):
        have = {r["name"] for r in await q(f"PRAGMA table_info({table})")}
        for col, decl in columns.items():
            if col not in have:
                await x(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")

    # Sekali saja: database lama memakai markup 35% & skema referral lama.
    if not await q1("SELECT 1 FROM settings WHERE key='markup_25_applied'"):
        if (await setting("markup_percent")) == "35":
            await set_setting("markup_percent", "25")
        await set_setting("markup_25_applied", "1")
    if not await q1("SELECT 1 FROM settings WHERE key='ref_safe_applied'"):
        if (await setting("ref_percent")) == "5":
            await set_setting("ref_percent", "20")
        if (await setting("ref_signup_bonus")) == "500":
            await set_setting("ref_signup_bonus", "0")
        await set_setting("ref_safe_applied", "1")


async def init(path: str):
    global _db
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    await _db.commit()
    await _migrate()
    await _seed()
    await mask_catalog_codes()


async def close():
    if _db:
        await _db.close()


async def q(sql, args=()):
    async with _db.execute(sql, args) as c:
        return await c.fetchall()


async def q1(sql, args=()):
    async with _db.execute(sql, args) as c:
        return await c.fetchone()


async def x(sql, args=()):
    c = await _db.execute(sql, args)
    await _db.commit()
    return c


async def checkpoint():
    await _db.execute("PRAGMA wal_checkpoint(FULL)")


# ---------- settings ----------
async def setting(key: str) -> str:
    r = await q1("SELECT value FROM settings WHERE key=?", (key,))
    return r["value"] if r else DEFAULT_SETTINGS.get(key, "")


async def set_setting(key: str, value: str):
    await x("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value))


# ---------- seed demo ----------
async def _seed():
    for k, v in DEFAULT_SETTINGS.items():
        await x("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))

    if not await q1("SELECT 1 FROM categories LIMIT 1"):
        demo = {
            "Instagram": [("IG Followers [Demo]", 15000, 100, 10000, "Followers campuran, estimasi cepat. (DEMO)"),
                          ("IG Likes [Demo]", 8000, 50, 20000, "Likes postingan. (DEMO)"),
                          ("IG Views Reels [Demo]", 3000, 100, 100000, "Views reels. (DEMO)")],
            "TikTok": [("TikTok Followers [Demo]", 18000, 100, 10000, "Followers akun TikTok. (DEMO)"),
                       ("TikTok Likes [Demo]", 6000, 50, 20000, "Likes video. (DEMO)"),
                       ("TikTok Views [Demo]", 1500, 100, 500000, "Views video. (DEMO)")],
            "YouTube": [("YT Views [Demo]", 25000, 100, 50000, "Views video. (DEMO)"),
                        ("YT Subscribers [Demo]", 90000, 50, 5000, "Subscribers channel. (DEMO)")],
            "Telegram": [("Telegram Members [Demo]", 20000, 100, 20000, "Member channel/grup. (DEMO)"),
                         ("Telegram Post Views [Demo]", 2000, 100, 100000, "Views postingan. (DEMO)")],
        }
        for cat, items in demo.items():
            cid = await get_or_create_category(cat)
            for name, price, mn, mx, desc in items:
                await x("INSERT INTO services(category_id,name,price_per_1k,min_qty,max_qty,description) VALUES(?,?,?,?,?,?)",
                        (cid, name, price, mn, mx, desc))

    if not await q1("SELECT 1 FROM products LIMIT 1"):
        c = await x("INSERT INTO products(name,price,description) VALUES(?,?,?)",
                    ("Akun Premium [Demo]", 15000, "Produk demo — isi stok asli lewat Panel Admin."))
        for i in range(1, 6):
            await x("INSERT INTO product_stock(product_id,data) VALUES(?,?)",
                    (c.lastrowid, f"demo{i}@tarakapedia.com | pass: Demo#{i}123"))
        c = await x("INSERT INTO products(name,price,description) VALUES(?,?,?)",
                    ("Template Mockup Pack [Demo]", 25000, "Produk demo — link download dikirim otomatis."))
        for i in range(1, 4):
            await x("INSERT INTO product_stock(product_id,data) VALUES(?,?)",
                    (c.lastrowid, f"https://tarakapedia.com/demo-download/{i}"))

    if not await q1("SELECT 1 FROM missions LIMIT 1"):
        for t, ty, tg, rw in [("Check-in Harian", "daily", 1, 200),
                              ("Order Pertama", "orders", 1, 500),
                              ("Order 5 Kali", "orders", 5, 2500),
                              ("Total Deposit Rp 50.000", "deposit", 50000, 1500),
                              ("Ajak 3 Teman", "referral", 3, 3000)]:
            await x("INSERT INTO missions(title,type,target,reward) VALUES(?,?,?,?)", (t, ty, tg, rw))


async def get_or_create_category(name: str) -> int:
    r = await q1("SELECT id FROM categories WHERE name=?", (name,))
    if r:
        return r["id"]
    low = name.lower()
    emoji = next((e for k, e in [("insta", "📸"), ("tiktok", "🎵"), ("youtube", "▶️"), ("telegram", "✈️"),
                                 ("facebook", "📘"), ("twitter", "🐦"), ("shopee", "🛍"), ("spotify", "🎧")]
                  if k in low), "📁")
    c = await x("INSERT INTO categories(name,emoji) VALUES(?,?)", (name, emoji))
    return c.lastrowid


# ---------- harga / sinkronisasi provider ----------
_PROVIDER_CODE = re.compile(r"(?<![A-Za-z0-9])MP(?=\d|\b)", re.IGNORECASE)


def mask_provider_code(text) -> str:
    """Samarkan kode internal provider (MP, MP1, MP 5) jadi TP, TP1, TP 5.

    Kode ini bukan identitas layanan yang perlu diketahui user, jadi diubah
    sejak data masuk dan juga saat katalog lama dimuat ulang.
    """
    return _PROVIDER_CODE.sub("TP", str(text or ""))


async def mask_catalog_codes() -> int:
    """Ubah kode MP lama di katalog yang sudah tersimpan menjadi TP."""
    changed = 0
    for table, column in (("services", "name"), ("services", "description"),
                          ("categories", "name")):
        rows = await q(f"SELECT id,{column} AS value FROM {table}")
        updates = []
        for row in rows:
            old = row["value"] or ""
            new = mask_provider_code(old)
            if new != old:
                updates.append((new, row["id"]))
        if updates:
            await _db.executemany(f"UPDATE {table} SET {column}=? WHERE id=?", updates)
            changed += len(updates)
    if changed:
        await _db.commit()
    return changed


def hitung_harga(modal: int, persen: int, flat: int = 0) -> int:
    """Harga jual minimal agar tidak rugi. Modal provider tidak pernah ditampilkan ke user."""
    if modal <= 0:
        return 0
    return -(-modal * (100 + max(0, persen)) // 100) + max(0, flat)


async def suggested_price(modal: int) -> int:
    pct = int(await setting("markup_percent") or 0)
    flat = int(await setting("markup_flat") or 0)
    return hitung_harga(modal, pct, flat)


async def effective_price(svc) -> int:
    """Harga yang benar-benar dipakai user: tidak pernah di bawah modal + margin."""
    base = int(svc["price_per_1k"] or 0)
    if not svc["provider_price"]:
        return base
    return max(base, await suggested_price(int(svc["provider_price"])))


async def sorted_services(rows) -> list[dict]:
    """Urutkan layanan by harga jual termurah → termahal (tanpa query per baris).

    Tiap dict hasil punya kunci `_price` = harga efektif yang dipakai user.
    """
    pct = int(await setting("markup_percent") or 0)
    flat = int(await setting("markup_flat") or 0)
    out = []
    for s in rows:
        d = dict(s)
        modal = int(d.get("provider_price") or 0)
        base = int(d.get("price_per_1k") or 0)
        d["_price"] = max(base, hitung_harga(modal, pct, flat)) if modal else base
        out.append(d)
    return sorted(out, key=lambda d: (d["_price"], str(d.get("name") or "").lower()))


# Katalog provider punya ratusan sub-kategori. Menu user dikelompokkan dulu
# per platform supaya tidak menumpuk; kunci ASCII dipakai di callback Telegram.
PLATFORM_MAP = [
    ("instagram", "📸", "Instagram", ("instagram", "ig")),
    ("tiktok", "🎵", "TikTok", ("tiktok", "tik tok")),
    ("youtube", "▶️", "YouTube", ("youtube", "you tube", "yt")),
    ("facebook", "📘", "Facebook", ("facebook", "fb")),
    ("telegram", "✈️", "Telegram", ("telegram", "tg")),
    ("twitter", "🐦", "Twitter / X", ("twitter", "x")),
    ("whatsapp", "💬", "WhatsApp", ("whatsapp", "wa")),
    ("spotify", "🎧", "Spotify", ("spotify",)),
    ("shopee", "🛍", "Shopee", ("shopee",)),
    ("tokopedia", "🛍", "Tokopedia", ("tokopedia",)),
    ("lazada", "🛍", "Lazada", ("lazada",)),
    ("bukalapak", "🛍", "Bukalapak", ("bukalapak",)),
    ("threads", "🧵", "Threads", ("threads",)),
    ("twitch", "🎮", "Twitch", ("twitch",)),
    ("discord", "🎮", "Discord", ("discord",)),
    ("roblox", "🎮", "Roblox", ("roblox",)),
    ("soundcloud", "🎧", "SoundCloud", ("soundcloud", "sound cloud")),
    ("audiomack", "🎧", "Audiomack", ("audiomack",)),
    ("snackvideo", "🎬", "Snack Video", ("snackvideo", "snack video")),
    ("linkedin", "💼", "LinkedIn", ("linkedin", "linked in")),
    ("quora", "💬", "Quora", ("quora",)),
    ("google", "📍", "Google", ("google map", "google")),
    ("website", "🌐", "Website", ("website", "website traffic")),
]


def platform_of(text: str) -> tuple[str, str, str]:
    """Deteksi platform dari nama kategori/layanan. Fallback: Lainnya."""
    low = " " + re.sub(r"[^a-z0-9]+", " ", str(text or "").lower()) + " "
    for key, emoji, label, needles in PLATFORM_MAP:
        for needle in needles:
            n = re.sub(r"[^a-z0-9]+", " ", needle).strip()
            if not n:
                continue
            if len(n) <= 2:
                if f" {n} " in low:
                    return key, emoji, label
            elif n in low:
                return key, emoji, label
    return "lainnya", "📁", "Lainnya"


async def grouped_categories() -> list[dict]:
    """Platform → sub-kategori, lengkap dengan jumlah & harga termurah.

    Memakai harga efektif dari ``sorted_services`` dan tidak menambah query
    per layanan. Kategori tanpa layanan aktif otomatis tidak muncul.
    """
    svcs = await sorted_services(await q("SELECT * FROM services WHERE active=1"))
    if not svcs:
        return []
    cats = {int(r["id"]): dict(r) for r in await q("SELECT * FROM categories")}
    groups: dict[str, dict] = {}

    for s in svcs:
        cid = int(s.get("category_id") or 0)
        cat = cats.get(cid) or {"id": cid, "name": "Lainnya", "emoji": "📁"}
        cat_name = str(cat.get("name") or "Lainnya")
        svc_name = str(s.get("name") or "")
        key, emoji, label = platform_of(f"{cat_name} {svc_name}")

        g = groups.setdefault(key, {
            "key": key, "emoji": emoji, "label": label,
            "count": 0, "min_price": None, "cats": {},
        })
        g["count"] += 1
        if g["min_price"] is None or s["_price"] < g["min_price"]:
            g["min_price"] = s["_price"]

        c = g["cats"].setdefault(cid, {
            "id": cid, "name": cat_name, "emoji": cat.get("emoji") or "📁",
            "count": 0, "min_price": None,
        })
        c["count"] += 1
        if c["min_price"] is None or s["_price"] < c["min_price"]:
            c["min_price"] = s["_price"]

    out = []
    for g in groups.values():
        g["cats"] = sorted(g["cats"].values(),
                           key=lambda c: (c["min_price"], c["name"].lower()))
        out.append(g)
    out = sorted(out, key=lambda g: (g["min_price"], g["label"].lower()))

    # Preferensi katalog: WhatsApp menempati slot Twitch, Twitch pindah ke
    # posisi WhatsApp. Urutan platform lain tetap mengikuti harga termurah.
    idx_wa = next((i for i, g in enumerate(out) if g["key"] == "whatsapp"), None)
    idx_tw = next((i for i, g in enumerate(out) if g["key"] == "twitch"), None)
    if idx_wa is not None and idx_tw is not None and idx_wa != idx_tw:
        out[idx_wa], out[idx_tw] = out[idx_tw], out[idx_wa]
    return out


async def sync_services(items: list[dict]) -> dict:
    """Upsert layanan provider ke database. Harga hanya naik, tidak pernah turun otomatis.

    Mengembalikan juga ringkasan perubahan layanan/harga untuk diumumkan.
    """
    added = updated = changed = 0
    new_items, price_changes = [], []
    for it in items:
        pid = int(it["id"])
        modal = max(0, int(it.get("price") or 0))
        name = mask_provider_code(it.get("name") or f"Layanan {pid}")
        ptype = str(it.get("type") or "default")
        category = mask_provider_code(it.get("category") or "Lainnya")
        mn = max(0, int(it.get("min") or 0))
        mx = max(mn, int(it.get("max") or mn))
        desc = mask_provider_code(it.get("description") or "")
        refill = int(it.get("refill") or 0)
        avg = str(it.get("average_time") or "")
        cid = await get_or_create_category(category)
        cur = await q1("SELECT * FROM services WHERE provider_id=?", (pid,))
        now_at = now()
        if cur:
            old_price = cur["price_per_1k"]
            price = old_price
            if cur["auto_price"]:
                price = max(price, await suggested_price(modal))
            await x("UPDATE services SET name=?,category_id=?,provider_type=?,provider_price=?,provider_min=?,"
                    "provider_max=?,provider_refill=?,provider_avg=?,description=?,min_qty=?,max_qty=?,"
                    "price_per_1k=?,synced_at=?,source='provider' WHERE id=?",
                    (name, cid, ptype, modal, mn, mx, refill, avg, desc, mn, mx, price, now_at, cur["id"]))
            if price != old_price:
                changed += 1
                if len(price_changes) < 8:
                    price_changes.append({"name": name, "category": category,
                                          "old": old_price, "new": price})
            updated += 1
        else:
            price = await suggested_price(modal) or 1000
            await x("INSERT INTO services(category_id,name,price_per_1k,min_qty,max_qty,description,active,"
                    "provider_id,provider_type,provider_price,provider_min,provider_max,provider_refill,"
                    "provider_avg,auto_price,synced_at,source) VALUES(?,?,?,?,?,?,1,?,?,?,?,?,?,?,1,?,'provider')",
                    (cid, name, price, mn, mx, desc, pid, ptype, modal, mn, mx, refill, avg, now_at))
            if len(new_items) < 8:
                new_items.append({"name": name, "category": category, "price": price})
            added += 1
    # Layanan demo lama tidak ikut tampil setelah katalog asli masuk.
    if items:
        await x("UPDATE services SET active=0 WHERE source='manual' AND name LIKE '%[Demo]%'")
    return dict(added=added, updated=updated, total=len(items),
                new_count=added, changed_count=changed,
                new_items=new_items, price_changes=price_changes)


# ---------- users ----------
async def upsert_user(uid, name, username) -> bool:
    if await q1("SELECT 1 FROM users WHERE id=?", (uid,)):
        await x("UPDATE users SET name=?, username=? WHERE id=?", (name, username, uid))
        return False
    await x("INSERT INTO users(id,name,username,joined_at) VALUES(?,?,?,?)", (uid, name, username, now()))
    return True


async def get_user(uid):
    return await q1("SELECT * FROM users WHERE id=?", (uid,))


async def list_users(page: int = 0, per: int = 8, search: str = ""):
    """Daftar semua user untuk panel admin, bisa dicari & dibagi halaman."""
    page, per = max(0, int(page)), max(1, min(20, int(per)))
    s = (search or "").strip().lstrip("@").lower()
    where, args = "", []
    if s:
        if s.isdigit():
            where = "WHERE id=? OR LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(username,'')) LIKE ?"
            args = [int(s), f"%{s}%", f"%{s}%"]
        else:
            where = "WHERE LOWER(COALESCE(name,'')) LIKE ? OR LOWER(COALESCE(username,'')) LIKE ?"
            args = [f"%{s}%", f"%{s}%"]
    total = (await q1(f"SELECT COUNT(*) n FROM users {where}", args))["n"]
    pages = max(1, (total + per - 1) // per)
    page = min(page, pages - 1)
    rows = await q(f"SELECT * FROM users {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                   (*args, per, page * per))
    return rows, total, page, pages


async def set_channel_status(uid, status: str):
    """Simpan status register channel. Return status lama (panggilnya yang cek perubahannya)."""
    u = await get_user(uid)
    if not u:
        return None
    old = u["channel_status"] or "pending"
    if old == status:
        return old
    ts = now()
    if status == "joined":
        await x("UPDATE users SET channel_status=?, channel_checked_at=?, "
                "channel_joined_at=COALESCE(channel_joined_at,?) WHERE id=?", (status, ts, ts, uid))
    else:
        await x("UPDATE users SET channel_status=?, channel_checked_at=? WHERE id=?", (status, ts, uid))
    return old


async def add_balance(uid, amt, type_, note=""):
    await x("UPDATE users SET balance=balance+? WHERE id=?", (amt, uid))
    await x("INSERT INTO transactions(user_id,type,amount,note,created_at) VALUES(?,?,?,?,?)",
            (uid, type_, amt, note, now()))


async def debit(uid, amt, type_, note="") -> bool:
    c = await x("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?", (amt, uid, amt))
    if c.rowcount == 0:
        return False
    await x("INSERT INTO transactions(user_id,type,amount,note,created_at) VALUES(?,?,?,?,?)",
            (uid, type_, -amt, note, now()))
    return True


async def set_referrer(uid, ref):
    if ref == uid or not await get_user(ref):
        return None
    c = await x("UPDATE users SET referred_by=?, referred_at=? WHERE id=? AND referred_by IS NULL",
                (ref, now(), uid))
    if c.rowcount == 0:
        return None
    bonus = int(await setting("ref_signup_bonus") or 0)
    if bonus > 0:
        await add_balance(ref, bonus, "referral", f"Bonus undangan {uid}")
        await x("UPDATE users SET ref_earned=ref_earned+? WHERE id=?", (bonus, ref))
    return bonus


async def referral_count(uid) -> int:
    return (await q1("SELECT COUNT(*) n FROM users WHERE referred_by=?", (uid,)))["n"]


# ---------- deposits ----------
async def active_deposits(uid):
    """Invoice yang masih bisa dibayar (belum lunas/expired)."""
    return await q("SELECT * FROM deposits WHERE user_id=? AND status='pending' ORDER BY id DESC", (uid,))


async def create_deposit(uid, amount, method, ref="", info=None) -> int:
    info = info or {}
    c = await x("INSERT INTO deposits(user_id,amount,method,ref,created_at,invoice_id,qris_image,"
                "payment_link,expired_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (uid, amount, method, ref, now(), info.get("invoice_id") or ref,
                 info.get("qris_image", ""), info.get("payment_link", ""), info.get("expired_at")))
    return c.lastrowid


async def confirm_deposit(dep_id):
    """Return (deposit_row, None, 0) atau None jika sudah diproses.

    Komisi referral sengaja tidak dibayar saat deposit: deposit bukan pendapatan,
    jadi dibayar setelah order sukses dari margin yang benar-benar didapat.
    """
    c = await x("UPDATE deposits SET status='success', paid_at=? WHERE id=? AND status='pending'",
                (now(), dep_id))
    if c.rowcount == 0:
        return None
    d = await q1("SELECT * FROM deposits WHERE id=?", (dep_id,))
    await add_balance(d["user_id"], d["amount"], "deposit", f"Deposit #{dep_id}")
    return d, None, 0


async def confirm_deposit_by_invoice(invoice_id):
    """Dipanggil saat gateway QRIS melaporkan status paid (cek manual/polling)."""
    d = await q1("SELECT * FROM deposits WHERE invoice_id=? OR ref=? ORDER BY id DESC LIMIT 1",
                 (str(invoice_id), str(invoice_id)))
    if not d:
        return None
    return await confirm_deposit(d["id"])


async def expire_deposit_by_invoice(invoice_id) -> bool:
    d = await q1("SELECT id FROM deposits WHERE invoice_id=? OR ref=? ORDER BY id DESC LIMIT 1",
                 (str(invoice_id), str(invoice_id)))
    if not d:
        return False
    c = await x("UPDATE deposits SET status='expired' WHERE id=? AND status='pending'", (d["id"],))
    return c.rowcount > 0


async def pending_invoices():
    return await q("SELECT * FROM deposits WHERE status='pending' AND invoice_id IS NOT NULL "
                   "AND invoice_id!='' ORDER BY id")


# ---------- orders ----------
async def create_order(uid, svc, link, qty, price, extra=None):
    extra_json = json.dumps(extra or {}, ensure_ascii=False)
    note = f"Order {svc['name']}" + (f" x{qty}" if qty else "")
    if not await debit(uid, price, "order", note):
        return None
    c = await x("INSERT INTO orders(user_id,service_id,service_name,link,quantity,price,created_at,"
                "provider_id,provider_type,provider_price,extra) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (uid, svc["id"], svc["name"], link, qty, price, now(),
                 svc["provider_id"], svc["provider_type"], int(svc["provider_price"] or 0), extra_json))
    await x("UPDATE users SET total_order=total_order+1, total_spent=total_spent+? WHERE id=?", (price, uid))
    return c.lastrowid


async def cancel_order(oid) -> bool:
    o = await q1("SELECT * FROM orders WHERE id=?", (oid,))
    if not o:
        return False
    c = await x("UPDATE orders SET status='Canceled' WHERE id=? AND status IN ('Pending','Processing')", (oid,))
    if c.rowcount == 0:
        return False
    await add_balance(o["user_id"], o["price"], "refund", f"Refund order #{oid}")
    # Komisi yang sudah dibayar ikut ditarik supaya refund tidak bikin rugi.
    if int(o["ref_bonus"] or 0) > 0 and o["ref_bonus_user"]:
        await add_balance(o["ref_bonus_user"], -int(o["ref_bonus"]), "referral",
                          f"Tarik komisi order #{oid} (dibatalkan)")
        await x("UPDATE users SET ref_earned=MAX(0,ref_earned-?) WHERE id=?",
                (o["ref_bonus"], o["ref_bonus_user"]))
        await x("UPDATE orders SET ref_bonus=0, ref_bonus_user=NULL WHERE id=?", (oid,))
    return True


def _order_billable(o) -> int:
    """Satuan tagihan order: qty, jumlah baris komentar/username, atau 1 paket."""
    qty = int(o["quantity"] or 0)
    if qty > 0:
        return qty
    try:
        extra = json.loads(o["extra"] or "{}")
    except (TypeError, ValueError):
        extra = {}
    for key in ("comments", "usernames"):
        val = extra.get(key)
        if val:
            return max(1, len([line for line in str(val).splitlines() if line.strip()]))
    return 1000 if o["provider_type"] == "package" else 1


async def pay_order_referral(oid):
    """Bayar komisi sekali, hanya dari margin order yang sudah Completed.

    Return (bonus, referrer_id). ref_percent dipatok maks 50% margin supaya
    bot tetap untung. Modal provider hanya dipakai internal, tidak bocor ke user.
    """
    o = await q1("SELECT * FROM orders WHERE id=? AND status='Completed'", (oid,))
    if not o or int(o["ref_bonus"] or 0) > 0:
        return 0, None
    u = await get_user(o["user_id"])
    ref = u["referred_by"] if u else None
    days = max(0, int(await setting("ref_days") or 0))
    if ref and days:
        # DB lama belum punya referred_at → awal masa komisi pakai tanggal join.
        start = u["referred_at"] or u["joined_at"]
        try:
            joined = datetime.strptime(start, "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB)
            placed = datetime.strptime(o["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB)
        except (TypeError, ValueError):
            return 0, None
        if placed < joined or (placed - joined).days >= days:
            return 0, None
    modal = int(o["provider_price"] or 0)
    if not modal and o["service_id"]:
        s = await q1("SELECT provider_price FROM services WHERE id=?", (o["service_id"],))
        modal = int(s["provider_price"] or 0) if s else 0
    billable = _order_billable(o)
    if not ref or modal <= 0 or billable <= 0:
        return 0, None
    cost = math.ceil(modal * billable / 1000)
    margin = max(0, int(o["price"]) - cost)
    pct = max(0, min(50, int(await setting("ref_percent") or 0)))
    bonus = margin * pct // 100
    if bonus <= 0:
        return 0, None
    await add_balance(ref, bonus, "referral", f"Komisi order #{oid}")
    await x("UPDATE users SET ref_earned=ref_earned+? WHERE id=?", (bonus, ref))
    await x("UPDATE orders SET ref_bonus=?, ref_bonus_user=? WHERE id=?", (bonus, ref, oid))
    return bonus, ref


# ---------- shop ----------
async def buy_product(uid, pid):
    """Return (ok, pesan_atau_data, produk)."""
    p = await q1("SELECT * FROM products WHERE id=? AND active=1", (pid,))
    if not p:
        return False, "Produk tidak tersedia.", None
    stock = await q1("SELECT * FROM product_stock WHERE product_id=? AND sold=0 ORDER BY id LIMIT 1", (pid,))
    if not stock:
        return False, "Stok habis.", p
    if not await debit(uid, p["price"], "purchase", f"Beli {p['name']}"):
        return False, "Saldo tidak cukup.", p
    c = await x("UPDATE product_stock SET sold=1 WHERE id=? AND sold=0", (stock["id"],))
    if c.rowcount == 0:
        await add_balance(uid, p["price"], "refund", f"Refund {p['name']}")
        return False, "Stok baru saja habis, saldo dikembalikan.", p
    await x("INSERT INTO purchases(user_id,product_id,name,price,data,created_at) VALUES(?,?,?,?,?,?)",
            (uid, pid, p["name"], p["price"], stock["data"], now()))
    await x("UPDATE users SET total_spent=total_spent+? WHERE id=?", (p["price"], uid))
    return True, stock["data"], p


# ---------- missions ----------
async def mission_state(uid, m):
    """Return (progress, claimed)."""
    t = m["type"]
    if t == "orders":
        prog = (await get_user(uid))["total_order"]
    elif t == "deposit":
        prog = (await q1("SELECT COALESCE(SUM(amount),0) s FROM deposits WHERE user_id=? AND status='success'", (uid,)))["s"]
    elif t == "referral":
        prog = await referral_count(uid)
    else:  # daily
        prog = m["target"]
    period = today() if t == "daily" else "once"
    claimed = bool(await q1("SELECT 1 FROM mission_claims WHERE user_id=? AND mission_id=? AND period=?",
                            (uid, m["id"], period)))
    return prog, claimed


async def claim_mission(uid, mid):
    m = await q1("SELECT * FROM missions WHERE id=? AND active=1", (mid,))
    if not m:
        return False, "Misi tidak ditemukan.", 0
    prog, claimed = await mission_state(uid, m)
    if claimed:
        return False, "Misi sudah diklaim.", 0
    if prog < m["target"]:
        return False, "Misi belum selesai.", 0
    period = today() if m["type"] == "daily" else "once"
    c = await x("INSERT OR IGNORE INTO mission_claims(user_id,mission_id,period) VALUES(?,?,?)", (uid, mid, period))
    if c.rowcount == 0:
        return False, "Misi sudah diklaim.", 0
    await add_balance(uid, m["reward"], "mission", f"Misi: {m['title']}")
    return True, m["title"], m["reward"]


# ---------- stats ----------
async def top_spenders(limit: int = 3, period: str = "all"):
    """Papan peringkat rupiah: all / week (7 hari) / month (30 hari)."""
    limit = max(1, min(50, int(limit)))
    if period not in ("week", "month"):
        return await q("SELECT id, name, username, total_order, total_spent FROM users "
                       "WHERE total_spent>0 ORDER BY total_spent DESC, total_order DESC, id ASC LIMIT ?",
                       (limit,))
    days = 7 if period == "week" else 30
    since = (datetime.now(WIB) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    return await q("SELECT u.id, u.name, u.username, COUNT(o.id) total_order, "
                   "COALESCE(SUM(o.price),0) total_spent FROM users u "
                   "JOIN orders o ON o.user_id=u.id "
                   "WHERE o.created_at>=? AND o.status!='Canceled' "
                   "GROUP BY u.id HAVING SUM(o.price)>0 "
                   "ORDER BY SUM(o.price) DESC, COUNT(o.id) DESC, u.id ASC LIMIT ?", (since, limit))


async def global_stats():
    g = lambda r: r[0] if r and r[0] else 0
    users = g(await q1("SELECT COUNT(*) FROM users"))
    orders = g(await q1("SELECT COUNT(*) FROM orders"))
    rev_o = g(await q1("SELECT SUM(price) FROM orders WHERE status!='Canceled'"))
    rev_p = g(await q1("SELECT SUM(price) FROM purchases"))
    dep = g(await q1("SELECT SUM(amount) FROM deposits WHERE status='success'"))
    today_users = g(await q1("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (today() + "%",)))
    today_orders = g(await q1("SELECT COUNT(*) FROM orders WHERE created_at LIKE ?", (today() + "%",)))
    today_rev = g(await q1("SELECT SUM(price) FROM orders WHERE created_at LIKE ? AND status!='Canceled'", (today() + "%",)))
    pending_dep = g(await q1("SELECT COUNT(*) FROM deposits WHERE status='pending'"))
    active_orders = g(await q1("SELECT COUNT(*) FROM orders WHERE status IN ('Pending','Processing')"))
    balance = g(await q1("SELECT SUM(balance) FROM users"))
    return dict(users=users, orders=orders, revenue=rev_o + rev_p, deposits=dep, today_users=today_users,
                today_orders=today_orders, today_rev=today_rev, pending_dep=pending_dep,
                active_orders=active_orders, balance=balance)
