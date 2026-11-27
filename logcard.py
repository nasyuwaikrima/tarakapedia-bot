"""Kartu aktivitas & sambutan bergaya dashboard untuk Telegram.

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

W = 1200
PAD = 64
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG_TOP = (8, 12, 26)
BG_BOTTOM = (17, 26, 50)
CARD = (22, 31, 56)
CARD_ALT = (29, 40, 70)
STROKE = (44, 60, 96)
TEXT = (240, 245, 255)
MUTED = (149, 166, 199)
TEAL = (66, 226, 184)
BLUE = (94, 160, 252)
VIOLET = (167, 139, 250)
GOLD = (255, 203, 103)

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


def _gradient_bar(draw, box, colors):
    x0, y0, x1, y1 = box
    steps = max(1, x1 - x0)
    for i in range(steps):
        k = i / (steps - 1) if steps > 1 else 0
        seg = min(k * (len(colors) - 1), len(colors) - 2)
        a, b = colors[int(seg)], colors[int(seg) + 1]
        f = k * (len(colors) - 1) - int(seg)
        color = tuple(int(a[j] + (b[j] - a[j]) * f) for j in range(3))
        draw.line((x0 + i, y0, x0 + i, y1), fill=color)


def render(text, title: str | None = None, badge: str | None = None,
           footer: str | None = None, tiles=None) -> io.BytesIO:
    """Kembalikan PNG kartu dashboard dalam memory buffer."""
    if Image is None:
        raise RuntimeError("Pillow tidak tersedia")
    data = parse(text, title, badge, footer, tiles)
    rows = data["rows"]
    height = 596 + len(rows) * 92
    img = Image.new("RGB", (W, height), BG_TOP)
    d = ImageDraw.Draw(img)

    # Latar gradasi, grid halus, dan dua glow.
    for y in range(height):
        k = y / max(1, height - 1)
        d.line((0, y, W, y), fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k)
                                        for i in range(3)))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for x in range(0, W, 48):
        od.line((x, 0, x, height), fill=(255, 255, 255, 5))
    for y in range(0, height, 48):
        od.line((0, y, W, y), fill=(255, 255, 255, 5))
    od.ellipse((W - 320, -210, W + 150, 260), fill=(*BLUE, 28))
    od.ellipse((-190, height - 320, 230, height + 120), fill=(*TEAL, 20))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    f_brand = _font(23, True)
    f_small = _font(20)
    f_title = _font(52, True)
    f_label = _font(19, True)
    f_value = _font(31, True)
    f_row = _font(26)
    f_footer = _font(19)

    # Garis aksen atas + navbar.
    _gradient_bar(d, (PAD, 46, W - PAD, 54), [TEAL, BLUE, VIOLET])
    d.ellipse((PAD, 74, PAD + 48, 122), fill=(20, 58, 61))
    d.text((PAD + 14, 82), "T", font=_font(27, True), fill=TEAL)
    d.text((PAD + 66, 84), "TARAKAPEDIA  ·  SMM PANEL", font=f_brand, fill=TEXT)
    now = datetime.now(timezone(timedelta(hours=7)))
    stamp = now.strftime("%H:%M WIB")
    tw = int(d.textlength(stamp, font=f_small))
    d.rounded_rectangle((W - PAD - tw - 70, 76, W - PAD, 120), radius=16, fill=(19, 52, 49))
    d.ellipse((W - PAD - tw - 56, 91, W - PAD - tw - 46, 101), fill=TEAL)
    d.text((W - PAD - tw - 34, 84), stamp, font=f_small, fill=TEXT)

    # Hero.
    d.text((PAD, 152), "TARAKAPEDIA  /  AKTIVITAS LANGSUNG", font=f_label, fill=BLUE)
    d.text((PAD, 194), _fit(d, data["title"], f_title, 790), font=f_title, fill=TEXT)
    badge_font = _font(27, True) if MONEY.fullmatch(data["badge"]) else _font(22, True)
    bw = int(d.textlength(data["badge"], font=badge_font)) + 52
    bx = max(PAD + 820, W - PAD - bw)
    d.rounded_rectangle((bx, 236, W - PAD, 292), radius=20,
                        fill=(24, 62, 56) if MONEY.fullmatch(data["badge"]) else (29, 42, 74))
    d.text((bx + 26, 250), data["badge"], font=badge_font,
           fill=GOLD if MONEY.fullmatch(data["badge"]) else BLUE)

    # Tiga metrik ringkas, terasa seperti dashboard.
    tiles = data["tiles"] or [
        ("AKTIVITAS", _fit(d, data["title"], f_value, 250)),
        ("NOMINAL", data["badge"] if MONEY.fullmatch(data["badge"]) else "—"),
        ("WAKTU", stamp),
    ]
    gap, tw3 = 22, (W - 2 * PAD - 2 * 22) // 3
    for i, (label, value) in enumerate(tiles[:3]):
        x = PAD + i * (tw3 + gap)
        d.rounded_rectangle((x, 326, x + tw3, 462), radius=22, fill=CARD if i % 2 == 0 else CARD_ALT,
                            outline=STROKE, width=2)
        d.rounded_rectangle((x, 350, x + 6, 438), radius=3, fill=[TEAL, BLUE, VIOLET][i])
        d.text((x + 26, 348), _fit(d, label, f_label, tw3 - 50), font=f_label, fill=MUTED)
        d.text((x + 26, 389), _fit(d, value, f_value, tw3 - 50), font=f_value, fill=TEXT)

    # Detail transaksi.
    y = 498
    for i, row in enumerate(rows):
        d.rounded_rectangle((PAD, y, W - PAD, y + 76), radius=18,
                            fill=CARD if i % 2 == 0 else CARD_ALT, outline=STROKE, width=1)
        d.ellipse((PAD + 20, y + 22, PAD + 54, y + 56), fill=[TEAL, BLUE, VIOLET][i % 3])
        initial = next((c.upper() for c in row if c.isalnum()), str(i + 1))
        d.text((PAD + 29, y + 27), initial, font=_font(20, True), fill=(10, 16, 32))
        d.text((PAD + 72, y + 23), _fit(d, row, f_row, W - 2 * PAD - 110), font=f_row, fill=TEXT)
        y += 92

    d.text((PAD, height - 62), _fit(d, data["footer"], f_footer, W - 2 * PAD - 200),
           font=f_footer, fill=MUTED)
    d.ellipse((W - PAD - 160, height - 54, W - PAD - 148, height - 42), fill=TEAL)
    d.text((W - PAD - 136, height - 62), "VERIFIED LIVE", font=f_footer, fill=MUTED)

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
    """Kartu sambutan untuk user baru dengan gaya dashboard yang sama."""
    clean_name = (clean(name) or "Pengguna")[:40]
    return photo(
        f"👤 {clean_name}\n"
        "⚡ Order otomatis 24/7\n"
        "💸 Deposit QRIS dengan konfirmasi otomatis\n"
        "🎁 Komisi referral hingga 7 hari",
        title="SELAMAT DATANG DI TARAKAPEDIA",
        badge="MEMBER BARU",
        footer="Gabung 2 channel untuk mulai bertransaksi  ·  Tarakapedia",
        tiles=[("PENGGUNA", clean_name[:16]), ("AKSES", "24/7"), ("STATUS", "BARU")],
    )
