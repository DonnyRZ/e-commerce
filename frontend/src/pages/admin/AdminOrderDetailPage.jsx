import { useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, CheckCircle2, Clock3, XCircle } from "lucide-react";
import { toast } from "sonner";
import {
  confirmAdminPayment,
  getAdminOrder,
  rejectAdminPayment,
  updateAdminOrderStatus,
  updateAdminFulfillment,
  uploadAdminPaymentEvidence,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

const STAGES = [
  ["supplier_shipping", "Barang dikirim supplier"],
  ["received_by_admin", "Diterima admin"],
  ["customer_shipping", "Dikirim ke customer"],
  ["delivered", "Diterima customer"],
];
const NEXT_STAGE = { paid: "supplier_shipping", supplier_shipping: "received_by_admin", received_by_admin: "customer_shipping", customer_shipping: "delivered" };
const NEXT_LABEL = { supplier_shipping: "Tandai supplier sudah mengirim", received_by_admin: "Tandai barang diterima admin", customer_shipping: "Kirim ke customer", delivered: "Tandai selesai" };
const LEGACY_NEXT = { paid: "processing", processing: "shipped", shipped: "delivered" };

export default function AdminOrderDetailPage() {
  const { orderNumber } = useParams();
  const queryClient = useQueryClient();
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [selectedEvidence, setSelectedEvidence] = useState(null);
  const [carrier, setCarrier] = useState("");
  const [tracking, setTracking] = useState("");
  const [note, setNote] = useState("");
  const { data: order, isLoading } = useQuery({ queryKey: ["admin-order", orderNumber], queryFn: () => getAdminOrder(orderNumber) });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-order", orderNumber] });
    queryClient.invalidateQueries({ queryKey: ["admin-orders"] });
    queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
  };
  const run = async (action, success) => {
    setBusy(true);
    try { await action(); toast.success(success); refresh(); } catch (error) {
      const detail = error?.response?.data?.detail;
      const code = typeof detail === "string" ? detail : detail?.error;
      const messages = { payment_evidence_required: "Upload bukti transfer terlebih dahulu.", insufficient_stock: "Stok tidak mencukupi.", payment_not_eligible: "Pembayaran belum dikonfirmasi.", invalid_fulfillment_transition: "Order belum dapat masuk ke tahap ini." };
      toast.error(messages[code] || "Perubahan order gagal.");
    } finally { setBusy(false); }
  };
  if (isLoading) return <div data-testid="admin-order-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  if (!order) return <p className="text-sm text-neutral-500" data-testid="admin-order-missing">Order not found.</p>;

  const manual = order.order_source === "telegram_manual";
  const nextStage = NEXT_STAGE[order.status];
  const legacyNext = LEGACY_NEXT[order.status];
  const addr = order.shipping_address || {};
  const payment = order.payment;
  const latestEvidence = payment?.evidence?.[0];
  const reachedIndex = ["paid", "supplier_shipping", "received_by_admin", "customer_shipping", "delivered"].indexOf(order.status);

  return (
    <div data-testid="admin-order-detail">
      <Link to="/orders" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to orders</Link>
      <div className="mt-3 flex flex-wrap items-start justify-between gap-4">
        <div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Order lifecycle</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]" data-testid="order-number">{order.order_number}</h1><p className="mt-1 text-xs text-neutral-500">{fmtDate(order.created_at)} · {order.email || "guest Telegram"}</p></div>
        <div className="flex flex-wrap items-center gap-2"><StatusPill value={order.status} /><StatusPill value={order.payment_state} />{!manual && legacyNext ? <button disabled={busy} onClick={() => run(() => updateAdminOrderStatus(orderNumber, legacyNext), `Order moved to ${legacyNext}.`)} className="h-10 bg-[#145A46] px-4 text-sm font-semibold text-white disabled:opacity-50">Mark as {legacyNext}</button> : null}</div>
      </div>

      {manual ? <section className="mt-6 border border-[#CD9B3A]/40 bg-[#FDF7E9] p-5" data-testid="order-timeline"><h2 className="text-sm font-semibold text-[#02422C]">Progress pengiriman</h2><div className="mt-5 grid gap-3 md:grid-cols-4">{["paid", ...STAGES.map(([key]) => key)].map((stage, index) => { const reached = reachedIndex >= index; const label = stage === "paid" ? "Pembayaran dikonfirmasi" : STAGES.find(([key]) => key === stage)?.[1]; return <div key={stage} className={`flex items-start gap-2 text-xs ${reached ? "text-[#02422C]" : "text-neutral-400"}`}><span className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full ${reached ? "bg-[#02422C] text-white" : "bg-white"}`}>{reached ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Clock3 className="h-3.5 w-3.5" />}</span><span>{label}</span></div>; })}</div></section> : null}

      <div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_1fr]">
        <div className="space-y-6">
          <section className="border border-neutral-200 bg-white" data-testid="order-items"><h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">Items</h2><div className="divide-y divide-neutral-100">{(order.items || []).map((item) => <div key={item.sku} className="flex gap-3 px-5 py-4 text-sm"><div className="min-w-0 flex-1"><p className="font-medium">{item.product_name}</p><p className="mt-1 text-xs text-neutral-400">{item.sku} · {item.quantity} × {fmtMoney(item.unit_price, order.currency)}</p></div><span className="font-semibold">{fmtMoney(item.line_total, order.currency)}</span></div>)}</div><div className="space-y-2 px-5 py-4 text-sm"><div className="flex justify-between text-neutral-500"><span>Subtotal</span><span>{fmtMoney(order.subtotal, order.currency)}</span></div><div className="flex justify-between text-neutral-500"><span>Shipping</span><span>{fmtMoney(order.shipping_amount, order.currency)}</span></div><div className="flex justify-between border-t border-neutral-100 pt-2 text-base font-semibold"><span>Total</span><span>{fmtMoney(order.grand_total, order.currency)}</span></div></div></section>
          {manual ? <section className="border border-neutral-200 bg-white p-5" data-testid="manual-fulfillment"><div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-semibold">Fulfillment</h2><p className="mt-1 text-xs text-neutral-500">Supplier → admin → customer. Tracking bersifat opsional.</p></div></div>{nextStage ? <div className="mt-4 grid gap-3 sm:grid-cols-2"><input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Carrier (opsional)" value={carrier} onChange={(e) => setCarrier(e.target.value)} /><input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Nomor resi (opsional)" value={tracking} onChange={(e) => setTracking(e.target.value)} /><input className="h-10 border border-neutral-300 px-3 text-sm sm:col-span-2" placeholder="Catatan internal (opsional)" value={note} onChange={(e) => setNote(e.target.value)} /><button disabled={busy} onClick={() => run(() => updateAdminFulfillment(orderNumber, { stage: nextStage, carrier: carrier || undefined, tracking_number: tracking || undefined, note: note || undefined }), NEXT_LABEL[nextStage])} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50">{busy ? "Menyimpan…" : NEXT_LABEL[nextStage]}</button></div> : <p className="mt-4 text-sm text-neutral-500">Lifecycle fulfillment selesai.</p>}<div className="mt-5 space-y-2">{(order.fulfillment || []).map((stage) => <div key={stage.stage} className="flex flex-wrap justify-between gap-2 border-t border-neutral-100 pt-3 text-xs"><span className="font-medium text-[#02422C]">{STAGES.find(([key]) => key === stage.stage)?.[1] || stage.stage}</span><span className="text-neutral-500">{stage.tracking_number || "Tanpa resi"} · {fmtDate(stage.shipped_at || stage.received_at)}</span></div>)}</div></section> : null}
        </div>
        <div className="space-y-6">
          <section className="border border-neutral-200 bg-white p-5" data-testid="order-shipping"><h2 className="text-sm font-semibold">Shipping address</h2><address className="mt-3 text-sm not-italic leading-6 text-neutral-600">{addr.recipient_name}<br />{addr.phone}<br />{addr.address_line_1}<br />{addr.city}{addr.state_province ? `, ${addr.state_province}` : ""} {addr.postal_code}<br />{addr.country_code}</address></section>
          <section className="border border-neutral-200 bg-white p-5" data-testid="order-payment"><div className="flex items-start justify-between gap-3"><div><h2 className="text-sm font-semibold">Pembayaran manual</h2><p className="mt-1 text-xs text-neutral-500">{payment ? fmtMoney(payment.amount, order.currency) : "Tidak ada payment record"}</p></div>{payment ? <StatusPill value={payment.status} /> : null}</div>{payment ? <><div className="mt-4 space-y-2 text-xs text-neutral-500"><p>Reference: <span className="font-mono text-neutral-700">{payment.merchant_trans_id}</span></p>{payment.review_note ? <p className="border-l-2 border-[#CD9B3A] pl-3">{payment.review_note}</p> : null}</div><div className="mt-4 rounded border border-dashed border-neutral-300 p-3">{latestEvidence ? <div className="space-y-3"><div className="flex items-center justify-between gap-3 text-sm"><span className="truncate">{latestEvidence.original_filename}</span><a className="font-semibold text-[#145A46] hover:underline" href={latestEvidence.download_url} target="_blank" rel="noreferrer">Lihat / unduh</a></div>{latestEvidence.mime_type?.startsWith("image/") ? <img src={latestEvidence.download_url} alt="Preview bukti transfer" className="max-h-56 w-full rounded border border-neutral-200 object-contain" /> : <p className="text-xs text-neutral-500">Dokumen PDF siap dibuka melalui tombol di atas.</p>}<p className="text-[11px] text-neutral-400">{latestEvidence.mime_type} · {(latestEvidence.file_size / 1024).toFixed(0)} KB</p></div> : <p className="text-xs text-neutral-500">Belum ada bukti transfer.</p>}<input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="mt-3 block w-full text-xs" onChange={(e) => { const file = e.target.files?.[0]; if (file) { setSelectedEvidence(file); run(() => uploadAdminPaymentEvidence(orderNumber, file), "Bukti transfer diunggah."); } }} disabled={busy} />{selectedEvidence ? <p className="mt-2 text-xs text-neutral-600">Dipilih: {selectedEvidence.name} · {(selectedEvidence.size / 1024).toFixed(0)} KB</p> : null}<p className="mt-2 text-[11px] text-neutral-400">JPG, PNG, WebP, atau PDF. Maksimal 8 MB.</p></div>{payment.status === "pending_review" ? <><textarea className="mt-3 min-h-20 w-full border border-neutral-300 p-3 text-sm" placeholder="Alasan penolakan (wajib jika menolak)" value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} /><div className="mt-3 flex flex-wrap gap-2"><button disabled={busy} onClick={() => run(() => confirmAdminPayment(orderNumber), "Pembayaran dikonfirmasi dan stok dikunci.")} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-50"><CheckCircle2 className="h-4 w-4" /> Konfirmasi pembayaran</button><button disabled={busy || rejectReason.length < 3} onClick={() => run(() => rejectAdminPayment(orderNumber, rejectReason), "Bukti ditolak dan menunggu pengganti.")} className="inline-flex h-10 items-center gap-2 border border-red-200 px-4 text-sm font-semibold text-red-700 disabled:opacity-40"><XCircle className="h-4 w-4" /> Tolak</button></div></> : null}</> : null}</section>
        </div>
      </div>
    </div>
  );
}
