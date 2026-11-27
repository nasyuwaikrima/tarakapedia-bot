"""Kartu aktivitas bergaya dashboard untuk log channel.

Gambar dibuat otomatis dengan Pillow. Modul ini sengaja opsional: bila Pillow
atau font tidak tersedia, pemanggil tetap bisa mengirim log berbentuk teks.
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

W = 1080
PAD = 56
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

BG_TOP = (9, 14, 30)
BG_BOTTOM = (18, 28, 52)
CARD = (23, 33, 58)
CARD_ALT = (31, 43, 73)
TEXT = (236, 243, 255)
MUTED = (150, 166, 197)
ACCENT = (72, 224, 187)
BLUE = (96, 165, 250)
GOLD = (255, 207, 102)

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
          footer: str | None = None) -> dict:
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


def render(text, title: str | None = None, badge: str | None = None,
           footer: str | None = None) -> io.BytesIO:
    """Kembalikan PNG kartu aktivitas dalam memory buffer."""
    if Image is None:
        raise RuntimeError("Pillow tidak tersedia")
    data = parse(text, title, badge, footer)
    rows = data["rows"]
    height = 306 + len(rows) * 78 + 74
    img = Image.new("RGB", (W, height), BG_TOP)
    d = ImageDraw.Draw(img)

    # Latar gradasi halus + aksen lingkaran.
    for y in range(height):
        k = y / max(1, height - 1)
        d.line((0, y, W, y), fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * k)
                                        for i in range(3)))
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.ellipse((W - 250, -170, W + 130, 210), fill=(*BLUE, 26))
    od.ellipse((-170, height - 260, 190, height + 100), fill=(*ACCENT, 18))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(img)

    f_brand = _font(22, True)
    f_small = _font(20)
    f_title = _font(42, True)
    f_row = _font(26)
    f_footer = _font(19)

    # Header branding.
    d.rounded_rectangle((PAD, 42, W - PAD, 122), radius=20, fill=CARD)
    d.rounded_rectangle((PAD, 58, PAD + 8, 106), radius=4, fill=ACCENT)
    d.text((PAD + 30, 60), "TARAKAPEDIA  ·  SMM PANEL", font=f_brand, fill=TEXT)
    now = datetime.now(timezone(timedelta(hours=7))).strftime("%d %b %Y  ·  %H:%M WIB")
    tw = d.textlength(now, font=f_small)
    d.text((W - PAD - 28 - tw, 66), now, font=f_small, fill=MUTED)

    # Judul aktivitas + chip nominal bila ada.
    d.rounded_rectangle((PAD, 142, W - PAD, 268), radius=22, fill=CARD_ALT)
    d.rounded_rectangle((PAD + 26, 172, PAD + 34, 238), radius=4, fill=ACCENT)
    d.text((PAD + 54, 168), _fit(d, data["title"], f_title, 560), font=f_title, fill=TEXT)
    badge_font = _font(26, True) if MONEY.fullmatch(data["badge"]) else _font(22, True)
    aw = int(d.textlength(data["badge"], font=badge_font)) + 48
    x0 = max(PAD + 600, W - PAD - 26 - aw)
    d.rounded_rectangle((x0, 182, W - PAD - 26, 230), radius=14,
                        fill=(20, 58, 55) if MONEY.fullmatch(data["badge"]) else (20, 44, 77))
    d.text((x0 + 24, 191), data["badge"], font=badge_font,
           fill=GOLD if MONEY.fullmatch(data["badge"]) else BLUE)

    # Detail transaksi, satu baris per informasi.
    y = 292
    for i, row in enumerate(rows):
        d.rounded_rectangle((PAD, y, W - PAD, y + 66), radius=16,
                            fill=CARD if i % 2 == 0 else CARD_ALT)
        d.ellipse((PAD + 22, y + 25, PAD + 34, y + 37), fill=ACCENT if i % 2 == 0 else BLUE)
        d.text((PAD + 52, y + 18), _fit(d, row, f_row, W - 2 * PAD - 96), font=f_row, fill=TEXT)
        y += 78

    d.text((PAD, height - 54), _fit(d, data["footer"], f_footer, W - 2 * PAD - 180),
           font=f_footer, fill=MUTED)
    d.ellipse((W - PAD - 132, height - 47, W - PAD - 120, height - 35), fill=ACCENT)
    d.text((W - PAD - 110, height - 54), "VERIFIED LIVE", font=f_footer, fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf


def photo(text, title: str | None = None, badge: str | None = None,
          footer: str | None = None):
    """BufferedInputFile siap dikirim lewat Bot API."""
    from aiogram.types import BufferedInputFile

    raw = render(text, title, badge, footer)
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
    )
