# Audit mobile CMS — 4 Oktober 2026

## Cakupan dan bukti

Audit dilakukan pada stack development terisolasi dengan PostgreSQL, Redis,
backend dan dua frontend hasil build produksi. Semua data percakapan/order audit
bersifat sintetis; tidak ada pesan Telegram atau push ke perangkat nyata yang
dikirim selama tes.

Screenshot lengkap diambil untuk seluruh route CMS dan keadaan editor utama:
login, pemulihan password, dashboard, katalog, produk baru dan empat tipe produk,
departemen/kategori, tiga filter order, inquiry dan tujuh tahap order, inbox dan
percakapan Telegram, customer/detail, Content Hub/semua konten, homepage, stories,
help, navigation/footer, media/editor, Settings/payment editor, dua locale editor,
media picker, drawer dan panel produk Telegram. Semua 54 screenshot mobile
ditinjau secara visual; form panjang juga diperiksa pada bagian tengah/bawah.

| Lebar viewport | Screenshot/keadaan | Hasil pemeriksaan |
| --- | ---: | --- |
| 320 px | 54 | Tidak ada overflow halaman, gambar rusak, atau error JavaScript |
| 390 px | 54 | Sama; 0 pelanggaran axe WCAG A/AA pada seluruh keadaan |
| 412 px | 54 | Tidak ada overflow halaman, gambar rusak, atau error JavaScript |
| 768 px | 54 | Sama, termasuk drawer dan detail customer versi tablet |
| 1280 px | 52 | Sama; drawer/panel mobile digantikan layout desktop |

Galeri lokal tersedia di `/workspace/cms-mobile-audit/final/index.html`, dengan
268 gambar penuh dan `report.json` per ukuran. Screenshot tidak dimasukkan ke
Git. CI menyimpan screenshot serta trace kegagalan sebagai artifact
`cms-mobile-audit` selama 14 hari.

## Temuan yang diperbaiki

| Temuan | Perbaikan |
| --- | --- |
| Label form tidak terhubung, kontrol/filter tanpa nama, dan teks terlalu pucat | ID/label/aria pada editor, filter dan upload; kontras CMS ditingkatkan |
| Tabel audit Settings dan beberapa kartu melebar pada layar kecil | Kartu mobile, tabel desktop dengan scroll lokal, grid dan judul dapat menyusut/membungkus |
| Field media sempit di samping preview | Field disusun di bawah preview pada mobile |
| Kontrol kecil dan input memicu zoom browser mobile | Target tombol 44 px, input 16 px, area checkbox/radio diperbesar |
| Drawer/panel chat tidak menjaga fokus keyboard | Dialog dengan focus trap, Escape, dan pengembalian fokus; panel ditutup ketika berpindah ke desktop |
| Restore sesi membuat sebagian form terus loading | Pembersihan cache privat diurutkan sebelum identitas login diterbitkan |
| Link order chat menjadi `/admin/admin/orders/...` | Link memakai basename router dan tetap dalam scope aplikasi |
| Chat terpilih tidak dapat dibuka dari notifikasi | ID percakapan disimpan di query URL; kembali dari login menjaga deep link |
| Draft chat lama terbawa dan respons kirim terlambat menghapus draft chat lain | Draft direset saat ganti percakapan; respons hanya membersihkan percakapan asal |
| Tinggi chat/composer tidak mengikuti keyboard dan safe area | Visual viewport, safe area, dan autoscroll hanya ketika berada dekat pesan terbaru |
| Carousel dengan banyak produk berisiko memotong kontrol sentuh | Tombol 44 px membungkus; diuji dengan 10 produk pada 320 px |
| CMS belum installable dan navigasi root keluar dari scope | Manifest, ikon, service worker, tombol install, basename `/admin/`, redirect relatif HTTPS |
| Pesan media Telegram nonfoto diabaikan | Voice/dokumen/media mendapat placeholder dan notifikasi masuk; isi media tersebut dibuka di Telegram |
| Tidak ada notifikasi per perangkat | Subscription admin, antrean transaksi, enkripsi Web Push, retry, penonaktifan endpoint kedaluwarsa, tombol tes/nonaktifkan |
| File build dari checkout cloud tidak dapat dibaca worker Nginx | Permission asset diperbaiki pada kedua Dockerfile frontend |

## Pengujian

- Backend: **77 unit test** lulus, termasuk enkripsi/dekripsi payload Web Push
  nyata dan VAPID signature dengan jaringan provider diintersep.
- PostgreSQL + HTTP API: **5 tes integrasi** lulus. Dua admin dengan tiga device
  mendapat fan-out chat dan order; duplicate/edit/outbound tidak menambah push;
  rollback, logout/token version, perubahan role, unsubscribe, CSRF dan ownership
  diperiksa. Provider eksternal diganti transport tes.
- Frontend: **66 tes dalam 17 suite**, lint, build storefront dan CMS lulus.
- Browser: **20 tes fungsional** lulus, termasuk installability native Chromium,
  install diterima/dibatalkan, permission ditolak/diterima, daftar/nonaktifkan
  perangkat, native service-worker push ketika halaman di background, deep link,
  keyboard, focus trap, carousel panjang, offline serta batas cache privat.
- Audit browser: **5 ukuran layar** lulus. Audit 390/320 diulang pada image CMS
  final; 54 keadaan per ukuran. Total cakupan lintas ukuran: 268 screenshot.
- Image Docker CMS dan backend berhasil dibangun dan dijalankan; API smoke
  lulus pada image final. Head database adalah `c8d9e0f1a2b3`.
- Migration dari database baru sampai head, downgrade/upgrade revision push
  pada database sementara, syntax shell deploy, render Compose produksi dan
  `git diff --check` lulus.

Tes browser install prompt dan subscription memakai simulasi event/transport
untuk cabang UI; tes installability dan service worker memakai Chromium asli.
Belum ada pengujian instalasi fisik Android atau pengiriman langsung melalui
FCM ke Android dari production. Setelah deployment, admin perlu konfirmasi
dialog instalasi Android, izin notifikasi pada tiap device, lalu memakai tombol
notifikasi tes. Browser tidak mengizinkan silent install atau silent permission.

## Kesiapan GitHub Actions ke VPS

Workspace cloud tidak mengganti runner GitHub Actions. Workflow existing tetap
memverifikasi CI, membuat archive commit immutable beserta checksum, memakai
SSH dengan known hosts terpin, menjalankan wrapper deploy, dan memeriksa health.
Branch produksi yang diizinkan tetap `codex/deployment-marketplace` dan `main`.
CI diperluas untuk mencakup hasil pekerjaan ini.

Deploy script menyiapkan kunci VAPID persisten sebelum migration; backend hanya
memasang kunci read-only. Petunjuk instalasi, konfigurasi dan backup kunci ada
di [cms-mobile-app.md](cms-mobile-app.md). Runbook deployment disesuaikan dengan
service `cms`/`storefront` dan persiapan kunci.

Deployment **belum dijalankan**: `gh auth status` menolak `GH_TOKEN` environment
ini, dan konfirmasi backup database/media di luar VPS belum diberikan. Input
`backup_confirmed=true` memang diwajibkan workflow existing. Nilai/kesiapan SSH
secrets GitHub production serta backup VPS belum dapat diverifikasi melalui
akses yang tersedia. Jangan menyatakan backup terkonfirmasi sebelum bukti atau
konfirmasi operator tersedia.

## Menjalankan ulang

Lihat [cms-mobile-app.md](cms-mobile-app.md) untuk seed dan tes terisolasi.
Untuk seluruh ukuran layar:

```sh
cd frontend
CMS_AUDIT_WIDTHS=390,320,412,768,1280 npm run test:browser
```

Pada cloud ini, set `PLAYWRIGHT_CHROMIUM_EXECUTABLE=/usr/bin/chromium` untuk
browser sistem. Siapkan ruang disk sebelum build Docker dengan storage `vfs`;
build CMS/backend secara berurutan dan bersihkan cache build yang tidak digunakan
bila diperlukan. Tidak ada volume/database/media yang dihapus untuk cleanup.
