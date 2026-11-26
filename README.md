# Tarakapedia SMM Bot — Telegram

Bot SMM panel berbasis Telegram dengan **order real ke API MedanPedia**, katalog layanan tersimpan di database, harga dikelola sepenuhnya oleh admin, dan menu berupa **foto + caption** yang rapi.

> **Development by nasyuwaikrima**

---

## Daftar isi
1. [Fitur utama](#1-fitur-utama)
2. [Struktur file](#2-struktur-file)
3. [Instalasi dari awal (VPS Ubuntu/Debian)](#3-instalasi-dari-awal-vps-ubuntudebian)
4. [Konfigurasi `.env`](#4-konfigurasi-env)
5. [Menjalankan bot](#5-menjalankan-bot)
6. [API MedanPedia yang dipakai](#6-api-medanpedia-yang-dipakai)
7. [Strategi harga & perlindungan rugi](#7-strategi-harga--perlindungan-rugi)
8. [Panduan admin](#8-panduan-admin)
9. [Panduan user](#9-panduan-user)
10. [Tipe layanan & field yang dikirim](#10-tipe-layanan--field-yang-dikirim)
11. [Deposit, produk, referral, misi](#11-deposit-produk-referral-misi)
12. [Backup & restore database](#12-backup--restore-database)
13. [Troubleshooting](#13-troubleshooting)
14. [Catatan pengembangan](#14-catatan-pengembangan)

---

## 1. Fitur utama

- ✅ **Order real** ke `https://api.medanpedia.co.id/order` (bukan simulasi).
- ✅ Mendukung semua tipe order: default, package, custom comment, mention list, mention hashtag, mention follower, mention media likers, dan tipe lain yang sejenis.
- ✅ **Sinkron katalog** `/services` → semua layanan disimpan ke SQLite (id provider, tipe, kategori, min/max, garansi refill, estimasi waktu).
- ✅ **Cek saldo provider** `/profile` khusus admin — dipakai sebagai informasi **modal**, tidak pernah ditampilkan ke user.
- ✅ **Status order otomatis** `/status` tiap 20 detik + notifikasi ke user saat selesai.
- ✅ **Refill** `/refill` dan `/refill_status` bisa diajukan admin maupun user (untuk layanan bergaransi).
- ✅ **Harga dikelola admin**: margin global, harga manual per layanan, kunci harga, dan batas bawah harga agar tidak pernah rugi.
- ✅ **Modal provider disembunyikan** dari semua tampilan user. User hanya melihat harga jual.
- ✅ Menu utama dikirim sebagai **foto + caption** yang rapi; foto bisa diganti admin lewat panel.
- ✅ Kategori & layanan diurutkan **termurah → termahal** memakai harga jual efektif (modal + margin tidak pernah bocor).
- ✅ Deposit **QRIS PixPayz real**: invoice dibuat otomatis, QRIS bisa dilihat ulang kapan saja lewat riwayat, status lunas dicek otomatis ke PixPayz tiap 20 detik (**tanpa webhook/domain**), invoice **tidak bisa dibatalkan**.
- ✅ Batas **3 invoice aktif per user** (bisa diatur admin) — antrean deposit tetap terkendali.
- ✅ Toko produk + stok, referral, misi, broadcast, backup DB, statistik.
- ✅ Migrasi database otomatis: database lama tetap aman saat di-upgrade.
- ✅ Kode terpisah per lapisan (config, db, providers, ui, handlers) agar mudah dirawat.

---

## 2. Struktur file

| File | Fungsi |
|---|---|
| `config.py` | Semua konfigurasi dari `.env` (token bot, kredensial provider, path foto). |
| `db.py` | Skema SQLite, migrasi, harga, sinkronisasi layanan, transaksi & statistik. |
| `providers.py` | Client HTTP API MedanPedia: `services`, `profile`, `order`, `status`, `refill`, `refill_status`. |
| `ui.py` | Keyboard, format Rupiah, teks menu, pengiriman **foto + caption**. |
| `handlers/user.py` | Alur user: deposit, order bertipe, pesanan, refill, toko, referral, misi. |
| `handlers/admin.py` | Panel admin: provider API, margin, layanan, user, order, deposit, foto menu, dll. |
| `main.py` | Entry point, middleware keamanan, worker sinkronisasi status order, invoice QRIS & katalog. |
| `payments.py` | Gateway QRIS PixPayz: profil, buat invoice, cek invoice, rate limiter 2 req/detik. |
| `assets/menu.png` | Foto menu bawaan (bisa diganti dari panel admin). |
| `data/tarakapedia.db` | Database SQLite (tidak ikut di-commit). |
| `tarakapedia-bot.service` | Unit systemd untuk jalan 24/7. |

---

## 3. Instalasi dari awal (VPS Ubuntu/Debian)

```bash
sudo apt update && sudo apt install -y python3 python3-venv git
sudo mkdir -p /opt/tarakapedia-bot && sudo chown $USER /opt/tarakapedia-bot

# Upload/ekstrak project ke /opt/tarakapedia-bot, lalu:
cd /opt/tarakapedia-bot
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

cp .env.example .env
nano .env                      # isi token bot, ADMIN_IDS, dan kredensial provider
./venv/bin/python main.py      # uji coba; tekan Ctrl+C setelah berhasil
```

Bot aktif ketika log menampilkan `Bot @username berjalan`.

### Upgrade dari versi lama
```bash
cd /opt/tarakapedia-bot
git pull
./venv/bin/pip install -r requirements.txt
sudo systemctl restart tarakapedia-bot
sudo journalctl -u tarakapedia-bot -f
```
Kolom baru ditambahkan otomatis (`db._migrate()`); data user, saldo, dan order lama tetap ada.

---

## 4. Konfigurasi `.env`

```env
BOT_TOKEN=123456:TOKEN_DARI_BOTFATHER
ADMIN_IDS=123456789,987654321
BOT_NAME=Tarakapedia
WEBSITE_URL=https://tarakapedia.com
ADMIN_CONTACT_URL=https://t.me/username_admin
DB_PATH=data/tarakapedia.db

# Wajib untuk order real:
MEDANPEDIA_API_ID=11
MEDANPEDIA_API_KEY=api_key_asli_dari_panel_medanpedia
MEDANPEDIA_BASE_URL=https://api.medanpedia.co.id
MEDANPEDIA_TIMEOUT=20

# Wajib untuk deposit QRIS:
PIXPAYZ_API_KEY=ISI_API_KEY_DARI_DASHBOARD_PIXPAYZ
PIXPAYZ_BASE_URL=https://pixpayz.com
PIXPAYZ_TIMEOUT=20
PIXPAYZ_MIN_INTERVAL=0.6
PIXPAYZ_POLL_SECONDS=20
MAX_ACTIVE_DEPOSITS=3
```

- `ADMIN_IDS` dipisah koma. Hanya ID ini yang bisa membuka `/admin`.
- `MEDANPEDIA_API_ID` dan `MEDANPEDIA_API_KEY` **wajib** diisi; jika kosong, order ditolak dan saldo user dikembalikan otomatis (tidak ada order demo).
- `PIXPAYZ_API_KEY` **wajib** diisi untuk deposit QRIS; API key hanya dibaca dari `.env`, tidak pernah ditaruh di kode.
- `PIXPAYZ_MIN_INTERVAL=0.6` menjaga request tidak melewati batas **2 request/detik** PixPayz. Jangan dikurangi.
- `MAX_ACTIVE_DEPOSITS=3` = batas invoice aktif per user. Bisa diubah juga dari **⚙️ Pengaturan → Batas invoice aktif per user**.
- Jangan pernah commit `.env` — sudah masuk `.gitignore`.
- Opsi foto menu: `MENU_PHOTO=assets/menu.png`, `CUSTOM_MENU_PHOTO=data/menu_photo.jpg`.

---

## 5. Menjalankan bot

### Manual
```bash
cd /opt/tarakapedia-bot && ./venv/bin/python main.py
```

### 24/7 dengan systemd
```bash
sudo cp tarakapedia-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tarakapedia-bot
sudo systemctl status tarakapedia-bot
sudo journalctl -u tarakapedia-bot -f
```
Sesuaikan `WorkingDirectory`, `ExecStart`, dan `User` di file service jika path berbeda.

---

## 6. API MedanPedia yang dipakai

Semua endpoint memakai **POST** dengan body JSON dan kredensial `api_id` + `api_key`.

| Endpoint | Digunakan untuk | Dipanggil dari |
|---|---|---|
| `/services` | Ambil seluruh layanan (`service_fav` opsional) | Admin → Sync Layanan, startup & tiap 30 menit |
| `/profile` | Saldo provider = **modal admin** | Admin → Cek Modal |
| `/order` | Pasang pesanan sesuai tipe layanan | Alur order user |
| `/status` | Cek status pesanan aktif | Worker tiap 20 detik |
| `/refill` | Ajukan refill | User & admin |
| `/refill_status` | Cek hasil refill | Worker & admin |

Contoh body order default:
```json
{"api_id": 11, "api_key": "...", "service": 9, "target": "sebastianwirajaya11", "quantity": 100}
```
Contoh body custom comment:
```json
{"api_id": 11, "api_key": "...", "service": 9, "target": "https://www.instagram.com/p/xxx/", "comments": "komentar pertama\nkomentar kedua"}
```
Response sukses provider dibaca fleksibel (`data.order`, `data.id_order`, angka langsung, dll). Jika provider gagal, bot **membatalkan order dan mengembalikan saldo** user.

---

## 7. Strategi harga & perlindungan rugi

Prinsip: **modal provider adalah rahasia admin**, harga jual ditentukan admin.

```
harga jual minimum = ceil(modal provider × (100% + margin%) ) + margin flat per 1K
```

- Default margin: **35% + Rp 0/1K**. Diubah di Panel Admin → Provider API → **Atur Margin**.
- Saat sinkron katalog, harga jual **hanya naik**, tidak pernah turun otomatis — jadi kenaikan harga provider tidak mengurangi pendapatan dan tidak ditampilkan ke user.
- Jika admin mengubah harga manual ke nilai di bawah batas aman, sistem otomatis memakai batas aman saat tagihan (`db.effective_price()`).
- Per layanan bisa dikunci (`Auto Harga = OFF`) agar tidak ikut penyesuaian otomatis; batas aman tetap berlaku.
- Detail layanan di admin menampilkan modal provider; tampilan user **hanya** menampilkan harga jual, min/max, garansi, dan deskripsi.

Alur order aman:
1. User pilih layanan → isi target/jumlah/field tambahan → lihat harga → konfirmasi.
2. Saldo di-debit, order dicatat dengan id provider & data tambahan.
3. Bot mengirim order ke `/order`.
4. Jika gagal → `cancel_order()` → saldo otomatis dikembalikan.

---

## 8. Panduan admin

Ketik `/admin` atau tekan tombol **🛠 Panel Admin** di menu utama.

| Menu | Fungsi |
|---|---|
| 📊 Statistik | User, order, omzet, deposit, uptime. |
| 👥 Kelola User | Cari ID/@username, tambah/kurang saldo, ban/unban. |
| 🛒 Layanan | Lihat & ubah harga, on/off, kunci/buka auto harga, hapus, tambah manual (boleh dengan ID provider). |
| 📱 Produk App | Produk digital + stok. |
| 📦 Pesanan | Detail order, ubah status, refund, lihat ID provider & refill. |
| 💳 Deposit | Lihat invoice QRIS pending; konfirmasi manual hanya jika pengecekan otomatis delay. Tidak ada tombol batal/tolak. |
| 🎯 Misi | Tambah/on-off/hapus misi. |
| ⚙️ Pengaturan | Maintenance, komisi referral, bonus daftar, min deposit, batas invoice aktif, pengumuman. |
| 🌐 Provider API | Sync layanan, cek modal, atur margin, filter favorit, auto sync, refill & cek refill. |
| 📸 Foto Menu | Upload foto menu baru atau kembalikan ke foto bawaan. |
| 📢 Broadcast | Kirim pesan ke semua user. |
| 💾 Backup DB | Kirim file database ke chat admin. |

### Menambah layanan manual dengan ID provider
Format satu baris:
```
Kategori | Nama | Harga per 1K | Min | Max | Deskripsi | ID Provider | Tipe
```
Contoh:
```
Instagram | IG Followers Premium | 74200 | 100 | 100000 | Garansi 30 hari | 9 | default
```
ID Provider dan tipe boleh kosong. Layanan dengan ID provider ikut dipakai untuk order real.

### Refill
- User: **📦 Pesanan Saya** → tombol **🔁 Refill** pada order bergaransi; tekan lagi untuk **📊 Cek Refill**.
- Admin: **🌐 Provider API → 🔁 Refill Order / 📊 Cek Refill**, masukkan ID order bot.

---

## 9. Panduan user

- `/start` → menu utama (foto + caption).
- `/menu` → tampilkan menu lagi.
- 💰 **Deposit Saldo** → invoice aktif langsung tampil dengan QRIS-nya; pilih nominal / nominal custom untuk membuat invoice baru (maks 3 aktif).
- 🧾 **Riwayat Deposit** → lihat semua transaksi; ketuk salah satu untuk menampilkan QRIS/invoice lama lagi dan cek status.
- 🛒 **Order Termurah** → kategori & layanan diurutkan termurah dulu → target → jumlah (jika perlu) → field tambahan (jika perlu) → konfirmasi.
- 📦 **Pesanan Saya** → status order, ID provider, refill.
- Lainnya: toko aplikasi, riwayat, profil, kode referral, misi, website, hubungi admin.

Perintah penting: `/start`, `/menu`, `/admin` (khusus admin).

---

## 10. Tipe layanan & field yang dikirim

| Tipe provider | Field dari user | Body tambahan ke `/order` |
|---|---|---|
| `default` | target, quantity | `quantity` |
| `package` | target | — |
| `custom_comment` | target, comments | `comments` (dipisah newline) |
| `comment_likes` | target, quantity | `quantity` |
| `mention_list` | target, usernames | `usernames` (dipisah newline) |
| `mention_hashtag` / `mention_hastag` | target, quantity, hashtag | `quantity`, `hashtag` |
| `mention_follower` | target, quantity, username | `quantity`, `username` |
| `mention_media` | target, quantity, media | `quantity`, `media` |
| `poll`, `comment_reply`, `comment_live` | target, quantity (+ comments bila ada) | `quantity` / `comments` |

Alias seperti `custom_comments`, `mention_hastag`, dan `mentions_custom_list` dinormalisasi otomatis dari response `/services`.

---

## 11. Deposit QRIS, produk, referral, misi

### Alur deposit QRIS
1. User pilih nominal (atau nominal custom) → bot memanggil `/api/createinvoice` PixPayz.
2. Bot menyimpan `invoice_id`, `qris_image`, `payment_link`, dan `expired_at` ke database, lalu **langsung menampilkan QRIS** beserta tombol halaman bayar.
3. Invoice **tidak bisa dibatalkan** — tidak ada tombol batal. Invoice yang belum dibayar otomatis tampil lagi di menu **💰 Deposit Saldo**, dan semua transaksi bisa dilihat di **📄 Riwayat Deposit** (ketuk untuk menampilkan QRIS lama + cek status).
4. Bot mengecek `/api/checkinvoice` ke PixPayz tiap 20 detik (maks 20 invoice per siklus, bergilir agar tidak ada yang terlewat). Begitu `paid`, saldo user langsung ditambah. User juga bisa menekan **🔄 Cek Status** kapan saja.
5. Saat status `expired`, invoice ditandai kedaluwarsa dan slot aktif user terbebas. Konfirmasi bersifat **idempoten**: pengecekan otomatis, cek manual, dan tombol konfirmasi admin tidak bisa menambah saldo dua kali.
6. **Batas 3 invoice aktif per user** (default). Setelah tercapai, pilihan nominal hilang sampai ada invoice yang lunas/kedaluwarsa — mencegah antrean deposit menumpuk.

### Endpoint PixPayz yang dipakai
Semua endpoint **GET** dengan query `apikey`:

| Endpoint | Fungsi | Dipanggil dari |
|---|---|---|
| `/api/profile` | Cek profil & saldo merchant | Diagnosa gateway |
| `/api/createinvoice` | Buat invoice QRIS (`amount`) | Tombol nominal deposit |
| `/api/checkinvoice` | Cek status invoice (`id`) | Tombol 🔄 Cek Status, polling 20 detik |

### Tanpa webhook, tanpa domain
Bot **tidak menyediakan server webhook**. Seluruh konfirmasi deposit berasal dari pengecekan langsung ke `/api/checkinvoice`, jadi tidak perlu domain, nginx, SSL, atau pendaftaran webhook di dashboard PixPayz.

- **Rate limit PixPayz: 2 request/detik.** Semua request (buat/cek invoice) lewat satu rate limiter global dengan jeda 0.6 detik dan retry saat HTTP 429. Jangan menurunkan `PIXPAYZ_MIN_INTERVAL`.
- Deteksi pembayaran maksimal ~20 detik setelah status `paid` di PixPayz (atau langsung saat tombol 🔄 Cek Status ditekan).

### Lainnya
- **Produk app**: admin menambah produk & stok; pembelian otomatis mengirim data stok ke user.
- **Referral**: bonus daftar + komisi deposit; link `t.me/<bot>?start=ref_<id>`.
- **Misi**: harian, jumlah order, total deposit, jumlah referral — diklaim lewat tombol.

---

## 12. Backup & restore database

- Backup: Panel Admin → **💾 Backup DB** (file dikirim ke chat admin).
- Manual:
```bash
cd /opt/tarakapedia-bot
sqlite3 data/tarakapedia.db ".backup data/backup-$(date +%F).db"
```
- Restore: matikan bot, ganti `data/tarakapedia.db`, lalu nyalakan lagi. Migrasi akan tetap dijalankan otomatis.

---

## 13. Troubleshooting

| Gejala | Penyebab & solusi |
|---|---|
| `Kredensial MedanPedia belum diisi` | Isi `MEDANPEDIA_API_ID` & `MEDANPEDIA_API_KEY` di `.env`, restart bot. |
| `Belum ada layanan tersedia` | Buka `/admin → 🌐 Provider API → 🔄 Sync Layanan`. |
| Order gagal, saldo kembali | Provider error / field belum lengkap. Lihat pesan error di chat; cek log `journalctl -u tarakapedia-bot -f`. |
| Harga user berubah sendiri | Itu penyesuaian margin saat kenaikan modal provider (tidak pernah turun). Kunci lewat tombol **🤖 Auto Harga** di detail layanan. |
| Foto menu tidak muncul | Pastikan `assets/menu.png` ada, atau upload ulang lewat **📸 Foto Menu**. Bot otomatis fallback ke teks. |
| Status order tidak berubah | Cek koneksi ke `/status`, pastikan `provider_order_id` tersimpan di order. |
| `API key PixPayz belum diisi` | Isi `PIXPAYZ_API_KEY` di `.env`, restart bot. |
| QRIS tidak muncul | Cek koneksi ke `/api/createinvoice`; pastikan `qris_image` tersimpan. Invoice lama bisa ditampilkan ulang lewat **📄 Riwayat Deposit**. |
| Deposit sudah bayar tapi saldo belum bertambah | Tekan **🔄 Cek Status** pada invoice, atau tunggu pengecekan otomatis tiap 20 detik. Cek log `journalctl -u tarakapedia-bot -f` jika tetap gagal. |
| `Terlalu banyak request (429)` | PixPayz membatasi 2 req/detik. Biarkan `PIXPAYZ_MIN_INTERVAL=0.6`; bot otomatis retry. |
| `Maksimal 3 invoice aktif` | Selesaikan atau tunggu invoice lama kedaluwarsa. Admin bisa mengubah batas di **⚙️ Pengaturan → Batas invoice aktif per user**. |

---

## 14. Catatan pengembangan

- Website masih dalam tahap pengembangan; tombol website di menu bersifat informasi.
- Semua konfigurasi sensitif hanya ada di `.env`.
- Kredensial provider & PixPayz, saldo/modal, dan harga modal tidak pernah dikirim ke handler atau tampilan user.
- Invoice QRIS sengaja tidak bisa dibatalkan: status akhir hanya `paid`, `expired`, atau konfirmasi manual admin.
- Penambahan endpoint baru cukup ditambahkan sebagai method di `providers.py` lalu dipanggil dari panel admin.
- Dibuat dengan arsitektur modular dan clean code agar mudah dikembangkan.

**Development by nasyuwaikrima**
