"""Provider layanan SMM. Saat ini DEMO: status berjalan otomatis berdasarkan waktu.

Untuk provider asli (API panel SMM): implementasikan place_order() dan status() dengan HTTP request
ke API provider, lalu ganti `provider` di bawah.
"""
import random
from datetime import datetime

from db import WIB


class DemoProvider:
    name = "demo"

    async def place_order(self, service, link: str, qty: int) -> str:
        return f"DEMO{random.randint(100000, 999999)}"

    async def status(self, order) -> str:
        created = datetime.strptime(order["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=WIB)
        sec = (datetime.now(WIB) - created).total_seconds()
        if sec < 20:
            return "Pending"
        if sec < 90:
            return "Processing"
        return "Completed"


provider = DemoProvider()
