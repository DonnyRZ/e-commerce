import { useState } from "react";
import { Bell, BellOff, CheckCircle2, Download, Smartphone } from "lucide-react";
import { useCmsDevice } from "./CmsDeviceProvider";

export default function CmsDeviceSettings() {
  const device = useCmsDevice();
  const [busy, setBusy] = useState(false);
  const [installHelp, setInstallHelp] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  if (!device) return null;
  const run = async action => {
    setBusy(true); setError(""); setMessage("");
    try { await action(); }
    catch { setError("Tindakan belum berhasil. Periksa koneksi, lalu coba lagi."); }
    finally { setBusy(false); }
  };
  const denied = device.permission === "denied";
  const button = "inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold disabled:opacity-50";
  return (
    <section className="mt-6 rounded-xl border border-neutral-200 bg-white p-5" data-testid="cms-device-settings">
      <div className="flex items-center gap-2 text-[#02422C]"><Smartphone className="h-5 w-5" aria-hidden="true" /><h2 className="font-semibold">Aplikasi CMS di perangkat ini</h2></div>
      <p className="mt-2 text-sm leading-6 text-neutral-600">Pasang CMS di layar utama Android. Buka lewat ikon aplikasi untuk memakai layar penuh tanpa bilah URL.</p>
      <button type="button" disabled={busy || device.installed} className={`${button} mt-4 bg-[#02422C] text-white`} data-testid="cms-install" onClick={() => run(async () => {
        const outcome = await device.install();
        setInstallHelp(outcome === "unavailable");
        if (outcome === "dismissed") setMessage("Pemasangan dibatalkan. Anda dapat mencoba lagi dari menu Chrome.");
        if (outcome === "accepted") setMessage("Pemasangan dikonfirmasi. Setelah selesai, buka CMS dari ikon di layar utama.");
      })}>{device.installed ? <CheckCircle2 className="h-4 w-4" /> : <Download className="h-4 w-4" />}{device.installed ? "CMS sudah terpasang" : "Install ke Android"}</button>
      {installHelp ? <div className="mt-3 rounded-lg bg-neutral-50 p-3 text-sm leading-6" data-testid="cms-install-help"><p>Buka CMS melalui Chrome Android, lalu pilih menu ⋮ → <strong>Tambahkan ke layar utama</strong> → <strong>Instal</strong>. Jika dibuka dari aplikasi lain, pilih “Buka di Chrome” dahulu.</p></div> : null}
      <div className="mt-5 border-t border-neutral-100 pt-5">
        <div className="flex items-center gap-2"><Bell className="h-4 w-4 text-[#02422C]" aria-hidden="true" /><h3 className="text-sm font-semibold">Chat Telegram &amp; order baru</h3></div>
        <p className="mt-2 text-sm leading-6 text-neutral-600">CMS mengirim push ke setiap perangkat terdaftar. Jika push chat belum terkonfirmasi dalam 15 detik, bot Telegram Business mengirim notifikasi cadangan dengan tautan langsung ke chat.</p>
        <p className="mt-3 text-sm font-medium" role="status" data-testid="cms-push-status">{device.registered ? "Notifikasi aktif di perangkat ini" : denied ? "Izin notifikasi diblokir" : !device.supported ? "Browser ini belum mendukung notifikasi CMS" : device.config.isError ? "Status notifikasi server belum dapat dimuat" : device.config.isLoading ? "Memeriksa layanan notifikasi…" : !device.config.data?.enabled ? "Layanan notifikasi belum tersedia" : device.autoEnrollDisabled ? "Notifikasi belum diaktifkan" : device.permission === "granted" ? "Pendaftaran push perlu dipulihkan di perangkat ini" : "Notifikasi belum diaktifkan"}</p>
        {device.config.data?.telegram_backup_url ? <p className="mt-3 text-sm leading-6 text-neutral-600">Aktifkan cadangan sekali pada akun Telegram Business yang terhubung: <a className="font-semibold text-[#02422C] underline" href={device.config.data.telegram_backup_url} target="_blank" rel="noreferrer">buka bot lalu tekan Start</a>.</p> : null}
        {denied ? <p className="mt-2 text-xs leading-5 text-neutral-500">Izinkan notifikasi CMS melalui pengaturan situs Chrome atau pengaturan aplikasi Android, lalu buka kembali halaman ini.</p> : null}
        {!device.supported ? <p className="mt-2 text-xs leading-5 text-neutral-500">Gunakan Chrome Android terbaru dengan koneksi HTTPS untuk mengaktifkan notifikasi.</p> : null}
        {device.workerError ? <p className="mt-2 text-xs text-amber-800">Aplikasi belum siap menerima notifikasi. Muat ulang halaman dan coba lagi.</p> : null}
        <div className="mt-3 flex flex-wrap gap-2">
          {device.registered ? <>
            <button type="button" className={`${button} border border-neutral-300`} disabled={busy} data-testid="cms-push-test" onClick={() => run(async () => { await device.test(); setMessage("Notifikasi tes masuk antrean pengiriman. Periksa notifikasi perangkat ini."); })}>Kirim notifikasi tes</button>
            <button type="button" className={`${button} text-neutral-600`} disabled={busy} data-testid="cms-push-disable" onClick={() => run(() => device.disable())}><BellOff className="h-4 w-4" />Nonaktifkan</button>
          </> : <button type="button" className={`${button} border border-[#02422C] text-[#02422C]`} disabled={busy || denied || !device.supported || !device.config.data?.enabled} data-testid="cms-push-enable" onClick={() => run(async () => { if (await device.enable()) setMessage("Perangkat terdaftar untuk notifikasi chat Telegram dan order baru."); })}><Bell className="h-4 w-4" />Aktifkan notifikasi</button>}
          {device.config.isError ? <button type="button" className={`${button} border border-neutral-300`} onClick={() => device.config.refetch()}>Coba lagi</button> : null}
        </div>
      </div>
      {message ? <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm leading-5 text-emerald-900" role="status">{message}</p> : null}
      {error ? <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-800" role="alert">{error}</p> : null}
    </section>
  );
}
