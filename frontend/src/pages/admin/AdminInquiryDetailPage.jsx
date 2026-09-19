import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, CheckCircle2, Circle, PackageCheck } from "lucide-react";
import { toast } from "sonner";
import { createAdminOrderFromInquiry, getAdminTelegramInquiry } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney } from "./adminUtils";

const STEPS = ["Inquiry", "Data customer", "Pengiriman", "Konfirmasi"];

export default function AdminInquiryDetailPage() {
  const { reference } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ recipient: "", phone: "", email: "", address: "", city: "", shippingAmount: "0" });
  const { data: inquiry, isLoading } = useQuery({ queryKey: ["admin-telegram-inquiry", reference], queryFn: () => getAdminTelegramInquiry(reference) });
  useEffect(() => {
    if (inquiry?.order_number) navigate(`/orders/${inquiry.order_number}`, { replace: true });
  }, [inquiry, navigate]);
  const mutation = useMutation({
    mutationFn: () => createAdminOrderFromInquiry(reference, {
      guest_email: form.email || undefined,
      shipping_method: "manual",
      shipping_amount: Number(form.shippingAmount) || 0,
      shipping_address: { recipient_name: form.recipient, phone: form.phone, address_line_1: form.address, city: form.city, country_code: "UZ" },
    }, `manual-${reference}`),
    onSuccess: (order) => { toast.success("Order dibuat."); navigate(`/orders/${order.order_number}`); },
    onError: (error) => toast.error(error?.response?.data?.detail?.error || "Order gagal dibuat."),
  });
  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  if (isLoading) return <div data-testid="admin-inquiry-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  if (!inquiry) return <div className="py-12 text-sm text-neutral-500">Inquiry tidak ditemukan.</div>;
  const items = inquiry.snapshot?.items || [];

  return (
    <div data-testid="admin-inquiry-detail">
      <Link to="/orders?stage=inquiry" className="inline-flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900"><ArrowLeft className="h-4 w-4" aria-hidden="true" /> Kembali ke workflow</Link>
      <div className="mt-5"><p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Telegram inquiry</p><h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">Buat order manual</h1><p className="mt-2 text-sm text-neutral-500">Order dibuat manual dan belum mengurangi stok sampai pembayaran dikonfirmasi.</p></div>
      <div className="mt-6 grid gap-3 sm:grid-cols-4">{STEPS.map((step, index) => <div key={step} className={`flex items-center gap-2 border-b-2 pb-3 text-sm ${index === 0 ? "border-[#02422C] font-semibold text-[#02422C]" : "border-neutral-200 text-neutral-400"}`}><span className={`flex h-7 w-7 items-center justify-center rounded-full ${index === 0 ? "bg-[#02422C] text-white" : "border border-neutral-300 bg-white"}`}>{index === 0 ? <CheckCircle2 className="h-4 w-4" aria-hidden="true" /> : <Circle className="h-4 w-4" aria-hidden="true" />}</span>{step}</div>)}</div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[1.5fr_0.8fr]">
        <section className="rounded border border-neutral-200 bg-white" data-testid="inquiry-cart"><div className="border-b border-neutral-200 px-5 py-4"><h2 className="font-semibold text-[#02422C]">Keranjang inquiry</h2><p className="mt-1 text-xs text-neutral-500">{reference} · {fmtDate(inquiry.created_at)}</p></div><div className="divide-y divide-neutral-100">{items.map((item) => <div key={item.sku} className="flex items-center justify-between gap-4 px-5 py-4"><div className="min-w-0"><p className="truncate text-sm font-medium">{item.name}</p><p className="mt-1 text-xs text-neutral-500">{item.sku} · qty {item.quantity}</p></div><span className="text-sm font-semibold text-[#02422C]">{fmtMoney(item.line_total || item.unit_price || 0, inquiry.currency)}</span></div>)}</div></section>
        <aside className="h-fit rounded border border-[#CD9B3A]/40 bg-[#FDF7E9] p-5"><p className="text-sm font-semibold text-[#02422C]">Ringkasan order</p><div className="mt-4 space-y-2 text-sm"><div className="flex justify-between"><span className="text-neutral-600">Jumlah item</span><span>{inquiry.item_count}</span></div><div className="flex justify-between"><span className="text-neutral-600">Subtotal</span><span>{fmtMoney(inquiry.subtotal, inquiry.currency)}</span></div><div className="flex justify-between border-t border-[#CD9B3A]/30 pt-3 font-semibold"><span>Total sementara</span><span className="text-[#02422C]">{fmtMoney(inquiry.subtotal, inquiry.currency)}</span></div></div><p className="mt-4 text-xs leading-5 text-neutral-600">Stok belum dikurangi. Stok baru dikunci setelah pembayaran dikonfirmasi.</p></aside>
      </div>
      <section className="mt-6 rounded border border-neutral-200 bg-white p-5" data-testid="inquiry-customer-form"><div className="flex items-start justify-between gap-3"><div><h2 className="font-semibold text-[#02422C]">Data customer dan pengiriman</h2><p className="mt-1 text-xs text-neutral-500">Lengkapi data sebelum membuat order.</p></div><PackageCheck className="h-5 w-5 text-[#CD9B3A]" aria-hidden="true" /></div><div className="mt-5 grid gap-3 md:grid-cols-2"><input className="h-11 border border-neutral-300 px-3 text-sm" placeholder="Nama penerima *" value={form.recipient} onChange={(e) => update("recipient", e.target.value)} /><input className="h-11 border border-neutral-300 px-3 text-sm" placeholder="Nomor telepon *" value={form.phone} onChange={(e) => update("phone", e.target.value)} /><input className="h-11 border border-neutral-300 px-3 text-sm" placeholder="Email (opsional)" value={form.email} onChange={(e) => update("email", e.target.value)} /><input className="h-11 border border-neutral-300 px-3 text-sm" placeholder="Ongkir UZS" inputMode="numeric" value={form.shippingAmount} onChange={(e) => update("shippingAmount", e.target.value.replace(/[^0-9]/g, ""))} /><input className="h-11 border border-neutral-300 px-3 text-sm md:col-span-2" placeholder="Alamat lengkap *" value={form.address} onChange={(e) => update("address", e.target.value)} /><input className="h-11 border border-neutral-300 px-3 text-sm" placeholder="Kota *" value={form.city} onChange={(e) => update("city", e.target.value)} /></div></section>
      <div className="mt-6 flex flex-wrap items-center justify-between gap-3 rounded border border-neutral-200 bg-white p-4"><Link to="/orders?stage=inquiry" className="inline-flex h-10 items-center gap-2 border border-neutral-300 px-4 text-sm font-semibold">Kembali</Link><button type="button" disabled={mutation.isPending || !form.recipient || !form.phone || !form.address || !form.city} onClick={() => mutation.mutate()} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-5 text-sm font-semibold text-white disabled:opacity-40">{mutation.isPending ? "Membuat order…" : "Buat order menunggu pembayaran"}<ArrowRight className="h-4 w-4" aria-hidden="true" /></button></div>
    </div>
  );
}
