import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Check, Circle, Search, Truck } from "lucide-react";
import { getAdminOrderWorkflow } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney, StatusPill } from "./adminUtils";

const STEPS = [
  ["inquiry", "Inquiry"],
  ["pending_payment", "Menunggu pembayaran"],
  ["payment_review", "Pembayaran diverifikasi"],
  ["supplier_shipping", "Supplier mengirim"],
  ["received_by_admin", "Diterima admin"],
  ["customer_shipping", "Dikirim ke customer"],
  ["delivered", "Selesai"],
];

const FILTERS = [["all", "Semua"], ["actionable", "Perlu tindakan"], ...STEPS];
const ACTION_LABELS = {
  review_inquiry: "Review inquiry",
  wait_payment: "Lihat order",
  verify_payment: "Verifikasi pembayaran",
  supplier_ship: "Tandai supplier mengirim",
  receive_admin: "Tandai diterima admin",
  ship_customer: "Kirim ke customer",
  mark_delivered: "Tandai selesai",
  view_order: "Lihat detail",
};

function StepProgress({ current }) {
  const index = Math.max(0, STEPS.findIndex(([key]) => key === current));
  return (
    <div className="mt-4 flex items-center gap-1 overflow-hidden" aria-label="Order progress">
      {STEPS.map(([key, label], stepIndex) => {
        const complete = stepIndex < index;
        const active = stepIndex === index;
        return (
          <div key={key} className="flex min-w-0 flex-1 items-center gap-1">
            <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${complete || active ? "border-[#02422C] bg-[#02422C] text-white" : "border-neutral-300 bg-white text-neutral-300"}`} title={label}>
              {complete ? <Check className="h-3 w-3" aria-hidden="true" /> : active ? <Circle className="h-2.5 w-2.5 fill-current" aria-hidden="true" /> : <span className="h-1.5 w-1.5 rounded-full bg-current" />}
            </span>
            <span className={`hidden truncate text-[11px] sm:block ${active ? "font-semibold text-[#02422C]" : complete ? "text-neutral-600" : "text-neutral-400"}`}>{label}</span>
            {stepIndex < STEPS.length - 1 ? <span className={`h-px min-w-2 flex-1 ${complete ? "bg-[#02422C]" : "bg-neutral-200"}`} /> : null}
          </div>
        );
      })}
    </div>
  );
}

function WorkflowCard({ item }) {
  const isInquiry = item.kind === "inquiry";
  const title = isInquiry ? item.reference : item.order_number;
  const href = isInquiry ? `/orders/inquiry/${encodeURIComponent(item.reference)}` : `/orders/${item.order_number}`;
  const stageLabel = STEPS.find(([key]) => key === item.stage)?.[1] || "Order lama";
  return (
    <article className={`rounded border bg-white p-5 transition-shadow hover:shadow-sm ${item.next_action !== "wait_payment" && item.next_action !== "view_order" ? "border-[#CD9B3A]/50" : "border-neutral-200"}`} data-testid={`workflow-card-${title}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2"><h2 className="truncate font-semibold text-[#02422C]">{title}</h2><StatusPill value={stageLabel} /></div>
          <p className="mt-1 text-sm text-neutral-700">{item.customer?.name || "Guest Telegram"}</p>
          <p className="mt-1 text-xs text-neutral-500">{item.customer?.city || "Telegram inquiry"} · {fmtDate(item.created_at)}</p>
        </div>
        <div className="text-right"><p className="text-lg font-semibold text-[#02422C]">{fmtMoney(item.grand_total ?? item.subtotal, item.currency)}</p><p className="mt-1 text-xs text-neutral-500">{item.item_count} item</p></div>
      </div>
      <StepProgress current={item.stage} />
      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-neutral-100 pt-4"><span className="text-xs text-neutral-500">{isInquiry ? "Keranjang menunggu dibuatkan order" : `Status: ${stageLabel}`}</span><Link to={href} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white hover:bg-[#145A46]">{ACTION_LABELS[item.next_action] || "Lanjutkan"}<ArrowRight className="h-4 w-4" aria-hidden="true" /></Link></div>
    </article>
  );
}

export default function AdminOrdersPage() {
  const [params, setParams] = useSearchParams();
  const filter = params.get("stage") || "all";
  const [q, setQ] = useState(params.get("q") || "");
  const page = parseInt(params.get("page") || "1", 10);
  const apiParams = { scope: filter === "actionable" ? "actionable" : "all", stage: !["all", "actionable"].includes(filter) ? filter : undefined, q: params.get("q") || undefined, page, page_size: 20 };
  const { data, isLoading } = useQuery({ queryKey: ["admin-order-workflow", apiParams], queryFn: () => getAdminOrderWorkflow(apiParams) });
  const items = data?.items || [];
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / (data?.page_size || 20)));
  const setFilter = (value) => { const next = new URLSearchParams(params); if (value === "all") next.delete("stage"); else next.set("stage", value); next.delete("page"); setParams(next); };
  const submitSearch = (event) => { event.preventDefault(); const next = new URLSearchParams(params); if (q.trim()) next.set("q", q.trim()); else next.delete("q"); next.delete("page"); setParams(next); };

  return (
    <div data-testid="admin-orders-page">
      <div className="flex flex-wrap items-start justify-between gap-4"><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Sales</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">Order Workflow</h1><p className="mt-2 max-w-2xl text-sm text-neutral-500">Kelola pesanan dengan mudah, dari inquiry sampai selesai.</p></div><div className="rounded-full bg-[#FDF7E9] px-4 py-2 text-xs text-[#02422C]">Satu order, satu langkah aktif</div></div>
      <div className="mt-6 hidden items-start gap-2 overflow-x-auto rounded border border-[#CD9B3A]/30 bg-[#FDF7E9] p-4 lg:flex">{STEPS.map(([key, label], index) => <div key={key} className="flex min-w-[110px] flex-1 items-center gap-2 text-center text-xs text-[#02422C]"><span className="mx-auto flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white text-[#02422C]">{index === 0 ? <Truck className="h-4 w-4" aria-hidden="true" /> : index + 1}</span><span className="text-left leading-tight">{label}</span>{index < STEPS.length - 1 ? <span className="h-px min-w-4 flex-1 bg-[#CD9B3A]/50" /> : null}</div>)}</div>
      <div className="mt-6 flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between"><div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter order workflow">{FILTERS.map(([value, label]) => <button key={value} type="button" onClick={() => setFilter(value)} className={`rounded-full px-4 py-2 text-xs font-semibold ${filter === value ? "bg-[#02422C] text-white" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"}`} aria-selected={filter === value}>{label}{value !== "all" && data?.counts?.[value] !== undefined ? <span className="ml-2 opacity-70">{data.counts[value]}</span> : null}</button>)}</div><form className="relative shrink-0" onSubmit={submitSearch}><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cari order atau inquiry" className="h-10 w-full border border-neutral-300 bg-white pl-9 pr-3 text-sm outline-none focus:border-[#02422C] lg:w-64" data-testid="orders-search" /></form></div>
      <div className="mt-5 space-y-4">{isLoading ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-44 w-full" />) : null}{!isLoading && !items.length ? <div className="rounded border border-dashed border-neutral-300 bg-white p-12 text-center text-sm text-neutral-500" data-testid="orders-empty">Tidak ada item pada tahap ini.</div> : null}{!isLoading ? items.map((item) => <WorkflowCard key={item.kind === "inquiry" ? item.reference : item.order_number} item={item} />) : null}</div>
      <div className="mt-5 flex items-center justify-between text-sm"><span className="text-neutral-500" data-testid="orders-total">{data?.total || 0} item</span><div className="flex items-center gap-2"><button type="button" disabled={page <= 1} onClick={() => { const next = new URLSearchParams(params); next.set("page", String(page - 1)); setParams(next); }} className="h-9 border border-neutral-300 px-3 text-xs disabled:opacity-40">Sebelumnya</button><span className="text-xs text-neutral-500">{page} / {totalPages}</span><button type="button" disabled={page >= totalPages} onClick={() => { const next = new URLSearchParams(params); next.set("page", String(page + 1)); setParams(next); }} className="h-9 border border-neutral-300 px-3 text-xs disabled:opacity-40">Berikutnya</button></div></div>
    </div>
  );
}
