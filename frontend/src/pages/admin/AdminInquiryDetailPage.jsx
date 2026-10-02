import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, PackageCheck } from "lucide-react";
import { toast } from "sonner";
import { createAdminOrderFromInquiry, getAdminTelegramInquiry } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney } from "./adminUtils";
import { OrderProgress } from "./OrderProgress";
import { countOrderItemUnits, formatOrderItemOptions } from "./orderItemUtils";

const fieldClass = "h-11 w-full border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#02422C] focus:ring-1 focus:ring-[#02422C]";

export default function AdminInquiryDetailPage() {
  const { reference } = useParams();
  const navigate = useNavigate();
  const [form, setForm] = useState({ recipient: "", phone: "", email: "", address: "", city: "", shippingAmount: "0" });
  const { data: inquiry, isLoading } = useQuery({
    queryKey: ["admin-telegram-inquiry", reference],
    queryFn: () => getAdminTelegramInquiry(reference),
    refetchInterval: 10000,
  });

  useEffect(() => {
    if (inquiry?.order_number) navigate(`/orders/${inquiry.order_number}`, { replace: true });
  }, [inquiry, navigate]);

  const mutation = useMutation({
    mutationFn: () => createAdminOrderFromInquiry(reference, {
      guest_email: form.email || undefined,
      shipping_method: "manual",
      shipping_amount: Number(form.shippingAmount) || 0,
      shipping_address: {
        recipient_name: form.recipient.trim(),
        phone: form.phone.trim(),
        address_line_1: form.address.trim(),
        city: form.city.trim(),
        country_code: "UZ",
      },
    }, `manual-${reference}`),
    onSuccess: (order) => {
      toast.success("Order dibuat. Pilihan bank sedang dikirim ke Telegram.");
      navigate(`/orders/${order.order_number}`, { replace: true });
    },
    onError: (error) => toast.error(error?.response?.data?.detail?.error || "Order gagal dibuat."),
  });

  const update = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  if (isLoading) return <div data-testid="admin-inquiry-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  if (!inquiry) return <div className="py-12 text-sm text-neutral-500">Inquiry tidak ditemukan.</div>;
  if (!inquiry.order_number && !["sent", "unknown"].includes(inquiry.status)) {
    return (
      <div className="space-y-4 rounded border border-neutral-200 bg-white p-5" role="status">
        <h1 className="text-xl font-semibold text-[#02422C]">Menunggu pesan customer di Telegram</h1>
        <p className="text-sm text-neutral-600">Order belum dapat dibuat. Customer perlu mengirim pesan referensi dari keranjang terlebih dahulu. Halaman ini diperbarui otomatis.</p>
        <Link className="text-sm text-[#145A46] underline" to="/orders?stage=inquiry">Kembali ke workflow</Link>
      </div>
    );
  }

  const items = inquiry.snapshot?.items || [];
  const subtotal = Number(inquiry.subtotal) || 0;
  const unitCount = countOrderItemUnits(items);
  const shippingAmount = Number(form.shippingAmount) || 0;
  const grandTotal = subtotal + shippingAmount;

  return (
    <div className="mx-auto max-w-6xl" data-testid="admin-inquiry-detail">
      <Link to="/orders?stage=inquiry" className="inline-flex items-center gap-2 text-sm text-neutral-500 hover:text-neutral-900">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Kembali ke workflow
      </Link>
      <header className="mt-5">
        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Telegram inquiry</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">Buat order manual</h1>
        <p className="mt-2 text-sm text-neutral-600">{inquiry.customer?.name ? <>Customer: {inquiry.customer.name}{inquiry.customer.username ? ` (@${inquiry.customer.username})` : ""}. </> : null}Lengkapi data penerima dan ongkir. Setelah dibuat, customer menerima pilihan bank di Telegram.</p>
      </header>

      <OrderProgress currentStage="inquiry" className="mt-6 rounded border border-[#CD9B3A]/30 bg-[#FDF7E9] p-4" />

      <form
        className="mt-6 space-y-5"
        data-testid="inquiry-order-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (![form.recipient, form.phone, form.address, form.city].every((value) => value.trim())) {
            toast.error("Lengkapi nama, nomor telepon, alamat, dan kota penerima.");
            return;
          }
          mutation.mutate();
        }}
      >
        <div className="grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.8fr)]">
          <section className="rounded border border-neutral-200 bg-white" data-testid="inquiry-cart">
            <div className="border-b border-neutral-200 px-5 py-4">
              <h2 className="font-semibold text-[#02422C]">Item inquiry</h2>
              <p className="mt-1 text-xs text-neutral-500">{reference} · {fmtDate(inquiry.created_at)}</p>
            </div>
            <div className="divide-y divide-neutral-100">
              {items.map((item) => (
                <div key={item.sku} className="flex items-center justify-between gap-4 px-5 py-4">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-neutral-900">{item.name}</p>
                    {formatOrderItemOptions(item) ? <p className="mt-1 text-sm font-semibold text-[#02422C]" data-testid={`inquiry-item-options-${item.sku}`}>{formatOrderItemOptions(item)}</p> : null}
                    <p className="mt-1 text-xs text-neutral-500">SKU: {item.sku} · Jumlah: {item.quantity} unit · {fmtMoney(item.unit_price, inquiry.currency)} / unit</p>
                  </div>
                  <span className="shrink-0 text-sm font-semibold text-[#02422C]">{fmtMoney(item.line_total ?? item.unit_price ?? 0, inquiry.currency)}</span>
                </div>
              ))}
            </div>
          </section>

          <aside className="h-fit rounded border border-[#CD9B3A]/40 bg-[#FDF7E9] p-5" data-testid="inquiry-order-summary">
            <div className="flex items-center gap-2">
              <PackageCheck className="h-5 w-5 text-[#CD9B3A]" aria-hidden="true" />
              <h2 className="text-sm font-semibold text-[#02422C]">Ringkasan pembayaran</h2>
            </div>
            <div className="mt-4 space-y-3 text-sm">
              <div className="flex justify-between gap-3"><span className="text-neutral-600">{items.length} jenis produk · {unitCount} unit · Subtotal</span><span>{fmtMoney(subtotal, inquiry.currency)}</span></div>
              <div className="flex justify-between gap-3"><span className="text-neutral-600">Ongkir</span><span>{fmtMoney(shippingAmount, inquiry.currency)}</span></div>
              <div className="flex justify-between gap-3 border-t border-[#CD9B3A]/30 pt-3 font-semibold"><span>Total transfer</span><span className="text-[#02422C]">{fmtMoney(grandTotal, inquiry.currency)}</span></div>
            </div>
            <p className="mt-4 text-xs leading-5 text-neutral-600">Customer membayar satu kali. Stok belum dikurangi; order diteruskan ke supplier setelah admin mengonfirmasi pembayaran.</p>
          </aside>
        </div>

        <section className="rounded border border-neutral-200 bg-white p-5" data-testid="inquiry-customer-form">
          <div className="flex items-start justify-between gap-3">
            <div><h2 className="font-semibold text-[#02422C]">Data penerima dan pengiriman</h2><p className="mt-1 text-sm text-neutral-500">Kolom bertanda * wajib diisi.</p></div>
            <PackageCheck className="h-5 w-5 text-[#CD9B3A]" aria-hidden="true" />
          </div>
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <label className="space-y-1.5 text-xs font-medium text-neutral-700">Nama penerima *<input className={fieldClass} autoComplete="name" required value={form.recipient} onChange={(event) => update("recipient", event.target.value)} /></label>
            <label className="space-y-1.5 text-xs font-medium text-neutral-700">Nomor telepon *<input className={fieldClass} type="tel" autoComplete="tel" required value={form.phone} onChange={(event) => update("phone", event.target.value)} /></label>
            <label className="space-y-1.5 text-xs font-medium text-neutral-700">Email (opsional)<input className={fieldClass} type="email" autoComplete="email" value={form.email} onChange={(event) => update("email", event.target.value)} /></label>
            <label className="space-y-1.5 text-xs font-medium text-neutral-700">Ongkir (UZS)<input className={fieldClass} inputMode="numeric" value={form.shippingAmount} onChange={(event) => update("shippingAmount", event.target.value.replace(/[^0-9]/g, ""))} /></label>
            <label className="space-y-1.5 text-xs font-medium text-neutral-700 sm:col-span-2">Alamat lengkap *<input className={fieldClass} autoComplete="street-address" required value={form.address} onChange={(event) => update("address", event.target.value)} /></label>
            <label className="space-y-1.5 text-xs font-medium text-neutral-700">Kota *<input className={fieldClass} autoComplete="address-level2" required value={form.city} onChange={(event) => update("city", event.target.value)} /></label>
          </div>
        </section>

        <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-neutral-200 bg-white p-4">
          <Link to="/orders?stage=inquiry" className="inline-flex h-10 items-center gap-2 border border-neutral-300 px-4 text-sm font-semibold text-neutral-700">Kembali</Link>
          <button type="submit" disabled={mutation.isPending || items.length === 0} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-5 text-sm font-semibold text-white hover:bg-[#145A46] disabled:cursor-not-allowed disabled:opacity-50" data-testid="create-order-from-inquiry">
            {mutation.isPending ? "Membuat order…" : "Buat order & kirim pilihan bank"}
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </form>
    </div>
  );
}
