import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
BOT_NAME = os.getenv("BOT_NAME", "Tarakapedia")
DB_PATH = os.getenv("DB_PATH", "data/tarakapedia.db")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://tarakapedia.com")
ADMIN_CONTACT_URL = os.getenv("ADMIN_CONTACT_URL", "https://t.me/telegram")

# Kredensial provider SMM (MedanPedia). Isi di .env — jangan pernah hardcode di kode.
MEDANPEDIA_API_ID = os.getenv("MEDANPEDIA_API_ID", "").strip()
MEDANPEDIA_API_KEY = os.getenv("MEDANPEDIA_API_KEY", "").strip()
MEDANPEDIA_BASE_URL = os.getenv("MEDANPEDIA_BASE_URL", "https://api.medanpedia.co.id").rstrip("/")
MEDANPEDIA_TIMEOUT = int(os.getenv("MEDANPEDIA_TIMEOUT", "20") or 20)

# Pembayaran QRIS PixPayz. API key hanya ada di .env.
PIXPAYZ_API_KEY = os.getenv("PIXPAYZ_API_KEY", "").strip()
PIXPAYZ_BASE_URL = os.getenv("PIXPAYZ_BASE_URL", "https://pixpayz.com").rstrip("/")
PIXPAYZ_TIMEOUT = int(os.getenv("PIXPAYZ_TIMEOUT", "20") or 20)
PIXPAYZ_MIN_INTERVAL = float(os.getenv("PIXPAYZ_MIN_INTERVAL", "0.6") or 0.6)  # batas 2 req/detik
PIXPAYZ_WEBHOOK_PORT = int(os.getenv("PIXPAYZ_WEBHOOK_PORT", "8080") or 8080)
PIXPAYZ_WEBHOOK_PATH = os.getenv("PIXPAYZ_WEBHOOK_PATH", "/webhook/pixpayz")
PIXPAYZ_POLL_SECONDS = int(os.getenv("PIXPAYZ_POLL_SECONDS", "20") or 20)
MAX_ACTIVE_DEPOSITS = int(os.getenv("MAX_ACTIVE_DEPOSITS", "3") or 3)

# Foto menu: bawaan repo, bisa ditimpa lewat panel admin (diunggah ke data/menu_photo.jpg).
MENU_PHOTO = Path(os.getenv("MENU_PHOTO", str(BASE_DIR / "assets" / "menu.png")))
CUSTOM_MENU_PHOTO = Path(os.getenv("CUSTOM_MENU_PHOTO", "data/menu_photo.jpg"))
