# Audit jeda notifikasi Telegram, 4 Oktober 2026

## Bukti VPS

Audit baca saja pada release `784a79b04bf98cd06939594e58eeb69ccb606325`.
Sumber: GitHub Actions audit runs `37221020514` dan `37221752082`.
Waktu di bawah **UTC**, bukan waktu lokal HP. Semua pesan memakai subscription
aktif yang sama, endpoint FCM yang sama, dan tag percakapan yang sama.

| Pesan masuk | FCM menerima HTTP 201 | Konfirmasi worker/tampilan tiba di VPS | Hasil |
| --- | --- | --- | --- |
| 17:23:22 | 17:23:25.080 | 17:25:15.419 / 17:25:15.471 | sekitar 113 detik sejak chat |
| 17:24:20 | 17:24:21.964 | tidak ada | belum ada bukti tampilan |
| 17:26:41 | 17:26:44.059 | 17:26:44.705 / 17:26:44.814 | sekitar 4 detik sejak chat |

Webhook dan antrean dibuat dalam 0–1 detik. Prioritas HTTP aktual dari pywebpush
2.5.0 adalah `Urgency: high` dan `TTL: 60`, diverifikasi oleh tes library nyata.
HTTP 201 berarti provider menerima, bukan bukti bahwa Android menampilkan.
Telegram cadangan diterima API pada 17:23:41.740 dan 17:24:38.654; itu juga bukan
bukti bahwa aplikasi Telegram di HP sudah menampilkan notifikasi.

Access log mencatat pengambilan worker pada 17:23:47, lalu ikon, badge, dan dua
ACK pada 17:25:15. Log lama hanya mencatat kedatangan ACK di server. Karena itu
log **belum membedakan** event push terlambat dari upload ACK yang ditahan jaringan.
Subscription kedaluwarsa atau instalasi baru tidak menjelaskan tiga pesan ini.

## Masalah yang terbukti dan perbaikan

1. Worker memakai URL HTTP untuk ikon/badge. Chromium memuat sumber gambar
   sebelum memanggil display native. Sumber Chromium
   `third_party/blink/renderer/modules/notifications/notification_resources_loader.cc`
   menetapkan timeout gambar 90 detik; jalur display berada di
   `service_worker_registration_notifications.cc`.
   Tes Chromium native mereproduksi: worker dingin, seluruh halaman CMS ditutup,
   ikon ditahan oleh server, ACK penerimaan muncul tetapi display belum selesai.
   Sesudah ikon dibebaskan, display selesai. Ikon/badge kini ditanam sebagai data
   PNG dalam worker utama, tanpa fetch, importScripts, atau ketergantungan cache.
   Tes versi baru mencatat display 20–26 ms dan nol permintaan gambar.
   Ini membuktikan hambatan implementasi, **belum membuktikan bahwa hambatan tersebut
   menjelaskan seluruh 113 detik pada HP pengguna**.
2. Tag lama sama untuk semua pesan dalam satu percakapan: notifikasi kedua
   menggantikan pertama. Tag kini berdasarkan hash event pesan, stabil untuk retry,
   berbeda untuk pesan berbeda. Timestamp memakai waktu antrean pesan.
3. Dua ACK paralel dan pembaruan fallback dapat saling menimpa JSON. Merge kini
   dilindungi row lock. Tes integrasi mengirim ACK bersamaan dan memeriksa seluruh
   tahap tetap tersimpan.
4. Loop push lama menunggu hingga 5 detik setelah idle dan ikut menunggu API
   Telegram cadangan. Commit transaksi kini membangunkan dispatcher langsung;
   fallback berjalan di task terpisah. Poll 1 detik menjadi pemulihan untuk proses
   lain. Rollback tidak membangunkan dispatcher; diuji di PostgreSQL.

## Membedakan sisa keterlambatan secara faktual

ACK baru membawa versi worker, waktu awal event dan waktu tahap dari HP, serta
elapsed event dari clock monotonic. Backend tetap menyimpan waktu kedatangan ACK
secara terpisah, tidak menggantinya dengan clock HP.

- Event mulai jauh setelah HTTP 201: jeda sebelum worker berjalan (provider,
  Chrome, Android, atau jaringan perangkat).
- Event mulai cepat tetapi display elapsed besar: hambatan worker/display.
- Event dan display cepat tetapi ACK sampai terlambat: jaringan upload ACK.
- ACK tidak ada: hasil belum diketahui; tidak boleh disimpulkan gagal atau sukses.

Jam HP dapat berbeda dari server. Gunakan selisih monotonic untuk biaya display,
versi worker untuk memastikan update aktif, dan pola beberapa pesan untuk korelasi.
Tes CDP menguji handler browser dan app tertutup; tidak melewati FCM serta tidak
mereproduksi Doze/OEM Android. Untuk memastikan hasil pada HP yang dilaporkan,
perlu kejadian nyata sesudah idle dengan worker baru. Tidak ada jaminan platform
Web Push dapat memaksa delivery instan ketika perangkat offline, Chrome dihentikan
paksa, atau Android menahan proses/jaringan.

## Pengujian

- Backend unit: event tag, actual encrypted push HTTP high/TTL, commit wake signal.
- PostgreSQL integration: ACK bersamaan, client timing, commit/rollback wake,
  fanout, revoked admin, dedup webhook, unsubscribe, fallback.
- Chromium native: worker dihentikan, tidak ada halaman CMS, ikon tidak dapat
  diunduh; versi lama tertahan, versi baru tampil tanpa permintaan ikon.
- Worker click: membuka/fokus percakapan yang dituju, termasuk aplikasi tertutup.
- Frontend tests, lint, production build, dan CI penuh sebelum deploy.
