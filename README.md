# Tarakapedia SMM Bot (Telegram)

Bot SMM panel: order layanan, toko aplikasi, deposit, referral, misi, statistik, dan panel admin lengkap.
Mode **DEMO**: payment (konfirmasi lewat tombol) dan provider (status order otomatis) masih simulasi.

## Install di VPS (Ubuntu/Debian)
```bash
sudo apt update && sudo apt install -y python3 python3-venv unzip
sudo mkdir -p /opt/tarakapedia-bot && sudo chown $USER /opt/tarakapedia-bot
# upload & ekstrak zip ke /opt/tarakapedia-bot
cd /opt/tarakapedia-bot
python3 -m venv venv && ./venv/bin/pip install -r requirements.txt
cp .env.example .env && nano .env      # isi BOT_TOKEN, ADMIN_IDS, link website & admin
./venv/bin/python main.py              # tes dulu
```

## Jalankan 24/7 (systemd)
```bash
sudo cp tarakapedia-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tarakapedia-bot
sudo journalctl -u tarakapedia-bot -f   # lihat log
```

## Pemakaian
- User: `/start` → menu. Admin: `/admin` (atau tombol 🛠 Panel Admin di menu).
- Admin bisa: statistik, kelola user (saldo/ban), layanan, produk + stok, pesanan (ubah status/refund),
  deposit pending, misi, pengaturan (maintenance, komisi referral, min deposit, pengumuman), broadcast, backup DB.
- Database: SQLite di `data/tarakapedia.db` (backup lewat panel admin atau salin file).

## Menuju produksi
- `payments.py` → ganti `DemoGateway` dengan gateway asli (QRIS/VA); panggil `db.confirm_deposit(id)` saat lunas.
- `providers.py` → ganti `DemoProvider` dengan API provider panel SMM asli.
- Layanan/produk demo bisa dihapus lewat Panel Admin.
