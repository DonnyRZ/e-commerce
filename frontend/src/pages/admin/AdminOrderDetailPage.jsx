import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronDown, Clock3, FileText, Landmark, MapPin, Package, RotateCw, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";
import { confirmAdminPayment, getAdminOrder, retryAdminPaymentNotification, updateAdminOrderStatus, updateAdminFulfillment, uploadAdminPaymentEvidence } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { OrderProgress, ORDER_STEPS } from "./OrderProgress";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

const MAX_EVIDENCE_BYTES = 8 * 1024 * 1024;
const ALLOWED_EVIDENCE_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];
const MANUAL_STATUS_LABELS = {
  pending_payment: "Menunggu pembayaran",
  payment_review: "Menunggu konfirmasi admin",
  paid: "Pembayaran dikonfirmasi",
  supplier_shipping: "Supplier mengirim",
  received_by_admin: "Diterima admin",
  customer_shipping: "Dikirim ke customer",
  delivered: "Selesai",
};
const NEXT_STAGE = { paid: "supplier_shipping", supplier_shipping: "received_by_admin", received_by_admin: "customer_shipping", customer_shipping: "delivered" };
const NEXT_LABEL = { supplier_shipping: "Tandai supplier sudah mengirim", received_by_admin: "Tandai barang diterima admin", customer_shipping: "Kirim ke customer", delivered: "Tandai diterima customer" };
const LEGACY_NEXT = { paid: "processing", processing: "shipped", shipped: "delivered" };

function Accordion({ icon: Icon, title, subtitle, children, testId }) {
  return (
    <details className="rounded border border-neutral-200 bg-white" data-testid={testId}>
      <summary className="flex cursor-pointer list-none items-center gap-3 p-4">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#F1F7F4] text-[#02422C]"><Icon className="h-4 w-4" aria-hidden="true" /></span>
        <span className="min-w-0 flex-1"><span className="block text-sm font-semibold text-[#02422C]">{title}</span>{subtitle ? <span className="mt-1 block truncate text-xs text-neutral-500">{subtitle}</span> : null}</span>
        <ChevronDown className="h-4 w-4 text-neutral-400" aria-hidden="true" />
      </summary>
      <div className="border-t border-neutral-100 px-4 pb-4 pt-3">{children}</div>
    </details>
  );
}

function TelegramPaymentPanel({ payment, orderNumber, busy, onRetry }) {
  const notification = payment?.telegram_notification || {};
  const sendingIsStale = notification.status === "sending"
    && notification.updated_at
    && Date.now() - Date.parse(notification.updated_at) > 120000;
  const statusLabels = {
    not_sent: "Belum dikirim",
    sending: "Sedang mengirim pilihan bank ke Telegram…",
    sent: "Pilihan bank terkirim · menunggu customer memilih",
    failed: "Pilihan bank gagal dikirim",
    unknown: "Status pengiriman belum diketahui",
    blocked: "Rekening transfer belum disiapkan",
    unavailable: "Chat Telegram tidak tersedia",
  };
  const status = notification.status || "unavailable";
  const canRetry = ["not_sent", "failed", "unknown", "blocked", "unavailable"].includes(status) || sendingIsStale;
  const retry = () => {
    const uncertain = status === "unknown" || sendingIsStale;
    const confirmText = uncertain
      ? "Telegram mungkin sudah menerima pesan sebelumnya. Kirim ulang dapat membuat pesan pilihan transfer kedua. Lanjutkan?"
      : "Kirim ulang pilihan bank dan instruksi pembayaran ke chat customer?";
    if (window.confirm(confirmText)) onRetry({ confirm_uncertain: uncertain });
  };

  return (
    <section className="rounded border border-neutral-200 bg-white p-4" data-testid="telegram-payment-notification">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#F1F7F4] text-[#02422C]"><Landmark className="h-4 w-4" aria-hidden="true" /></span>
          <div className="min-w-0"><h3 className="text-sm font-semibold text-[#02422C]">Pilihan bank di Telegram</h3><p className="mt-1 text-xs text-neutral-600" data-testid="telegram-payment-status">{sendingIsStale ? "Pengiriman tertahan · hasil belum pasti" : statusLabels[status] || status}</p></div>
        </div>
        {canRetry ? <button type="button" onClick={retry} disabled={busy} className="inline-flex h-9 shrink-0 items-center gap-2 border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 disabled:opacity-50" data-testid="retry-telegram-payment"><RotateCw className="h-3.5 w-3.5" aria-hidden="true" /> Kirim ulang</button> : null}
      </div>
      {payment?.destination ? (
        <div className="mt-4 grid gap-2 border-t border-neutral-100 pt-3 text-xs sm:grid-cols-2" data-testid="selected-payment-destination">
          <p><span className="text-neutral-500">Bank dipilih: </span><strong className="text-neutral-800">{payment.destination.bank_name}</strong></p>
          <p><span className="text-neutral-500">Nomor: </span><strong className="font-mono text-neutral-800">{payment.destination.masked_account_number}</strong></p>
          <p><span className="text-neutral-500">Jenis: </span><span className="text-neutral-700">{payment.destination.destination_type === "card" ? "Kartu" : "Rekening bank"}</span></p>
          <p><span className="text-neutral-500">Atas nama: </span><span className="text-neutral-700">{payment.destination.holder_name}</span></p>
        </div>
      ) : null}
      {notification.error === "no_active_destinations" ? <p className="mt-3 border-l-2 border-amber-500 pl-3 text-xs text-amber-900">Aktifkan minimal satu rekening di Settings → Metode transfer, lalu kirim ulang.</p> : null}
      {notification.error === "telegram_chat_unavailable" ? <p className="mt-3 border-l-2 border-amber-500 pl-3 text-xs text-amber-900">Inquiry ini tidak memiliki chat Telegram yang dapat dihubungi.</p> : null}
      {status === "unknown" || sendingIsStale ? <p className="mt-3 text-[11px] leading-5 text-neutral-500">Hasil sebelumnya belum pasti. Pastikan pesan belum masuk sebelum mengirim ulang.</p> : null}
      {notification.message_id ? <p className="mt-3 text-[11px] text-neutral-400">Pesan Telegram #{notification.message_id} · Order {orderNumber}</p> : null}
    </section>
  );
}

function EvidencePreview({ evidence, localUrl, title }) {
  if (!evidence) return null;
  const isImage = evidence.mime_type?.startsWith("image/") || evidence.type?.startsWith("image/");
  const url = localUrl || evidence.download_url;
  return (
    <div className="overflow-hidden rounded border border-neutral-200 bg-neutral-50" data-testid="payment-evidence-preview">
      {isImage ? <img src={url} alt={title} className="max-h-64 w-full object-contain" /> : <div className="flex items-center gap-3 p-4 text-sm text-neutral-600"><FileText className="h-5 w-5 shrink-0" aria-hidden="true" /><span>Dokumen PDF siap disimpan untuk arsip.</span></div>}
      <p className="border-t border-neutral-200 px-3 py-2 text-[11px] text-neutral-500">{evidence.original_filename || evidence.name} · {evidence.mime_type || evidence.type} · {((evidence.file_size ?? evidence.size) / 1024).toFixed(0)} KB</p>
    </div>
  );
}

function PaymentEvidenceUpload({
  fileRef,
  selectedEvidence,
  localPreviewUrl,
  latestEvidence,
  evidenceCount,
  busy,
  uploadProgress,
  onSelect,
  onClear,
  onUpload,
}) {
  return (
    <section className="rounded border border-dashed border-[#CD9B3A]/60 bg-white p-4" data-testid="payment-evidence-archive">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div><h3 className="text-sm font-semibold text-[#02422C]">Bukti transfer customer · arsip audit</h3><p className="mt-1 text-xs leading-5 text-neutral-600">Simpan bukti yang dikirim customer. Upload ini tidak mengonfirmasi pembayaran atau mengubah tahap order.</p></div>
        {evidenceCount > 0 ? <span className="rounded-full bg-[#F1F7F4] px-2.5 py-1 text-[11px] font-medium text-[#02422C]">{evidenceCount} file tersimpan</span> : null}
      </div>
      {latestEvidence ? (
        <div className="mt-4 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2 text-xs"><p className="font-medium text-neutral-700">Bukti terakhir tersimpan</p><a className="font-semibold text-[#145A46] hover:underline" href={latestEvidence.download_url} target="_blank" rel="noreferrer">Buka file</a></div>
          <EvidencePreview evidence={latestEvidence} title="Bukti transfer customer tersimpan" />
        </div>
      ) : <p className="mt-4 rounded bg-neutral-50 px-3 py-2 text-xs text-neutral-600">Belum ada bukti tersimpan. Simpan bukti sebelum mengonfirmasi pembayaran.</p>}
      <label className="mt-4 block text-xs font-medium text-neutral-700">Tambah bukti atau simpan pengganti
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp,application/pdf"
          className="mt-2 block w-full text-xs file:mr-3 file:h-9 file:border-0 file:bg-neutral-100 file:px-3 file:text-xs file:font-semibold file:text-neutral-700 hover:file:bg-neutral-200"
          onChange={(event) => onSelect(event.target.files?.[0] || null)}
          disabled={busy}
          data-testid="payment-evidence-input"
        />
      </label>
      {selectedEvidence ? (
        <div className="mt-4 space-y-3" data-testid="selected-payment-evidence">
          <EvidencePreview evidence={selectedEvidence} localUrl={localPreviewUrl} title="Pratinjau bukti transfer yang dipilih" />
          {uploadProgress !== null ? (
            <div>
              <div className="mb-1 flex justify-between text-[11px] text-neutral-600"><span>{uploadProgress >= 100 ? "Menyimpan file…" : "Mengunggah bukti…"}</span><span>{uploadProgress}%</span></div>
              <progress className="h-2 w-full accent-[#02422C]" max="100" value={uploadProgress} aria-label="Progres upload bukti transfer" />
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={onUpload} disabled={busy} className="inline-flex h-9 items-center gap-2 bg-[#145A46] px-3 text-xs font-semibold text-white hover:bg-[#02422C] disabled:opacity-50" data-testid="save-payment-evidence">{busy ? "Menyimpan bukti…" : "Simpan bukti untuk arsip"}</button>
            <button type="button" onClick={onClear} disabled={busy} className="inline-flex h-9 items-center gap-1 border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 disabled:opacity-50"><X className="h-3.5 w-3.5" aria-hidden="true" /> Batalkan</button>
          </div>
        </div>
      ) : null}
    </section>
  );
}

function PaymentStage({
  order,
  payment,
  orderNumber,
  busy,
  fileRef,
  selectedEvidence,
  localPreviewUrl,
  uploadProgress,
  onSelectEvidence,
  onClearEvidence,
  onUploadEvidence,
  onRetryNotification,
  onConfirm,
}) {
  const evidence = payment?.evidence || [];
  const latestEvidence = evidence[0];
  const legacyReview = order.status === "payment_review";
  const canConfirm = Boolean(latestEvidence) && ["pending", "pending_review"].includes(payment?.status);

  return (
    <section className="rounded border border-[#CD9B3A]/50 bg-[#FDF7E9] p-5 sm:p-6" data-testid="active-payment-stage">
      <div className="flex items-start gap-3">
        <Clock3 className="mt-1 h-6 w-6 shrink-0 text-[#CD9B3A]" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="text-xs font-semibold uppercase tracking-wide text-[#CD9B3A]">Langkah 2 dari 6</p>
          <h2 className="mt-1 text-lg font-semibold text-[#02422C]">Pembayaran · {legacyReview || latestEvidence ? "menunggu konfirmasi admin" : "menunggu transfer"}</h2>
          <p className="mt-2 text-sm leading-6 text-neutral-600">Customer membayar satu kali sesuai total final dan mengirim bukti melalui Telegram. Admin cocokkan mutasi rekening secara manual; bukti di CMS hanya untuk arsip.</p>
          {legacyReview ? <p className="mt-3 rounded border border-[#CD9B3A]/30 bg-white px-3 py-2 text-xs text-neutral-600">Order ini dibuat sebelum alur pembayaran disederhanakan. Tetap dapat dikonfirmasi di halaman yang sama.</p> : null}
        </div>
      </div>

      <div className="mt-5 grid gap-3 sm:grid-cols-2">
        <div className="rounded border border-[#CD9B3A]/30 bg-white p-4">
          <p className="text-xs uppercase tracking-wide text-neutral-500">Total transfer · satu kali</p>
          <p className="mt-2 text-2xl font-semibold text-[#02422C]">{fmtMoney(payment?.amount || order.grand_total, order.currency)}</p>
        </div>
        <div className="rounded border border-[#CD9B3A]/30 bg-white p-4">
          <p className="text-xs uppercase tracking-wide text-neutral-500">Referensi order</p>
          <p className="mt-2 break-all font-mono text-sm font-semibold text-[#02422C]">{orderNumber}</p>
        </div>
      </div>

      <div className="mt-4 space-y-4">
        <TelegramPaymentPanel payment={payment} orderNumber={orderNumber} busy={busy} onRetry={onRetryNotification} />
        <PaymentEvidenceUpload
          fileRef={fileRef}
          selectedEvidence={selectedEvidence}
          localPreviewUrl={localPreviewUrl}
          latestEvidence={latestEvidence}
          evidenceCount={evidence.length}
          busy={busy}
          uploadProgress={uploadProgress}
          onSelect={onSelectEvidence}
          onClear={onClearEvidence}
          onUpload={onUploadEvidence}
        />
      </div>

      <div className="mt-5 flex flex-col items-stretch gap-3 border-t border-[#CD9B3A]/30 pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs leading-5 text-neutral-600">Pastikan dana benar-benar masuk pada mutasi rekening sebelum menekan tombol konfirmasi.</p>
        <button type="button" disabled={busy || !canConfirm} onClick={onConfirm} className="inline-flex min-h-11 shrink-0 items-center justify-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white hover:bg-[#145A46] disabled:cursor-not-allowed disabled:opacity-50" data-testid="confirm-payment-and-continue">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          {busy ? "Menyimpan…" : "Konfirmasi pembayaran & lanjutkan ke supplier"}
        </button>
      </div>
      {!latestEvidence ? <p className="mt-2 text-right text-[11px] text-neutral-500">Tombol konfirmasi aktif setelah bukti tersimpan.</p> : null}
    </section>
  );
}

export default function AdminOrderDetailPage() {
  const { orderNumber } = useParams();
  const queryClient = useQueryClient();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [localPreviewUrl, setLocalPreviewUrl] = useState(null);
  const { data: order, isLoading } = useQuery({
    queryKey: ["admin-order", orderNumber],
    queryFn: () => getAdminOrder(orderNumber),
    refetchInterval: (query) => {
      const current = query.state.data;
      return current?.order_source === "telegram_manual"
        && ["pending_payment", "payment_review"].includes(current.status)
        ? 3000
        : false;
    },
    refetchIntervalInBackground: false,
  });

  useEffect(() => {
    if (!selectedEvidence || !selectedEvidence.type.startsWith("image/")) {
      setLocalPreviewUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(selectedEvidence);
    setLocalPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selectedEvidence]);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-order", orderNumber] });
    queryClient.invalidateQueries({ queryKey: ["admin-order-workflow"] });
    queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
  };

  const run = async (action, success, confirmText) => {
    if (confirmText && !window.confirm(confirmText)) return null;
    setBusy(true);
    try {
      const result = await action();
      toast.success(success);
      refresh();
      return result;
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const code = typeof detail === "string" ? detail : detail?.error;
      const messages = {
        payment_evidence_required: "Simpan bukti transfer untuk arsip sebelum konfirmasi.",
        payment_not_eligible: "Pembayaran belum dapat dikonfirmasi.",
        payment_record_missing: "Data pembayaran tidak ditemukan.",
        invalid_fulfillment_transition: "Order belum dapat masuk ke tahap ini.",
        payment_locked: "Pembayaran order sudah terkunci.",
        payment_notification_locked: "Order sudah tidak menunggu pembayaran.",
        payment_notification_already_sent: "Pesan pembayaran sudah terkirim.",
        payment_notification_outcome_uncertain: "Konfirmasi hasil pengiriman diperlukan sebelum mencoba ulang.",
        payment_destination_already_selected: "Customer sudah memilih rekening.",
        payment_notification_in_progress: "Pilihan bank sedang dikirim ke Telegram.",
      };
      toast.error(messages[code] || "Perubahan order gagal. Periksa koneksi lalu coba lagi.");
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handleEvidenceSelect = (file) => {
    if (!file) return;
    if (!ALLOWED_EVIDENCE_TYPES.includes(file.type)) {
      toast.error("Pilih bukti dalam format JPG, PNG, WebP, atau PDF.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    if (file.size > MAX_EVIDENCE_BYTES) {
      toast.error("Ukuran bukti maksimal 8 MB.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setSelectedEvidence(file);
    setUploadProgress(null);
  };

  const clearSelectedEvidence = () => {
    setSelectedEvidence(null);
    setUploadProgress(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  const handleEvidenceUpload = async () => {
    if (!selectedEvidence) return;
    setUploadProgress(0);
    const uploaded = await run(
      () => uploadAdminPaymentEvidence(orderNumber, selectedEvidence, (progress) => setUploadProgress(progress)),
      "Bukti tersimpan untuk arsip. Pembayaran belum dikonfirmasi.",
    );
    if (!uploaded) {
      setUploadProgress(null);
      return;
    }
    queryClient.setQueryData(["admin-order", orderNumber], (current) => {
      if (!current?.payment) return current;
      const existing = current.payment.evidence || [];
      return {
        ...current,
        payment: {
          ...current.payment,
          evidence: [uploaded, ...existing.filter((item) => item.id !== uploaded.id)],
        },
      };
    });
    setSelectedEvidence(null);
    setUploadProgress(null);
    if (fileRef.current) fileRef.current.value = "";
  };

  if (isLoading) return <div data-testid="admin-order-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  if (!order) return <p className="text-sm text-neutral-500" data-testid="admin-order-missing">Order tidak ditemukan.</p>;

  const nextStage = NEXT_STAGE[order.status];
  const legacyNext = LEGACY_NEXT[order.status];
  const payment = order.payment;
  const address = order.shipping_address || {};
  const isManual = order.order_source === "telegram_manual";
  const isPaymentStage = isManual && ["pending_payment", "payment_review"].includes(order.status);

  return (
    <div className="mx-auto max-w-7xl" data-testid="admin-order-detail">
      <Link to="/orders" className="inline-flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"><ArrowLeft className="h-4 w-4" aria-hidden="true" /> Kembali ke workflow</Link>
      <header className="mt-5 flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Order detail</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">{order.order_number}</h1><p className="mt-1 text-sm text-neutral-500">{fmtDate(order.created_at)} · {order.email || "Guest Telegram"}</p></div>
        <div className="flex flex-wrap items-center gap-2">{isManual ? <StatusPill value={MANUAL_STATUS_LABELS[order.status] || order.status} tone={["pending_payment", "payment_review"].includes(order.status) ? "amber" : order.status === "delivered" ? "emerald" : "blue"} /> : <><StatusPill value={order.status} /><StatusPill value={order.payment_state} /></>}{!isManual && legacyNext ? <button type="button" disabled={busy} onClick={() => run(() => updateAdminOrderStatus(orderNumber, legacyNext), `Order dipindahkan ke ${legacyNext}.`, `Pindahkan order ke ${legacyNext}?`)} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50">Tandai {legacyNext}</button> : null}</div>
      </header>

      {isManual ? <OrderProgress currentStage={order.status} className="mt-6 rounded border border-[#CD9B3A]/30 bg-[#FDF7E9] p-4" testId="order-progress" /> : null}

      <main className="mt-5 space-y-4">
        {isPaymentStage ? (
          <PaymentStage
            order={order}
            payment={payment}
            orderNumber={orderNumber}
            busy={busy}
            fileRef={fileRef}
            selectedEvidence={selectedEvidence}
            localPreviewUrl={localPreviewUrl}
            uploadProgress={uploadProgress}
            onSelectEvidence={handleEvidenceSelect}
            onClearEvidence={clearSelectedEvidence}
            onUploadEvidence={handleEvidenceUpload}
            onRetryNotification={(payload) => run(() => retryAdminPaymentNotification(orderNumber, payload), "Permintaan kirim ulang pilihan bank dimasukkan.")}
            onConfirm={() => run(() => confirmAdminPayment(orderNumber), "Pembayaran dikonfirmasi. Order siap diteruskan ke supplier.")}
          />
        ) : null}

        {isManual && !isPaymentStage && payment?.destination ? (
          <section className="rounded border border-[#02422C]/25 bg-[#F1F7F4] p-4" data-testid="payment-destination-history">
            <h2 className="text-sm font-semibold text-[#02422C]">Tujuan transfer customer</h2>
            <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2"><p><span className="text-neutral-500">Bank: </span><strong>{payment.destination.bank_name}</strong></p><p><span className="text-neutral-500">Nomor: </span><strong className="font-mono">{payment.destination.masked_account_number}</strong></p><p><span className="text-neutral-500">Jenis: </span>{payment.destination.destination_type === "card" ? "Kartu" : "Rekening bank"}</p><p><span className="text-neutral-500">Atas nama: </span>{payment.destination.holder_name}</p></div>
            <p className="mt-3 text-[11px] text-neutral-500">Status pesan Telegram: {payment.telegram_notification?.status || "—"}</p>
          </section>
        ) : null}

        {isManual && ["paid", "supplier_shipping", "received_by_admin", "customer_shipping"].includes(order.status) ? (
          <section className="rounded border border-[#02422C]/30 bg-[#F1F7F4] p-5" data-testid="active-fulfillment">
            <p className="text-xs font-semibold uppercase tracking-wide text-[#CD9B3A]">Langkah aktif</p>
            <h2 className="mt-1 text-lg font-semibold text-[#02422C]">{order.status === "paid" ? "Siap diteruskan ke supplier" : NEXT_LABEL[nextStage] || "Fulfillment"}</h2>
            <p className="mt-1 text-sm text-neutral-600">Order hanya diteruskan setelah pembayaran dikonfirmasi. Tracking dan catatan bersifat opsional.</p>
            {nextStage ? (
              <div className="mt-5 grid gap-3 sm:grid-cols-2">
                <input className="h-10 border border-neutral-300 bg-white px-3 text-sm" placeholder="Carrier (opsional)" id="fulfillment-carrier" />
                <input className="h-10 border border-neutral-300 bg-white px-3 text-sm" placeholder="Nomor resi (opsional)" id="fulfillment-tracking" />
                <input className="h-10 border border-neutral-300 bg-white px-3 text-sm sm:col-span-2" placeholder="Catatan internal (opsional)" id="fulfillment-note" />
                <button type="button" disabled={busy} onClick={() => { const carrier = document.getElementById("fulfillment-carrier")?.value; const tracking_number = document.getElementById("fulfillment-tracking")?.value; const note = document.getElementById("fulfillment-note")?.value; run(() => updateAdminFulfillment(orderNumber, { stage: nextStage, carrier: carrier || undefined, tracking_number: tracking_number || undefined, note: note || undefined }), NEXT_LABEL[nextStage], `Simpan tahap ${NEXT_LABEL[nextStage]}?`); }} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50 sm:w-fit">{busy ? "Menyimpan…" : NEXT_LABEL[nextStage]}</button>
              </div>
            ) : null}
            <div className="mt-5 space-y-2">{(order.fulfillment || []).map((item) => <div key={item.stage} className="flex flex-wrap justify-between gap-2 border-t border-[#02422C]/10 pt-3 text-xs"><span className="font-medium text-[#02422C]">{ORDER_STEPS.find(([key]) => key === item.stage)?.[1] || item.stage}</span><span className="text-neutral-600">{item.tracking_number || "Tanpa resi"} · {fmtDate(item.shipped_at || item.received_at)}</span></div>)}</div>
          </section>
        ) : null}

        {isManual && order.status === "delivered" ? <section className="rounded border border-[#02422C]/30 bg-[#F1F7F4] p-6" data-testid="active-delivered"><div className="flex items-start gap-4"><Check className="mt-1 h-6 w-6 shrink-0 text-[#02422C]" aria-hidden="true" /><div><h2 className="text-lg font-semibold text-[#02422C]">Order selesai</h2><p className="mt-2 text-sm text-neutral-600">Barang sudah ditandai diterima customer.</p></div></div></section> : null}
        {!isManual ? <section className="rounded border border-neutral-200 bg-white p-5"><h2 className="font-semibold text-[#02422C]">Order historis</h2><p className="mt-2 text-sm text-neutral-600">Order ini menggunakan lifecycle lama. Aksi yang tersedia tetap dibatasi oleh status pembayaran dan transisi backend.</p>{legacyNext ? <button type="button" disabled={busy} onClick={() => run(() => updateAdminOrderStatus(orderNumber, legacyNext), `Order dipindahkan ke ${legacyNext}.`, `Pindahkan order ke ${legacyNext}?`)} className="mt-4 h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50">Tandai {legacyNext}</button> : null}</section> : null}

        <div className="space-y-3">
          <Accordion icon={Package} title="Ringkasan item" subtitle={`${order.items?.length || 0} item · Total ${fmtMoney(order.grand_total, order.currency)}`} testId="order-items">
            <div className="divide-y divide-neutral-100">{(order.items || []).map((item) => <div key={item.sku} className="flex flex-wrap justify-between gap-3 py-3 text-sm"><div><p className="font-medium">{item.product_name}</p><p className="mt-1 text-xs text-neutral-500">{item.sku} · {item.quantity} × {fmtMoney(item.unit_price, order.currency)}</p></div><strong>{fmtMoney(item.line_total, order.currency)}</strong></div>)}</div>
            <div className="mt-4 space-y-2 border-t border-neutral-100 pt-3 text-sm"><div className="flex justify-between text-neutral-500"><span>Subtotal</span><span>{fmtMoney(order.subtotal, order.currency)}</span></div><div className="flex justify-between text-neutral-500"><span>Ongkir</span><span>{fmtMoney(order.shipping_amount, order.currency)}</span></div><div className="flex justify-between border-t border-neutral-100 pt-2 font-semibold"><span>Total</span><span>{fmtMoney(order.grand_total, order.currency)}</span></div></div>
          </Accordion>
          <Accordion icon={MapPin} title="Alamat customer" subtitle={`${address.recipient_name || "—"} · ${address.city || "—"}`} testId="order-address"><address className="text-sm not-italic leading-6 text-neutral-600">{address.recipient_name || "—"}<br />{address.phone || "—"}<br />{address.address_line_1 || "—"}<br />{address.city || "—"}{address.state_province ? `, ${address.state_province}` : ""} {address.postal_code || ""}<br />{address.country_code || "UZ"}</address></Accordion>
          <Accordion icon={FileText} title="Catatan aktivitas" subtitle={`${order.activity?.length || 0} aktivitas tercatat`} testId="order-activity"><div className="space-y-3">{(order.activity || []).length ? order.activity.map((entry, index) => <div key={`${entry.action}-${index}`} className="border-b border-neutral-100 pb-3 text-xs last:border-0"><p className="font-medium text-[#02422C]">{entry.action}</p><p className="mt-1 text-neutral-500">{fmtDate(entry.created_at)}</p></div>) : <p className="text-sm text-neutral-500">Belum ada catatan aktivitas.</p>}</div></Accordion>
        </div>
      </main>
    </div>
  );
}
