# CMS mobile Android dan notifikasi perangkat

## Memasang aplikasi

1. Buka `https://shanicantik.com/admin/` di Chrome Android dan masuk sebagai admin.
2. Buka **Settings → Aplikasi CMS di perangkat ini → Install ke Android**.
3. Konfirmasi dialog instalasi Android. Browser tidak mengizinkan instalasi tanpa persetujuan perangkat.
4. Buka CMS melalui ikon aplikasi. Manifest `standalone` menyembunyikan bilah URL; semua navigasi internal berada dalam cakupan `/admin/`.

Jika browser belum menawarkan dialog, tombol menjelaskan menu Chrome **Tambahkan ke layar utama → Instal**. Browser dalam aplikasi lain perlu dibuka di Chrome. Tautan **Lihat toko** keluar dari cakupan aplikasi CMS.

## Mengaktifkan notifikasi

Di setiap perangkat admin, buka Settings dan tekan **Aktifkan notifikasi**, lalu izinkan notifikasi Android/Chrome. Tekan **Kirim notifikasi tes** untuk memeriksa pengiriman. Instalasi saja tidak memberikan izin notifikasi.

Pesan Telegram Business masuk menjadi prioritas notifikasi. Notifikasi membuka percakapan terkait, termasuk ketika aplikasi sedang ditutup. Voice note, dokumen, dan media nonfoto ditampilkan sebagai penanda pesan untuk dilanjutkan di Telegram. Pending inquiry/order baru juga menghasilkan notifikasi. Pesan duplikat, edit pesan, dan pesan keluar tidak menghasilkan notifikasi chat baru.

Backend mencatat pengiriman untuk setiap perangkat dalam transaksi yang sama dengan chat/order. Pengiriman gagal sementara dicoba ulang; endpoint kedaluwarsa dinonaktifkan. Isi notifikasi layar kunci bersifat umum, tanpa nama atau teks customer. Menonaktifkan perangkat atau logout berhenti berlangganan perangkat tersebut. Akun yang tidak aktif, kehilangan role admin, atau memiliki token version lama tidak menerima pengiriman berikutnya.

Pengiriman memerlukan HTTPS, koneksi internet, Telegram webhook Business yang aktif, serta izin notifikasi browser/Android. Pembatasan baterai atau mematikan notifikasi Chrome/OS dapat menunda atau meniadakan notifikasi.

## Deployment dan kunci

`deploy/production/deploy.sh` membuat kunci VAPID EC P-256 sekali sebelum migration. Kunci privat disimpan di `/var/lib/marketplace/push-keys/vapid-private.pem`, mode `0600`, dan dipasang read-only pada backend. Kunci tidak masuk Git, frontend, atau GitHub secret. Release berikutnya menggunakan kunci yang sama.

- `ADMIN_PUSH_ENABLED=true` pada produksi, `false` secara default pada development/test.
- `VAPID_SUBJECT=https://shanicantik.com`, atau kontak `mailto:` yang valid.
- Backup direktori kunci secara terenkripsi bersama database/media. Jangan regenerasi pada deployment rutin; pergantian kunci memerlukan perangkat berlangganan ulang.
- Endpoint `/api/v1/admin/push/*` hanya untuk admin aktif. Mutasi memerlukan CSRF dan API membatasi endpoint ke penyedia Web Push yang dikenal.
- Service worker hanya menyimpan halaman offline umum. Halaman admin, API, media customer, dan data autentikasi tidak disimpan sebagai cache offline.

## Pengujian lokal terisolasi

Sesudah menjalankan Compose dan seed accounts/catalog/CMS:

```sh
docker compose exec -T backend python scripts/seed_mobile_audit.py
docker compose exec -T -e APP_ENV=test -e ADMIN_PUSH_ENABLED=false -e RATE_LIMIT_BACKEND=memory backend python -m unittest discover -s integration_tests -v
cd frontend
npm ci
npx playwright install chromium
CMS_AUDIT_WIDTHS=390,320 npm run test:browser
```

Fixture mobile ditolak pada `APP_ENV=production`. Tes tidak mengirim pesan Telegram atau push ke perangkat nyata. CI menjalankan unit, integrasi PostgreSQL, browser, audit aksesibilitas, dan mengambil screenshot halaman/editor.
