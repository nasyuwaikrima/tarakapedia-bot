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

# Foto menu: bawaan repo, bisa ditimpa lewat panel admin (diunggah ke data/menu_photo.jpg).
MENU_PHOTO = Path(os.getenv("MENU_PHOTO", str(BASE_DIR / "assets" / "menu.png")))
CUSTOM_MENU_PHOTO = Path(os.getenv("CUSTOM_MENU_PHOTO", "data/menu_photo.jpg"))
