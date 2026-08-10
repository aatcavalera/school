# Portal Analitik Absensi Siswa

Dashboard monitoring absensi siswa, disinkronkan otomatis dari School ID (skul.id), dengan dukungan multi-sekolah.

## Arsitektur

- **backend/** — FastAPI + SQLAlchemy (async) + PostgreSQL. Autentikasi JWT, sinkronisasi terjadwal ke School ID, agregasi dashboard, dan panel admin.
- **frontend/** — Next.js (App Router) + Tailwind CSS + Recharts. Login, dashboard, analytics, operations, dan settings.
- **PostgreSQL** — database khusus (`school_absensi`), terpisah dari database aplikasi lain meski bisa berbagi instance Postgres yang sama.
- **docker-compose.yml** — menjalankan 4 service: `backend` (API), `sync-worker` & `sync-scheduler` (job sinkronisasi background ke School ID), dan `frontend`.

## Menjalankan

1. Salin `.env.example` ke `.env` dan isi nilainya:
   ```bash
   cp .env.example .env
   ```
   Wajib diisi dengan nilai asli (jangan commit `.env`):
   - `POSTGRES_PASSWORD`, `JWT_SECRET`, `CREDENTIAL_ENCRYPTION_KEY` — generate string acak yang kuat.
   - `USERNAME_SCHOOL_ID` / `PASSWORD_SCHOOL_ID` — kredensial login akun School ID sekolah pertama (dienkripsi saat disimpan ke DB, bukan disimpan mentah).
   - `SCHOOL_2_*` — opsional, untuk sekolah kedua.

2. Build & jalankan:
   ```bash
   docker compose up -d --build
   ```

3. Buat user admin pertama:
   ```bash
   docker compose exec backend python -m app.seed_admin
   ```
   Username/password akan dicetak sekali di output — segera catat dan simpan.

4. Migrasi database (Alembic) dijalankan otomatis; untuk migrasi manual:
   ```bash
   docker compose exec backend alembic upgrade head
   ```

Frontend berjalan di `127.0.0.1:3010` secara default (lihat `docker-compose.yml` untuk port mapping), dan biasanya diletakkan di belakang reverse proxy (nginx + TLS) untuk akses publik.

## Struktur backend

| Router | Fungsi |
|---|---|
| `auth` | Login, ganti password, sesi JWT |
| `dashboard` / `dashboard_synced` | Agregasi data untuk halaman dashboard |
| `analytics` | Endpoint analitik lanjutan |
| `operations` | Endpoint operasional (mis. monitoring proses sync) |
| `import_data` | Import manual (legacy, nonaktif secara default — lihat `ALLOW_LEGACY_IMPORT`) |
| `settings_router` | Parameter jam sekolah, pengaturan aplikasi |
| `sync_admin` | Kelola koneksi & riwayat sinkronisasi School ID per sekolah |
| `admin_users` | Manajemen user admin |

Sinkronisasi data berjalan otomatis lewat `sync-worker` + `sync-scheduler` (lihat `app/sync_service.py`, `app/job_queue.py`, `app/integrations/school_id/`), terjadwal sesuai `ATTENDANCE_SYNC_START_LOCAL` / `ATTENDANCE_SYNC_END_LOCAL` / `ATTENDANCE_SYNC_WEEKDAYS`. Kredensial login School ID disimpan terenkripsi (`credential_cipher.py`) menggunakan `CREDENTIAL_ENCRYPTION_KEY`.

## Testing

```bash
docker compose exec backend pytest
```

## Catatan keamanan

- `.env` berisi rahasia (password DB, JWT secret, kredensial School ID) — **jangan pernah di-commit**. Sudah masuk `.gitignore`.
- Ganti password admin default segera setelah setup awal lewat halaman Settings.
