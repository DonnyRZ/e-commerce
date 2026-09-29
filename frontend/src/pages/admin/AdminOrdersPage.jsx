import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Archive, ArrowRight, RotateCcw, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { archiveAdminOrder, getAdminOrderWorkflow, permanentlyDeleteAdminOrder, permanentlyDeleteAdminTelegramInquiry, restoreAdminOrder } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney, StatusPill } from "./adminUtils";
import { ORDER_STEPS, OrderProgress, normalizeOrderStage } from "./OrderProgress";

const FILTERS = [...ORDER_STEPS, ["archived", "Diarsipkan"]];
const ACTION_LABELS = {
  review_inquiry: "Review inquiry",
  wait_payment: "Lihat pembayaran",
  verify_payment: "Periksa bukti pembayaran",
  supplier_ship: "Tandai supplier mengirim",
  receive_admin: "Tandai diterima admin",
  ship_customer: "Kirim ke customer",
  mark_delivered: "Tandai selesai",
  view_order: "Lihat detail",
  confirm_payment: "Konfirmasi pembayaran",
};

function progressStage(stage) {
  return normalizeOrderStage(stage);
}

function stageLabel(stage, evidenceCount = 0) {
  if (["pending_payment", "payment_review"].includes(stage) && evidenceCount > 0) return "Bukti tersimpan · siap dikonfirmasi";
  if (stage === "pending_payment") return "Menunggu transfer";
  if (stage === "payment_review") return "Menunggu konfirmasi admin";
  if (stage === "paid") return "Siap ke supplier";
  const currentStage = normalizeOrderStage(stage);
  return ORDER_STEPS.find(([key]) => key === currentStage)?.[1] || "Order lama";
}

function StepProgress({ current }) {
  return <OrderProgress currentStage={progressStage(current)} variant="compact" className="mt-4" />;
}

function WorkflowCard({ item, returnTo, workflowFilter }) {
  const queryClient = useQueryClient();
  const [busyAction, setBusyAction] = useState("");
  const isInquiry = item.kind === "inquiry";
  const title = isInquiry ? item.reference : item.order_number;
  const href = isInquiry ? `/orders/inquiry/${encodeURIComponent(item.reference)}` : `/orders/${item.order_number}`;
  const currentStatus = item.status || item.stage;
  const isPaymentStage = normalizeOrderStage(item.stage || currentStatus) === "payment";
  const currentStageLabel = item.archived_at
    ? "Diarsipkan"
    : stageLabel(isInquiry ? item.stage : currentStatus, item.evidence_count);
  const runOrderAction = async (action) => {
    if (busyAction) return;
    if (action === "archive" && !window.confirm("Arsipkan order ini? Order akan hilang dari tahapan aktif dan bisa dipulihkan dari filter Diarsipkan.")) return;
    if (action === "delete") {
      const description = isInquiry
        ? `Hapus permanen inquiry ${title} dari CMS? Snapshot keranjang akan dihapus, tetapi pesan Telegram yang sudah terkirim tidak ikut terhapus.`
        : `Hapus permanen order ${title}? Data pembayaran, bukti transfer, item, dan riwayat pengiriman akan dihapus. Tindakan ini tidak bisa dibatalkan.`;
      if (!window.confirm(description)) return;
      const confirmationLabel = isInquiry ? "referensi inquiry" : "nomor order";
      const typedIdentifier = window.prompt(`Ketik ${confirmationLabel} ini untuk melanjutkan: ${title}`);
      if (typedIdentifier !== title) {
        if (typedIdentifier !== null) toast.error("Referensi tidak cocok. Data tetap aman.");
        return;
      }
    }

    setBusyAction(action);
    try {
      if (action === "archive") await archiveAdminOrder(title);
      if (action === "restore") await restoreAdminOrder(title);
      if (action === "delete") {
        if (isInquiry) {
          await permanentlyDeleteAdminTelegramInquiry(title);
          queryClient.removeQueries({ queryKey: ["admin-telegram-inquiry", title] });
        } else {
          await permanentlyDeleteAdminOrder(title);
          queryClient.removeQueries({ queryKey: ["admin-order", title] });
        }
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["admin-order-workflow"] }),
        queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] }),
      ]);
      toast.success(action === "archive" ? "Order diarsipkan. Bisa dipulihkan dari filter Diarsipkan." : action === "restore" ? "Order dipulihkan ke tahap sebelumnya." : isInquiry ? "Inquiry dihapus permanen dari CMS." : "Order dihapus permanen.");
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const code = typeof detail === "string" ? detail : detail?.error;
      toast.error(code === "inquiry_already_converted"
        ? "Inquiry sudah menjadi order dan tidak dapat dihapus dari sini."
        : code === "inquiry_delivery_in_progress"
          ? "Pesan inquiry sedang diproses Telegram. Coba lagi sebentar."
          : code === "payment_notification_in_progress"
        ? "Pilihan pembayaran masih dikirim ke Telegram. Coba lagi sesaat."
        : "Aksi order gagal. Periksa koneksi lalu coba lagi.");
    } finally {
      setBusyAction("");
    }
  };
  return (
    <article className={`rounded border bg-white p-5 transition-shadow hover:shadow-sm ${item.next_action !== "wait_payment" && item.next_action !== "view_order" ? "border-[#CD9B3A]/50" : "border-neutral-200"}`} data-testid={`workflow-card-${title}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-semibold text-[#02422C]">{title}</h2><StatusPill value={currentStageLabel} tone={isPaymentStage ? "amber" : undefined} /></div>
          <p className="mt-1 text-sm text-neutral-700">{item.customer?.name || "Guest Telegram"}</p>
          <p className="mt-1 text-xs text-neutral-500">{item.customer?.city || "Telegram inquiry"} · {fmtDate(item.created_at)}</p>
        </div>
        <div className="text-right"><p className="text-lg font-semibold text-[#02422C]">{fmtMoney(item.grand_total ?? item.subtotal, item.currency)}</p><p className="mt-1 text-xs text-neutral-500">{item.item_count} item</p></div>
      </div>
      <StepProgress current={item.stage} />
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-4"><span className="text-xs text-neutral-500">{isInquiry ? "Keranjang menunggu dibuatkan order" : item.evidence_count > 0 && isPaymentStage ? "Bukti tersimpan · cocokkan mutasi rekening" : `Status: ${currentStageLabel}`}</span><div className="ml-auto flex flex-wrap items-center justify-end gap-2">{isInquiry ? <button type="button" onClick={() => runOrderAction("delete")} disabled={Boolean(busyAction)} className="inline-flex h-10 items-center gap-1.5 border border-red-200 px-3 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50" title="Hapus inquiry permanen" aria-label={`Hapus permanen inquiry ${title}`} data-testid={`delete-inquiry-${title}`}><Trash2 className="h-3.5 w-3.5" aria-hidden="true" />Hapus</button> : <>{item.archived_at ? <button type="button" onClick={() => runOrderAction("restore")} disabled={Boolean(busyAction)} className="inline-flex h-10 items-center gap-1.5 border border-[#02422C]/40 px-3 text-xs font-semibold text-[#02422C] hover:bg-[#F1F7F4] disabled:opacity-50" data-testid={`restore-order-${title}`}><RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />Pulihkan</button> : <button type="button" onClick={() => runOrderAction("archive")} disabled={Boolean(busyAction)} className="inline-flex h-10 items-center gap-1.5 border border-neutral-300 px-3 text-xs font-semibold text-neutral-700 hover:bg-neutral-50 disabled:opacity-50" data-testid={`archive-order-${title}`}><Archive className="h-3.5 w-3.5" aria-hidden="true" />Arsipkan</button>}<button type="button" onClick={() => runOrderAction("delete")} disabled={Boolean(busyAction)} className="inline-flex h-10 items-center gap-1.5 border border-red-200 px-3 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50" title="Hapus permanen" aria-label={`Hapus permanen order ${title}`} data-testid={`delete-order-${title}`}><Trash2 className="h-3.5 w-3.5" aria-hidden="true" />Hapus</button></>}<Link onClick={(event) => { if (busyAction) event.preventDefault(); }} aria-disabled={Boolean(busyAction)} to={href} state={{ returnTo, workflowFilter }} className={`inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white hover:bg-[#145A46] ${busyAction ? "pointer-events-none opacity-60" : ""}`}>{busyAction ? "Memproses…" : ACTION_LABELS[item.next_action] || "Lanjutkan"}<ArrowRight className="h-4 w-4" aria-hidden="true" /></Link></div></div>
    </article>
  );
}

export default function AdminOrdersPage() {
  const [params, setParams] = useSearchParams();
  const requestedFilter = params.get("stage") || "all";
  const filter = normalizeOrderStage(requestedFilter);
  const [q, setQ] = useState(params.get("q") || "");
  const page = Math.max(1, Number.parseInt(params.get("page") || "1", 10) || 1);
  const apiParams = { scope: filter === "actionable" ? "actionable" : "all", stage: !["all", "actionable"].includes(filter) ? filter : undefined, q: params.get("q") || undefined, page, page_size: 20 };
  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["admin-order-workflow", apiParams],
    queryFn: () => getAdminOrderWorkflow(apiParams),
    staleTime: 0,
    refetchOnMount: "always",
    refetchOnWindowFocus: true,
    refetchInterval: filter === "all" ? false : 30_000,
    refetchIntervalInBackground: false,
  });
  const items = data?.items || [];
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / (data?.page_size || 20)));
  const returnTo = `/orders${params.toString() ? `?${params.toString()}` : ""}`;
  useEffect(() => {
    if (!isLoading && data && page > totalPages) {
      const next = new URLSearchParams(params);
      next.set("page", String(totalPages));
      setParams(next, { replace: true });
    }
  }, [data, isLoading, page, params, setParams, totalPages]);
  const setFilter = (value) => { const next = new URLSearchParams(params); if (value === "all") next.delete("stage"); else next.set("stage", value); next.delete("page"); setParams(next); };
  const submitSearch = (event) => { event.preventDefault(); const next = new URLSearchParams(params); if (q.trim()) next.set("q", q.trim()); else next.delete("q"); next.delete("page"); setParams(next); };

  return (
    <div data-testid="admin-orders-page">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Sales</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">Order Workflow</h1><p className="mt-2 max-w-2xl text-sm text-neutral-500">Kelola pesanan dari inquiry sampai selesai. Customer membayar sekali; admin mencocokkan mutasi bank sebelum order diteruskan ke supplier.</p></div><div className="rounded-full bg-[#FDF7E9] px-4 py-2 text-xs text-[#02422C]" aria-live="polite">{isFetching ? "Memperbarui daftar…" : "Satu order, satu langkah aktif"}</div></div>
      <OrderProgress currentStage={null} className="mt-6 hidden rounded border border-[#CD9B3A]/30 bg-[#FDF7E9] p-4 lg:block" testId="workflow-overview" />
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div className="flex flex-wrap gap-2" role="group" aria-label="Filter tahap order">{FILTERS.map(([value, label]) => <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded-full px-4 py-2 text-xs font-semibold ${filter === value ? "bg-[#02422C] text-white" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"}`} aria-pressed={filter === value}>{label}{data?.counts?.[value] !== undefined ? <span className="ml-2 opacity-70">{data.counts[value]}</span> : null}</button>)}</div><form className="relative shrink-0" onSubmit={submitSearch}><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari order atau inquiry" className="h-10 w-full border border-neutral-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-[#02422C] lg:w-64" data-testid="orders-search" /></form></div>
      {filter === "payment" ? <p className="mt-3 rounded border border-[#CD9B3A]/30 bg-[#FDF7E9] px-4 py-3 text-xs text-[#02422C]" data-testid="payment-workflow-hint">Satu transfer per order. Bukti disimpan untuk audit; admin mengonfirmasi setelah cocok dengan mutasi rekening.</p> : null}
      <div className="mt-5 space-y-4">{isLoading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44 w-full" />) : null}{!isLoading && !items.length ? <div className="rounded border border-dashed border-neutral-300 bg-white p-12 text-center text-sm text-neutral-500" data-testid="orders-empty">Tidak ada item pada tahap ini.</div> : null}{!isLoading ? items.map((item) => <WorkflowCard key={item.kind === "inquiry" ? item.reference : item.order_number} item={item} returnTo={returnTo} workflowFilter={filter} />) : null}</div>
      <div className="mt-5 flex items-center justify-between text-sm"><span className="text-neutral-500" data-testid="orders-total">{data?.total || 0} item</span><div className="flex items-center gap-2"><button type="button" disabled={page <= 1} onClick={() => { const next = new URLSearchParams(params); next.set("page", String(page - 1)); setParams(next); }} className="h-9 border border-neutral-300 px-3 text-xs disabled:opacity-40">Sebelumnya</button><span className="text-xs text-neutral-500">{page} / {totalPages}</span><button type="button" disabled={page >= totalPages} onClick={() => { const next = new URLSearchParams(params); next.set("page", String(page + 1)); setParams(next); }} className="h-9 border border-neutral-300 px-3 text-xs disabled:opacity-40">Berikutnya</button></div></div>
    </div>
  );
}
