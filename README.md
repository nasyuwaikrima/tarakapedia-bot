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
- ✅ **Batas order mengikuti saldo provider**: semua layanan dicek modalnya sebelum diproses (cache 5 menit). Kalau kuota penuh, user hanya dapat pesan generik — angka saldo, modal, ID provider/refill, dan aturan batasnya tetap **khusus admin**.
- ✅ **Status order otomatis** `/status` tiap 20 detik + notifikasi ke user saat selesai.
- ✅ **Refill** `/refill` dan `/refill_status` bisa diajukan admin maupun user (untuk layanan bergaransi).
- ✅ **Harga dikelola admin**: margin global, harga manual per layanan, kunci harga, dan batas bawah harga agar tidak pernah rugi.
- ✅ **Modal provider disembunyikan** dari semua tampilan user. User hanya melihat harga jual.
- ✅ Menu utama dikirim sebagai **foto + caption** yang rapi; tombol disusun campuran **baris 2 tombol dan 1 tombol** agar rapi dan tidak melebihi lebar bubble. Fitur lanjutan masuk ke tombol **🧩 Lainnya**. Foto bisa diganti admin lewat panel. Tombol back/menu/invoice **mengedit pesan yang sama**, jadi tidak spam chat.
- ✅ **Bot Commands Menu** (tombol di pojok kiri bawah Telegram) diisi lewat `set_my_commands`: `/start`, `/layanan`, `/deposit`, `/pesanan`, `/riwayat`, `/profil`, `/referral`, `/toko`, `/misi`, `/top`. Ini bukan inline keyboard/reply keyboard. Admin mendapat tambahan `/admin` & `/users` lewat scope chat per ID. Saat `ADMIN_IDS` diubah, scope chat lama otomatis dihapus saat bot restart (state disimpan di `data/applied_admin_commands.json`), jadi command admin tidak tertinggal di akun yang sudah bukan admin.
- ✅ Katalog ratusan layanan **dikelompokkan per platform** dulu (Instagram, TikTok, YouTube, Facebook, Telegram, Twitter/X, WhatsApp, Shopee, Spotify, dll.). Menu `/layanan` menampilkan maksimal 8 platform per halaman, lalu sub-kategori, lalu layanan — tidak lagi menumpuk 100+ tombol. **Harga dan jumlah layanan ditulis jelas di tombol** (satu tombol per baris agar tidak terpotong di HP), bukan cuma di caption. Urutan tetap **termurah → termahal** memakai harga jual efektif (modal + margin tidak pernah bocor). Kategori yang tidak dikenali masuk **📁 Lainnya**. Posisi **WhatsApp** sengaja ditukar dengan **Twitch** sesuai preferensi katalog; urutan platform lain tetap mengikuti harga termurah.
- ✅ **Deskripsi layanan dari provider dimanfaatkan** sebagai spesifikasi di halaman detail: tag HTML dibersihkan, entitas didekode, duplikat dibuang, dan ditampilkan sebagai poin yang rapi. Seluruh teks bot menggunakan bahasa profesional (tanpa sapaan akrab seperti "kak"/"bang").
- ✅ **Top Transaksi** tampil di menu `/start` (3 teratas: username + total rupiah yang dibelanjakan) dan bisa dibuka sampai 10 teratas lewat satu tombol di home menu. Periode **Semua / Mingguan (7 hari) / Bulanan (30 hari)** dipilih lewat tab di dalam papan peringkat, supaya home menu tidak penuh.
- ✅ Deposit **QRIS PixPayz real**: invoice dibuat otomatis, QRIS bisa dilihat ulang kapan saja lewat riwayat, status lunas dicek otomatis ke PixPayz tiap 20 detik (**tanpa webhook/domain**), invoice **tidak bisa dibatalkan**.
- ✅ Batas **3 invoice aktif per user** (bisa diatur admin) — antrean deposit tetap terkendali.
- ✅ **Wajib gabung 2 channel**: `@tarakapedia` (register) & `@tarakapedia_log` (log). Berlaku juga untuk user lama; kalau keluar, bot menyuruh gabung lagi.
- ✅ **Status register tersimpan** di database & tampil di profil/panel admin; perubahan status ikut dilog ke channel.
- ✅ **Semua transaksi tampil di `@tarakapedia_log`**: deposit, order, refund, pembelian, misi, komisi referral, dan order selesai — biar calon user ikut tertarik.
- ✅ Toko produk + stok, referral, misi, broadcast, backup DB, statistik.
- ✅ **Referral aman**: komisi dibayar sekali saat order **selesai**, dihitung dari margin order (default 20%, dipatok maks 50%), bukan dari deposit, dan hanya berlaku **7 hari sejak teman daftar** — bot tetap untung, user tetap dapat hadiah.
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
| `channels.py` | Gate wajib join 2 channel, tombol gabung/cek ulang, dan pengingat saat user keluar channel. |
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
nano .env                      # isi token bot, ADMIN_IDS, channel, dan kredensial provider
./venv/bin/python main.py      # uji coba; tekan Ctrl+C setelah berhasil
```

Bot aktif ketika log menampilkan `Bot @username berjalan`.

**Sebelum dipakai user:** undang bot sebagai **admin** di `@tarakapedia` dan `@tarakapedia_log`. Tanpa itu, bot tidak bisa membaca status join dan tidak bisa mengirim log transaksi ke channel.

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

# Wajib join (bot sebaiknya jadi admin di kedua channel):
CHANNEL_REGISTRY=@tarakapedia
CHANNEL_LOG=@tarakapedia_log

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

- `ADMIN_IDS` dipisah koma (pakai ID Telegram lengkap, bukan potongan). Hanya ID ini yang bisa membuka `/admin` (admin dibebaskan dari gate channel). Setelah mengubahnya, jalankan `sudo systemctl restart tarakapedia-bot` agar scope command lama dibersihkan.
- `CHANNEL_REGISTRY` & `CHANNEL_LOG` = channel wajib. Tambahkan bot sebagai **admin** di keduanya supaya status keanggotaan terbaca dan log transaksi bisa dikirim.
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

Semua endpoint memakai **POST** dengan body berisi `api_id` + `api_key` (form-urlencoded). Endpoint `/profile` mengembalikan `username`, `full_name`, dan `balance`; hanya `balance` yang dipakai bot untuk batas order.

| Endpoint | Digunakan untuk | Dipanggil dari |
|---|---|---|
| `/services` | Ambil seluruh layanan (`service_fav` opsional) | Admin → Sync Layanan, startup & tiap 30 menit |
| `/profile` | Saldo provider = **modal admin** | Admin → Cek Modal + pengecekan batas order internal (cache 5 menit) |
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

- Default margin: **25% + Rp 0/1K** (database lama otomatis ikut sekali saat upgrade). Diubah di Panel Admin → Provider API → **Atur Margin**.
- Saat sinkron katalog, harga jual **hanya naik**, tidak pernah turun otomatis — jadi kenaikan harga provider tidak mengurangi pendapatan dan tidak ditampilkan ke user.
- Jika admin mengubah harga manual ke nilai di bawah batas aman, sistem otomatis memakai batas aman saat tagihan (`db.effective_price()`).
- Per layanan bisa dikunci (`Auto Harga = OFF`) agar tidak ikut penyesuaian otomatis; batas aman tetap berlaku.
- Detail layanan di admin menampilkan modal provider; tampilan user **hanya** menampilkan harga jual, min/max, garansi, dan deskripsi.
- Semua info provider — saldo, modal, ID provider, ID refill, dan batas order — tidak muncul di chat/riwayat user maupun channel log publik. Admin tetap melihatnya lewat Panel Admin dan notifikasi admin. Kalau saldo provider gagal dibaca, pengecekan batas memakai data cache terakhir; provider tetap menjadi penolakan terakhir.

Alur order aman:
1. User pilih layanan → isi target/jumlah/field tambahan → lihat harga → konfirmasi.
2. Saldo di-debit, order dicatat dengan id provider & data tambahan.
3. Bot mengirim order ke `/order`.
4. Jika gagal → `cancel_order()` → saldo otomatis dikembalikan.

---

## 8. Panduan admin

Ketik `/admin` atau tekan tombol **🛠 Panel Admin** di menu utama. Untuk melihat semua user langsung, ketik `/users` atau pilih **📋 Daftar User** di panel.

| Menu | Fungsi |
|---|---|
| 📊 Statistik | User, order, omzet, deposit, uptime. |
| 👥 Kelola User | Cari ID/@username, buka **📋 Daftar User** berhalaman + pencarian, tambah/kurang saldo, ban/unban. |
| 🛒 Layanan | Lihat & ubah harga, on/off, kunci/buka auto harga, hapus, tambah manual (boleh dengan ID provider). |
| 📱 Produk App | Produk digital + stok. |
| 📦 Pesanan | Detail order, ubah status, refund, lihat ID provider & refill. |
| 💳 Deposit | Lihat invoice QRIS pending; konfirmasi manual hanya jika pengecekan otomatis delay. Tidak ada tombol batal/tolak. |
| 🎯 Misi | Tambah/on-off/hapus misi. |
| ⚙️ Pengaturan | Maintenance, komisi referral, masa komisi (hari), bonus daftar, min deposit, batas invoice aktif, pengumuman. |
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

- `/start` → daftar/wajib gabung 2 channel → menu utama (foto + caption).
- `/menu` → tampilkan menu lagi (tetap dicek dulu status channel-nya).
- `/layanan`, `/deposit`, `/pesanan`, `/riwayat`, `/profil`, `/referral`, `/toko`, `/misi`, `/top` → pintasan langsung ke halaman masing-masing (tetap lewat gate 2 channel).
- Kalau keluar dari salah satu channel, bot langsung mengingatkan; tekan tombol channel lalu **✅ Saya sudah gabung** untuk masuk lagi.
- 💰 **Deposit Saldo** → invoice aktif langsung tampil dengan QRIS-nya; pilih nominal / nominal custom untuk membuat invoice baru (maks 3 aktif).
- 🧾 **Riwayat Deposit** → lihat semua transaksi; ketuk salah satu untuk menampilkan QRIS/invoice lama lagi dan cek status.
- 🛒 **Order Termurah** → kategori & layanan diurutkan termurah dulu → target → jumlah (jika perlu) → field tambahan (jika perlu) → konfirmasi.
- 📦 **Pesanan Saya** → status order & refill (ID provider tetap tersimpan internal, tidak ditampilkan).
- 🏆 **Top Transaksi** → papan peringkat 3 teratas (periode Semua) tampil langsung di menu `/start`; tombol **🏆 Top Transaksi** membuka papan 10 teratas beserta username dan total rupiah transaksi. Di dalam papan ada tab **Semua / Mingguan / Bulanan** — jadi tidak perlu menambah tombol periode di home menu. Urutan memakai total belanja (`total_spent`), bukan jumlah order. Periode mingguan/bulanan dihitung dari tanggal order, tidak termasuk order dibatalkan.
- 🧩 **Lainnya** → toko aplikasi, profil, kode referral, misi, website, hubungi admin, dan panel admin (khusus admin). **📢 Channel Kami** & **📜 Log Transaksi** tetap langsung tersedia di menu utama.

Perintah penting: `/start`, `/menu`, `/layanan`, `/deposit`, `/pesanan`, `/riwayat`, `/profil`, `/referral`, `/toko`, `/misi`, `/top`; admin: `/admin`, `/users`. User biasa tidak melihat tombol/command admin; kalau mengetik `/admin` atau `/users`, bot menjawab bahwa perintah itu khusus admin.

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

### Channel register & log transaksi
- `@tarakapedia` = **channel register**. User wajib gabung sebelum bisa deposit/order — termasuk user yang sudah terdaftar sebelum fitur ini aktif. Kalau keluar, bot meminta gabung lagi lewat tombol khusus.
- Status register (`joined` / `out` / `pending`) disimpan di tabel `users`, ditampilkan di **👤 Profil Saya** dan kartu user admin, serta dilog ke channel saat berubah.
- `@tarakapedia_log` = **channel log**. Semua transaksi tampil di sini: invoice baru, deposit lunas, order baru/selesai, refund, pembelian app, klaim misi, komisi referral, dan penyesuaian saldo admin.
- Mention user di log bisa diklik, jadi user lain gampang lihat aktivitas. Pengiriman log dibuat **best-effort**: kalau channel log error, transaksi user tetap berhasil.
- Kalau status keanggotaan gagal dibaca, bot memakai status `joined` terakhir (maks 24 jam). Kalau tidak ada, user tetap diminta gabung — jangan lupa jadikan bot admin di kedua channel.

### Lainnya
- **Produk app**: admin menambah produk & stok; pembelian otomatis mengirim data stok ke user.
- **Referral**: link `t.me/<bot>?start=ref_<id>`. Bonus daftar default **Rp 0** (nonaktif; bisa diatur admin). Komisi dibayar **setelah order downline statusnya Selesai** (lewat worker provider atau admin), besarnya `margin order × ref_percent` dengan `ref_percent` default **20%** dan dipatok maksimal **50% margin** supaya bot tidak rugi. **Masa komisi default 7 hari** sejak teman mendaftar lewat link (`ref_days`, 0 = tanpa batas); yang dihitung adalah **tanggal order dibuat**, jadi order dalam masa berlaku tetap dapat komisi walau selesai setelahnya. Data lama yang belum punya `referred_at` memakai tanggal join sebagai awal masa komisi. Deposit tidak memberi komisi; kalau order dibatalkan/di-refund, komisi yang sudah dibayar ikut ditarik. Modal provider disimpan di order saat dibuat dan tidak pernah ditampilkan ke user.
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
| User disuruh gabung terus padahal sudah join | Bot belum jadi admin di channel. Tambahkan bot sebagai admin di `@tarakapedia` & `@tarakapedia_log`, lalu restart. |
| Log transaksi tidak muncul | Bot belum admin di `@tarakapedia_log` atau channel salah. Cek `CHANNEL_LOG` di `.env` dan `journalctl -u tarakapedia-bot -f`. |
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
