"""Kartu dashboard & sambutan bergaya modern untuk Telegram.

Gambar dibuat otomatis dengan Pillow. Modul ini opsional: bila Pillow atau font
tidak tersedia, pemanggil tetap bisa mengirim pesan berbentuk teks.
"""
from __future__ import annotations

import html
import io
import re
from datetime import datetime, timedelta, timezone

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - dependency opsional
    Image = None

W = 1280
PAD = 68
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG_TOP = (7, 11, 25)
BG_BOTTOM = (18, 27, 54)
CARD = (23, 33, 60)
CARD_ALT = (31, 43, 76)
SHADOW = (5, 9, 20)
STROKE = (48, 65, 104)
TEXT = (242, 246, 255)
MUTED = (153, 170, 203)
TEAL = (64, 226, 183)
BLUE = (92, 160, 252)
VIOLET = (170, 140, 252)
GOLD = (255, 204, 104)

TAG = re.compile(r"<[^>]+>")
EMOJI = re.compile(
    "[" "\U0001F000-\U0001FAFF" "\U0001F1E6-\U0001F1FF"
    "\u2600-\u27BF" "\uFE0F" "\u2190-\u21FF" "\u2B00-\u2BFF" "]"
)
MONEY = re.compile(r"Rp\s?[\d.]+")


def clean(text) -> str:
    """Ubah HTML caption jadi teks polos untuk dirender di gambar."""
    return (html.unescape(TAG.sub("", str(text or "")))
            .replace("\r", "")
            .replace("\u00a0", " ")
            .strip())


def parse(text, title: str | None = None, badge: str | None = None,
          footer: str | None = None, tiles=None) -> dict:
    lines = [x.strip() for x in clean(text).splitlines() if x.strip()]
    headline = clean(title) if title else (lines.pop(0) if lines else "AKTIVITAS")
    rows = [x for x in lines if not x.startswith("🔗")]
    joined = " ".join(rows)
    money = MONEY.search(joined)
    return {
        "title": (EMOJI.sub("", headline).strip() or "AKTIVITAS"),
        "rows": [EMOJI.sub("", x).strip() for x in rows[:5]],
        "badge": clean(badge) if badge else (money.group(0).strip() if money else "LIVE UPDATE"),
        "footer": clean(footer) or "Diproses otomatis 24/7  ·  Tarakapedia SMM Panel",
        "tiles": tiles or [],
    }


def _font(size: int, bold: bool = False):
    if Image is None:
        return None
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REG, size)
    except OSError:
        return ImageFont.load_default(size)


def _fit(draw, text: str, font, width: int) -> str:
    text = str(text)
    if draw.textlength(text, font=font) <= width:
        return text
    while text and draw.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return (text + "…").strip()


def _base(height: int, glows=True):
    img = Image.new("RGB", (W, height), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(height):
        k = y / max(1, height - 1)
        d.line((0, y, W, y), fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k)
                                        for i in range(3)))
    if not glows:
        return img, d
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, W, 52):
        od.line((x, 0, x, height), fill=(255, 255, 255, 4))
    for y in range(0, height, 52):
        od.line((0, y, W, y), fill=(255, 255, 255, 4))
    od.ellipse((W - 340, -220, W + 160, 280), fill=(*BLUE, 26))
    od.ellipse((-200, height - 340, 240, height + 130), fill=(*TEAL, 20))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img, ImageDraw.Draw(img)


def _shadow_card(d, box, fill, radius=22, outline=STROKE):
    x0, y0, x1, y1 = box
    d.rounded_rectangle((x0, y0 + 10, x1, y1 + 10), radius=radius, fill=SHADOW)
    d.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=2)


def _gradient_bar(d, box, colors):
    x0, y0, x1, y1 = box
    steps = max(1, x1 - x0)
    for i in range(steps):
        k = i / (steps - 1) if steps > 1 else 0
        seg = min(k * (len(colors) - 1), len(colors) - 2)
        a, b = colors[int(seg)], colors[int(seg) + 1]
        f = k * (len(colors) - 1) - int(seg)
        d.line((x0 + i, y0, x0 + i, y1),
               fill=tuple(int(a[j] + (b[j] - a[j]) * f) for j in range(3)))


def _stamp() -> str:
    return datetime.now(timezone(timedelta(hours=7))).strftime("%H:%M WIB")


def render(text, title: str | None = None, badge: str | None = None,
           footer: str | None = None, tiles=None) -> io.BytesIO:
    """PNG dashboard aktivitas: navbar, metrik, dan detail transaksi."""
    if Image is None:
        raise RuntimeError("Pillow tidak tersedia")
    data = parse(text, title, badge, footer, tiles)
    rows = data["rows"]
    height = 640 + len(rows) * 98
    img, d = _base(height)

    f_brand = _font(24, True)
    f_small = _font(20)
    f_title = _font(55, True)
    f_label = _font(19, True)
    f_value = _font(33, True)
    f_row = _font(27)
    f_footer = _font(19)
    stamp = _stamp()

    _gradient_bar(d, (PAD, 48, W - PAD, 57), [TEAL, BLUE, VIOLET])
    d.ellipse((PAD, 78, PAD + 50, 128), fill=(20, 58, 61))
    d.text((PAD + 15, 86), "T", font=_font(29, True), fill=TEAL)
    d.text((PAD + 70, 88), "TARAKAPEDIA  ·  SMM PANEL", font=f_brand, fill=TEXT)
    tw = int(d.textlength(stamp, font=f_small))
    d.rounded_rectangle((W - PAD - tw - 74, 80, W - PAD, 126), radius=18, fill=(19, 52, 49))
    d.ellipse((W - PAD - tw - 60, 97, W - PAD - tw - 50, 107), fill=TEAL)
    d.text((W - PAD - tw - 38, 86), stamp, font=f_small, fill=TEXT)

    d.text((PAD, 162), "TARAKAPEDIA  /  AKTIVITAS LANGSUNG", font=f_label, fill=BLUE)
    d.text((PAD, 205), _fit(d, data["title"], f_title, 860), font=f_title, fill=TEXT)
    money_badge = bool(MONEY.fullmatch(data["badge"]))
    badge_font = _font(28, True) if money_badge else _font(23, True)
    bw = int(d.textlength(data["badge"], font=badge_font)) + 56
    bx = max(PAD + 880, W - PAD - bw)
    d.rounded_rectangle((bx, 250, W - PAD, 312), radius=22,
                        fill=(24, 62, 56) if money_badge else (30, 43, 78))
    d.text((bx + 28, 266), data["badge"], font=badge_font, fill=GOLD if money_badge else BLUE)

    tiles = data["tiles"] or [
        ("AKTIVITAS", _fit(d, data["title"], f_value, 270)),
        ("NOMINAL", data["badge"] if money_badge else "—"),
        ("WAKTU", stamp),
    ]
    gap = 24
    tw3 = (W - 2 * PAD - 2 * gap) // 3
    for i, (label, value) in enumerate(tiles[:3]):
        x = PAD + i * (tw3 + gap)
        _shadow_card(d, (x, 344, x + tw3, 488), CARD if i % 2 == 0 else CARD_ALT)
        color = [TEAL, GOLD, VIOLET][i]
        d.ellipse((x + 24, 366, x + 68, 410), fill=color)
        d.text((x + 34, 372), label[:1], font=_font(23, True), fill=(10, 16, 32))
        d.text((x + 24, 424), _fit(d, label, f_label, tw3 - 48), font=f_label, fill=MUTED)
        d.text((x + 24, 448), _fit(d, value, _font(27, True), tw3 - 48),
               font=_font(27, True), fill=TEXT)

    y = 522
    for i, row in enumerate(rows):
        _shadow_card(d, (PAD, y, W - PAD, y + 80), CARD if i % 2 == 0 else CARD_ALT, radius=20,
                     outline=SHADOW)
        color = [TEAL, BLUE, VIOLET][i % 3]
        d.rounded_rectangle((PAD + 20, y + 18, PAD + 60, y + 62), radius=12, fill=color)
        initial = next((c.upper() for c in row if c.isalnum()), str(i + 1))
        d.text((PAD + 32, y + 27), initial, font=_font(21, True), fill=(10, 16, 32))
        d.text((PAD + 78, y + 24), _fit(d, row, f_row, W - 2 * PAD - 120), font=f_row, fill=TEXT)
        y += 98

    d.line((PAD, height - 92, W - PAD, height - 92), fill=STROKE, width=2)
    d.text((PAD, height - 66), _fit(d, data["footer"], f_footer, W - 2 * PAD - 210),
           font=f_footer, fill=MUTED)
    d.ellipse((W - PAD - 170, height - 58, W - PAD - 158, height - 46), fill=TEAL)
    d.text((W - PAD - 146, height - 66), "VERIFIED LIVE", font=f_footer, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def render_welcome(name: str) -> io.BytesIO:
    """PNG sambutan khusus: poster vertikal, berbeda dari kartu transaksi."""
    if Image is None:
        raise RuntimeError("Pillow tidak tersedia")
    clean_name = (clean(name) or "Pengguna")[:32]
    height = 1120
    img, d = _base(height)

    f_kicker = _font(21, True)
    f_h1 = _font(76, True)
    f_h2 = _font(44, True)
    f_name = _font(46, True)
    f_body = _font(24)
    f_step = _font(27, True)
    f_desc = _font(20)
    f_small = _font(19)

    _gradient_bar(d, (PAD, 48, W - PAD, 58), [VIOLET, TEAL, BLUE])

    # Hero sambutan.
    d.text((PAD, 108), "SELAMAT DATANG", font=f_kicker, fill=TEAL)
    d.text((PAD, 152), "HALO, " + _fit(d, clean_name, f_h1, 820).upper(), font=f_h1, fill=TEXT)
    d.text((PAD, 252), "Tarakapedia SMM Panel", font=f_h2, fill=VIOLET)
    d.text((PAD, 326), "Akun Anda sudah aktif. Tiga langkah singkat sebelum mulai memesan.",
           font=f_body, fill=MUTED)

    # Kartu identitas dengan status aktif.
    _shadow_card(d, (PAD, 392, W - PAD, 542), CARD, radius=26)
    d.ellipse((PAD + 30, 424, PAD + 94, 488), fill=TEAL)
    d.text((PAD + 47, 435), "✓", font=_font(38, True), fill=(10, 16, 32))
    d.text((PAD + 118, 424), _fit(d, clean_name, f_name, 760), font=f_name, fill=TEXT)
    d.text((PAD + 120, 486), "MEMBER BARU  ·  STATUS AKTIF", font=f_small, fill=MUTED)

    # Tiga langkah, bukan metrik transaksi.
    steps = [
        ("01", "GABUNG 2 CHANNEL", "@tarakapedia & @tarakapedia_log", TEAL),
        ("02", "ISI SALDO QRIS", "Deposit lunas otomatis tanpa webhook", BLUE),
        ("03", "PILIH & ORDER", "Ratusan layanan, proses otomatis 24/7", VIOLET),
    ]
    gap, cw = 24, (W - 2 * PAD - 48) // 3
    for i, (num, title, desc, color) in enumerate(steps):
        x = PAD + i * (cw + gap)
        _shadow_card(d, (x, 582, x + cw, 864), CARD if i % 2 == 0 else CARD_ALT, radius=24)
        d.rounded_rectangle((x + 24, 606, x + 92, 672), radius=16, fill=color)
        d.text((x + 36, 617), num, font=_font(27, True), fill=(10, 16, 32))
        d.text((x + 24, 700), title, font=_font(23, True), fill=TEXT)
        d.text((x + 24, 748), _fit(d, desc, f_desc, cw - 48), font=f_desc, fill=MUTED)

    # Pita syarat keikutsertaan.
    d.rounded_rectangle((PAD, 912, W - PAD, 1012), radius=24, fill=(20, 58, 61))
    d.ellipse((PAD + 28, 938, PAD + 58, 968), fill=TEAL)
    d.text((PAD + 78, 936), "LANGKAH PERTAMA: gabung kedua channel, lalu tekan tombol konfirmasi.",
           font=f_body, fill=TEXT)

    d.line((PAD, 1052, W - PAD, 1052), fill=STROKE, width=2)
    d.text((PAD, 1072), "Selamat bertransaksi  ·  Tarakapedia SMM Panel", font=f_small, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def photo(text, title: str | None = None, badge: str | None = None,
          footer: str | None = None, tiles=None):
    """BufferedInputFile siap dikirim lewat Bot API."""
    from aiogram.types import BufferedInputFile

    raw = render(text, title, badge, footer, tiles)
    return BufferedInputFile(raw.getvalue(), filename="activity.png")


def welcome_photo(name: str):
    """Kartu sambutan khusus untuk user baru."""
    from aiogram.types import BufferedInputFile

    raw = render_welcome(name)
    return BufferedInputFile(raw.getvalue(), filename="welcome.png")
