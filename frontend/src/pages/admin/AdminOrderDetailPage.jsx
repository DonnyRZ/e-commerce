import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronDown, Clock3, FileText, Landmark, MapPin, Package, RotateCw, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { confirmAdminPayment, getAdminOrder, retryAdminPaymentNotification, updateAdminOrderStatus, updateAdminFulfillment, uploadAdminPaymentEvidence } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

const STEPS = [
  ["pending_payment", "Menunggu pembayaran"],
  ["payment_review", "Bukti transfer"],
  ["paid", "Pembayaran diverifikasi"],
  ["supplier_shipping", "Supplier mengirim"],
  ["received_by_admin", "Diterima admin"],
  ["customer_shipping", "Dikirim ke customer"],
  ["delivered", "Selesai"],
];
const NEXT_STAGE = { paid: "supplier_shipping", supplier_shipping: "received_by_admin", received_by_admin: "customer_shipping", customer_shipping: "delivered" };
const NEXT_LABEL = { supplier_shipping: "Tandai supplier sudah mengirim", received_by_admin: "Tandai barang diterima admin", customer_shipping: "Kirim ke customer", delivered: "Tandai diterima customer" };
const LEGACY_NEXT = { paid: "processing", processing: "shipped", shipped: "delivered" };

function Accordion({ icon: Icon, title, subtitle, children, testId }) {
  return <details className="rounded border border-neutral-200 bg-white" data-testid={testId}><summary className="flex cursor-pointer list-none items-center gap-3 p-4"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#F1F7F4] text-[#02422C]"><Icon className="h-4 w-4" aria-hidden="true" /></span><span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-[#02422C]">{title}</span>{subtitle ? <span className="mt-1 block truncate text-xs text-neutral-500">{subtitle}</span> : null}</span><ChevronDown className="h-4 w-4 text-neutral-400" aria-hidden="true" /></summary><div className="border-t border-neutral-100 px-4 pb-4 pt-3">{children}</div></details>;
}

function getStepDates(order) {
  const fulfillment = new Map((order.fulfillment || []).map((item) => [item.stage, item]));
  const latestEvidence = order.payment?.evidence?.[0];
  return {
    pending_payment: order.created_at,
    payment_review: latestEvidence?.created_at,
    paid: order.payment?.paid_at,
    supplier_shipping: fulfillment.get("supplier_shipping")?.shipped_at,
    received_by_admin: fulfillment.get("received_by_admin")?.received_at,
    customer_shipping: fulfillment.get("customer_shipping")?.shipped_at,
    delivered: fulfillment.get("delivered")?.received_at,
  };
}

function GuidedStepper({ order }) {
  const currentIndex = Math.max(0, STEPS.findIndex(([key]) => key === order.status));
  const dates = getStepDates(order);
  return <aside className="rounded border border-neutral-200 bg-white p-4" data-testid="guided-stepper"><p className="mb-4 text-xs font-semibold uppercase tracking-[0.16em] text-[#CD9B3A]">Order progress</p><ol className="space-y-1">{STEPS.map(([key, label], index) => { const complete = index < currentIndex; const active = index === currentIndex; const date = dates[key]; return <li key={key} className="relative flex gap-3 pb-4 last:pb-0"><span className={`relative z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${complete || active ? "border-[#02422C] bg-[#02422C] text-white" : "border-neutral-300 bg-white text-neutral-400"}`}>{complete ? <Check className="h-4 w-4" aria-hidden="true" /> : active ? <span className="h-2 w-2 rounded-full bg-current" /> : index + 1}</span><span className={`min-w-0 pt-1 text-sm ${active ? "font-semibold text-[#02422C]" : complete ? "text-neutral-600" : "text-neutral-400"}`}><span className="block">{label}</span>{date ? <span className="mt-1 block text-xs font-normal text-neutral-400" data-testid={`step-date-${key}`}>{fmtDate(date)}</span> : null}</span>{index < STEPS.length - 1 ? <span className={`absolute left-3.5 top-7 h-full w-px ${complete ? "bg-[#02422C]" : "bg-neutral-200"}`} /> : null}</li>; })}</ol></aside>;
}

function TelegramPaymentPanel({ payment, orderNumber, busy, onRetry }) {
  const notification = payment?.telegram_notification || {};
  const sendingIsStale = notification.status === "sending"
    && notification.updated_at
    && Date.now() - Date.parse(notification.updated_at) > 120000;
  const statusLabels = {
    not_sent: "Belum dikirim",
    sending: "Sedang dikirim",
    sent: "Pesan terkirim · menunggu customer memilih",
    failed: "Gagal dikirim",
    unknown: "Status pengiriman belum diketahui",
    blocked: "Rekening transfer belum disiapkan",
    unavailable: "Chat Telegram tidak tersedia",
  };
  const status = notification.status || "unavailable";
  const canRetry = ["not_sent", "failed", "unknown", "blocked", "unavailable"].includes(status) || sendingIsStale;
  const retry = () => {
    const uncertain = status === "unknown" || sendingIsStale;
    const confirmText = uncertain
      ? "Telegram mungkin sudah menerima pesan sebelumnya. Kirim ulang tetap dapat membuat pesan pilihan transfer kedua. Lanjutkan?"
      : "Kirim ulang pilihan bank dan instruksi pembayaran ke chat customer?";
    if (!window.confirm(confirmText)) return;
    onRetry({ confirm_uncertain: uncertain });
  };

  return (
    <div className="mt-5 rounded border border-neutral-200 bg-white p-4" data-testid="telegram-payment-notification">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#F1F7F4] text-[#02422C]"><Landmark className="h-4 w-4" aria-hidden="true" /></span>
          <div>
            <h3 className="text-sm font-semibold text-[#02422C]">Pilihan bank di Telegram</h3>
            <p className="mt-1 text-xs text-neutral-500" data-testid="telegram-payment-status">{sendingIsStale ? "Proses kirim tertahan · hasil belum pasti" : statusLabels[status] || status}</p>
          </div>
        </div>
        {canRetry ? <button type="button" onClick={retry} disabled={busy} className="inline-flex h-9 items-center gap-2 border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 disabled:opacity-50" data-testid="retry-telegram-payment"><RotateCw className="h-3.5 w-3.5" aria-hidden="true" /> Kirim ulang</button> : null}
      </div>
      {payment?.destination ? (
        <div className="mt-4 grid gap-2 border-t border-neutral-100 pt-3 text-xs sm:grid-cols-2">
          <p><span className="text-neutral-500">Bank dipilih: </span><strong className="text-neutral-800">{payment.destination.bank_name}</strong></p>
          <p><span className="text-neutral-500">Nomor: </span><strong className="font-mono text-neutral-800">{payment.destination.masked_account_number}</strong></p>
          <p><span className="text-neutral-500">Jenis: </span><span className="text-neutral-700">{payment.destination.destination_type === "card" ? "Kartu" : "Rekening bank"}</span></p>
          <p><span className="text-neutral-500">Atas nama: </span><span className="text-neutral-700">{payment.destination.holder_name}</span></p>
        </div>
      ) : null}
      {notification.error === "no_active_destinations" ? <p className="mt-3 border-l-2 border-amber-500 pl-3 text-xs text-amber-900">Aktifkan minimal satu rekening di Settings → Metode transfer, lalu kirim ulang.</p> : null}
      {notification.error === "telegram_chat_unavailable" ? <p className="mt-3 border-l-2 border-amber-500 pl-3 text-xs text-amber-900">Inquiry ini tidak memiliki chat Telegram yang dapat dihubungi.</p> : null}
      {status === "unknown" || sendingIsStale ? <p className="mt-3 text-[11px] leading-5 text-neutral-500">Hasil kirim sebelumnya ambigu. Pastikan tidak ada pesan pembayaran yang sudah masuk sebelum mengirim ulang.</p> : null}
      {notification.message_id ? <p className="mt-3 text-[11px] text-neutral-400">Telegram message #{notification.message_id} · Order {orderNumber}</p> : null}
    </div>
  );
}

export default function AdminOrderDetailPage() {
  const { orderNumber } = useParams();
  const queryClient = useQueryClient();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const { data: order, isLoading } = useQuery({ queryKey: ["admin-order", orderNumber], queryFn: () => getAdminOrder(orderNumber) });
  const refresh = () => { queryClient.invalidateQueries({ queryKey: ["admin-order", orderNumber] }); queryClient.invalidateQueries({ queryKey: ["admin-order-workflow"] }); queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] }); };
  const run = async (action, success, confirmText) => { if (confirmText && !window.confirm(confirmText)) return; setBusy(true); try { await action(); toast.success(success); refresh(); } catch (error) { const detail = error?.response?.data?.detail; const code = typeof detail === "string" ? detail : detail?.error; const messages = { payment_evidence_required: "Upload bukti transfer terlebih dahulu.", payment_not_eligible: "Pembayaran belum dikonfirmasi.", invalid_fulfillment_transition: "Order belum dapat masuk ke tahap ini.", payment_locked: "Pembayaran order sudah terkunci.", payment_notification_locked: "Order sudah tidak menunggu pembayaran.", payment_notification_already_sent: "Pesan pembayaran sudah terkirim.", payment_notification_outcome_uncertain: "Konfirmasi pengiriman diperlukan sebelum mencoba ulang.", payment_destination_already_selected: "Customer sudah memilih rekening.", payment_notification_in_progress: "Pesan pembayaran sedang dikirim." }; toast.error(messages[code] || "Perubahan order gagal."); } finally { setBusy(false); } };
  if (isLoading) return <div data-testid="admin-order-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  if (!order) return <p className="text-sm text-neutral-500" data-testid="admin-order-missing">Order tidak ditemukan.</p>;

  const nextStage = NEXT_STAGE[order.status];
  const legacyNext = LEGACY_NEXT[order.status];
  const payment = order.payment;
  const latestEvidence = payment?.evidence?.[0];
  const address = order.shipping_address || {};
  const isManual = order.order_source === "telegram_manual";

  return <div data-testid="admin-order-detail">
    <Link to="/orders" className="inline-flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"><ArrowLeft className="h-4 w-4" aria-hidden="true" /> Kembali ke workflow</Link>
    <div className="mt-5 flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Order detail</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">{order.order_number}</h1><p className="mt-1 text-sm text-neutral-500">{fmtDate(order.created_at)} · {order.email || "Guest Telegram"}</p></div><div className="flex flex-wrap items-center gap-2"><StatusPill value={order.status} /><StatusPill value={order.payment_state} />{!isManual && legacyNext ? <button type="button" disabled={busy} onClick={() => run(() => updateAdminOrderStatus(orderNumber, legacyNext), `Order dipindahkan ke ${legacyNext}.`, `Pindahkan order ke ${legacyNext}?`)} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50">Tandai {legacyNext}</button> : null}</div></div>
    <div className="mt-6 grid gap-6 xl:grid-cols-[250px_1fr]"><GuidedStepper order={order} /><main className="min-w-0 space-y-4">
      {isManual && order.status !== "pending_payment" && payment?.destination ? <section className="rounded border border-[#02422C]/25 bg-[#F1F7F4] p-4" data-testid="payment-destination-history"><h2 className="text-sm font-semibold text-[#02422C]">Tujuan transfer customer</h2><div className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><p><span className="text-neutral-500">Bank: </span><strong>{payment.destination.bank_name}</strong></p><p><span className="text-neutral-500">Nomor: </span><strong className="font-mono">{payment.destination.masked_account_number}</strong></p><p><span className="text-neutral-500">Jenis: </span>{payment.destination.destination_type === "card" ? "Kartu" : "Rekening bank"}</p><p><span className="text-neutral-500">Atas nama: </span>{payment.destination.holder_name}</p></div><p className="mt-3 text-[11px] text-neutral-500">Status pesan Telegram: {payment.telegram_notification?.status || "—"}</p></section> : null}
      {isManual && order.status === "pending_payment" ? <section className="rounded border border-[#CD9B3A]/50 bg-[#FDF7E9] p-6" data-testid="active-payment-wait"><div className="flex items-start gap-4"><Clock3 className="mt-1 h-6 w-6 shrink-0 text-[#CD9B3A]" aria-hidden="true" /><div className="min-w-0 flex-1"><h2 className="text-lg font-semibold text-[#02422C]">Menunggu pembayaran</h2><p className="mt-2 text-sm text-neutral-600">Customer belum mengirim bukti transfer. Setelah bukti diterima, unggah di sini untuk masuk ke tahap verifikasi.</p><p className="mt-4 text-sm font-semibold text-[#02422C]">Total yang harus dibayar: {fmtMoney(order.grand_total, order.currency)}</p><TelegramPaymentPanel payment={payment} orderNumber={orderNumber} busy={busy} onRetry={(payload) => run(() => retryAdminPaymentNotification(orderNumber, payload), "Instruksi pembayaran dikirim ulang.")} /><div className="mt-5 rounded border border-dashed border-[#CD9B3A]/60 bg-white p-4"><p className="text-sm font-semibold text-[#02422C]">Upload bukti pembayaran</p><p className="mt-1 text-xs text-neutral-500">JPG, PNG, WebP, atau PDF. Maksimal 8 MB.</p><input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="mt-3 block w-full text-xs" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setSelectedEvidence(file); run(() => uploadAdminPaymentEvidence(orderNumber, file), "Bukti transfer diunggah. Order masuk ke tahap verifikasi."); } }} disabled={busy} /><p className="mt-2 text-[11px] text-neutral-500">{selectedEvidence ? `Dipilih: ${selectedEvidence.name} · ${(selectedEvidence.size / 1024).toFixed(0)} KB` : "Pilih file setelah bukti transfer diterima dari customer."}</p></div></div></div></section> : null}
      {isManual && order.status === "payment_review" ? <section className="rounded border border-[#CD9B3A]/50 bg-[#FDF7E9] p-5" data-testid="active-payment-review"><div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-[#CD9B3A]">Langkah aktif</p><h2 className="mt-1 text-lg font-semibold text-[#02422C]">Pembayaran perlu diverifikasi</h2><p className="mt-1 text-sm text-neutral-600">Periksa nominal dan bukti transfer. Setelah dikonfirmasi, pre-order masuk proses pengadaan.</p></div><ShieldCheck className="h-6 w-6 text-[#CD9B3A]" aria-hidden="true" /></div><div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]"><div className="rounded border border-[#CD9B3A]/30 bg-white p-4 text-sm"><p className="text-xs uppercase tracking-wide text-neutral-500">Total pembayaran</p><p className="mt-2 text-xl font-semibold text-[#02422C]">{fmtMoney(payment?.amount || order.grand_total, order.currency)}</p><p className="mt-4 text-xs text-neutral-500">Reference</p><p className="mt-1 break-all font-mono text-xs text-neutral-700">{payment?.merchant_trans_id || "—"}</p>{payment?.review_note ? <p className="mt-4 border-l-2 border-[#CD9B3A] pl-3 text-xs text-neutral-600">{payment.review_note}</p> : null}</div><div className="rounded border border-neutral-200 bg-white p-4"><div className="flex flex-wrap items-center justify-between gap-2"><div><p className="text-sm font-semibold text-[#02422C]">Bukti transfer</p><p className="mt-1 text-xs text-neutral-500">Upload ulang jika customer mengirim file pengganti.</p></div>{latestEvidence ? <a className="text-sm font-semibold text-[#145A46] hover:underline" href={latestEvidence.download_url} target="_blank" rel="noreferrer">Buka file</a> : null}</div>{latestEvidence ? <div className="mt-4 overflow-hidden rounded border border-neutral-200 bg-neutral-50">{latestEvidence.mime_type?.startsWith("image/") ? <img src={latestEvidence.download_url} alt="Preview bukti transfer" className="max-h-64 w-full object-contain" /> : <p className="p-4 text-sm text-neutral-600">Dokumen PDF siap dibuka melalui tombol Buka file.</p>}<p className="border-t border-neutral-200 px-3 py-2 text-[11px] text-neutral-500">{latestEvidence.original_filename} · {latestEvidence.mime_type} · {(latestEvidence.file_size / 1024).toFixed(0)} KB</p></div> : <p className="mt-4 text-sm text-neutral-500">Belum ada bukti transfer.</p>}<input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="mt-4 block w-full text-xs" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setSelectedEvidence(file); run(() => uploadAdminPaymentEvidence(orderNumber, file), "Bukti transfer diunggah."); } }} disabled={busy} /><p className="mt-2 text-[11px] text-neutral-400">{selectedEvidence ? `Dipilih: ${selectedEvidence.name} · ${(selectedEvidence.size / 1024).toFixed(0)} KB` : "JPG, PNG, WebP, atau PDF. Maksimal 8 MB."}</p></div></div><div className="mt-5 flex justify-end"><button type="button" disabled={busy || payment?.status !== "pending_review"} onClick={() => run(() => confirmAdminPayment(orderNumber), "Pembayaran dikonfirmasi; pre-order masuk proses pengadaan.", "Konfirmasi pembayaran dan mulai proses pengadaan order ini?")} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50"><ShieldCheck className="h-4 w-4" aria-hidden="true" /> Konfirmasi pembayaran</button></div></section> : null}
      {isManual && ["paid", "supplier_shipping", "received_by_admin", "customer_shipping"].includes(order.status) ? <section className="rounded border border-[#02422C]/30 bg-[#F1F7F4] p-5" data-testid="active-fulfillment"><p className="text-xs font-semibold uppercase tracking-wide text-[#CD9B3A]">Langkah aktif</p><h2 className="mt-1 text-lg font-semibold text-[#02422C]">{order.status === "paid" ? "Siap dikirim supplier" : NEXT_LABEL[nextStage] || "Fulfillment"}</h2><p className="mt-1 text-sm text-neutral-600">Supplier → admin → customer. Tracking dan catatan bersifat opsional.</p>{nextStage ? <div className="mt-5 grid gap-3 sm:grid-cols-2"><input className="h-10 border border-neutral-300 bg-white px-3 text-sm" placeholder="Carrier (opsional)" id="fulfillment-carrier" /><input className="h-10 border border-neutral-300 bg-white px-3 text-sm" placeholder="Nomor resi (opsional)" id="fulfillment-tracking" /><input className="h-10 border border-neutral-300 bg-white px-3 text-sm sm:col-span-2" placeholder="Catatan internal (opsional)" id="fulfillment-note" /><button type="button" disabled={busy} onClick={() => { const carrier = document.getElementById("fulfillment-carrier")?.value; const tracking_number = document.getElementById("fulfillment-tracking")?.value; const note = document.getElementById("fulfillment-note")?.value; run(() => updateAdminFulfillment(orderNumber, { stage: nextStage, carrier: carrier || undefined, tracking_number: tracking_number || undefined, note: note || undefined }), NEXT_LABEL[nextStage], `Simpan tahap ${NEXT_LABEL[nextStage]}?`); }} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50 sm:w-fit">{busy ? "Menyimpan…" : NEXT_LABEL[nextStage]}</button></div> : null}<div className="mt-5 space-y-2">{(order.fulfillment || []).map((item) => <div key={item.stage} className="flex flex-wrap justify-between gap-2 border-t border-[#02422C]/10 pt-3 text-xs"><span className="font-medium text-[#02422C]">{STEPS.find(([key]) => key === item.stage)?.[1] || item.stage}</span><span className="text-neutral-600">{item.tracking_number || "Tanpa resi"} · {fmtDate(item.shipped_at || item.received_at)}</span></div>)}</div></section> : null}
      {isManual && order.status === "delivered" ? <section className="rounded border border-[#02422C]/30 bg-[#F1F7F4] p-6" data-testid="active-delivered"><div className="flex items-start gap-4"><Check className="mt-1 h-6 w-6 shrink-0 text-[#02422C]" aria-hidden="true" /><div><h2 className="text-lg font-semibold text-[#02422C]">Order selesai</h2><p className="mt-2 text-sm text-neutral-600">Barang sudah ditandai diterima customer.</p></div></div></section> : null}
      {!isManual ? <section className="rounded border border-neutral-200 bg-white p-5"><h2 className="font-semibold text-[#02422C]">Order historis</h2><p className="mt-2 text-sm text-neutral-600">Order ini menggunakan lifecycle lama. Aksi yang tersedia tetap dibatasi oleh status pembayaran dan transisi backend.</p>{legacyNext ? <button type="button" disabled={busy} onClick={() => run(() => updateAdminOrderStatus(orderNumber, legacyNext), `Order dipindahkan ke ${legacyNext}.`, `Pindahkan order ke ${legacyNext}?`)} className="mt-4 h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50">Tandai {legacyNext}</button> : null}</section> : null}
      <div className="space-y-3"><Accordion icon={Package} title="Ringkasan item" subtitle={`${order.items?.length || 0} item · Total ${fmtMoney(order.grand_total, order.currency)}`} testId="order-items"><div className="divide-y divide-neutral-100">{(order.items || []).map((item) => <div key={item.sku} className="flex flex-wrap justify-between gap-3 py-3 text-sm"><div><p className="font-medium">{item.product_name}</p><p className="mt-1 text-xs text-neutral-500">{item.sku} · {item.quantity} × {fmtMoney(item.unit_price, order.currency)}</p></div><strong>{fmtMoney(item.line_total, order.currency)}</strong></div>)}</div><div className="mt-4 space-y-2 border-t border-neutral-100 pt-3 text-sm"><div className="flex justify-between text-neutral-500"><span>Subtotal</span><span>{fmtMoney(order.subtotal, order.currency)}</span></div><div className="flex justify-between text-neutral-500"><span>Shipping</span><span>{fmtMoney(order.shipping_amount, order.currency)}</span></div><div className="flex justify-between border-t border-neutral-100 pt-2 font-semibold"><span>Total</span><span>{fmtMoney(order.grand_total, order.currency)}</span></div></div></Accordion>
        <Accordion icon={MapPin} title="Alamat customer" subtitle={`${address.recipient_name || "—"} · ${address.city || "—"}`} testId="order-address"><address className="text-sm not-italic leading-6 text-neutral-600">{address.recipient_name || "—"}<br />{address.phone || "—"}<br />{address.address_line_1 || "—"}<br />{address.city || "—"}{address.state_province ? `, ${address.state_province}` : ""} {address.postal_code || ""}<br />{address.country_code || "UZ"}</address></Accordion>
        <Accordion icon={FileText} title="Catatan aktivitas" subtitle={`${order.activity?.length || 0} aktivitas tercatat`} testId="order-activity"><div className="space-y-3">{(order.activity || []).length ? order.activity.map((entry, index) => <div key={`${entry.action}-${index}`} className="border-b border-neutral-100 pb-3 text-xs last:border-0"><p className="font-medium text-[#02422C]">{entry.action}</p><p className="mt-1 text-neutral-500">{fmtDate(entry.created_at)}</p></div>) : <p className="text-sm text-neutral-500">Belum ada catatan aktivitas.</p>}</div></Accordion>
      </div>
    </main></div>
  </div>;
}
