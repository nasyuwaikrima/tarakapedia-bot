import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x.isdigit()}
BOT_NAME = os.getenv("BOT_NAME", "Tarakapedia")
DB_PATH = os.getenv("DB_PATH", "data/tarakapedia.db")
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://tarakapedia.com")
ADMIN_CONTACT_URL = os.getenv("ADMIN_CONTACT_URL", "https://t.me/telegram")
