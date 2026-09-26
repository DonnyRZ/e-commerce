import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageCircle, PackageCheck } from "lucide-react";
import { toast } from "sonner";
import { createAdminOrderFromInquiry, getAdminTelegramInquiries } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney } from "./adminUtils";

function CreateOrderForm({ inquiry, onDone }) {
  const [email, setEmail] = useState("");
  const [recipient, setRecipient] = useState("");
  const [phone, setPhone] = useState("");
  const [address, setAddress] = useState("");
  const [city, setCity] = useState("");
  const [shippingAmount, setShippingAmount] = useState("0");
  const mutation = useMutation({
    mutationFn: () => createAdminOrderFromInquiry(inquiry.reference, {
      guest_email: email || undefined,
      shipping_method: "manual",
      shipping_amount: Number(shippingAmount) || 0,
      shipping_address: {
        recipient_name: recipient,
        phone,
        address_line_1: address,
        city,
        country_code: "UZ",
      },
    }, `manual-${inquiry.reference}`),
    onSuccess: onDone,
    onError: (error) => toast.error(error?.response?.data?.detail?.error || "Order gagal dibuat."),
  });
  return (
    <div className="mt-4 grid gap-3 border-t border-neutral-200 pt-4 lg:grid-cols-2">
      <input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Nama penerima" value={recipient} onChange={(e) => setRecipient(e.target.value)} />
      <input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Nomor telepon" value={phone} onChange={(e) => setPhone(e.target.value)} />
      <input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Email (opsional)" value={email} onChange={(e) => setEmail(e.target.value)} />
      <input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Ongkir UZS" inputMode="numeric" value={shippingAmount} onChange={(e) => setShippingAmount(e.target.value.replace(/[^0-9]/g, ""))} />
      <input className="h-10 border border-neutral-300 px-3 text-sm lg:col-span-2" placeholder="Alamat lengkap" value={address} onChange={(e) => setAddress(e.target.value)} />
      <input className="h-10 border border-neutral-300 px-3 text-sm" placeholder="Kota" value={city} onChange={(e) => setCity(e.target.value)} />
      <button type="button" disabled={!recipient || !phone || !address || mutation.isPending} onClick={() => mutation.mutate()} className="h-10 bg-[#02422C] px-4 text-sm font-semibold text-white disabled:opacity-40">
        {mutation.isPending ? "Membuat order…" : "Buat order menunggu pembayaran"}
      </button>
    </div>
  );
}

export default function AdminTelegramInquiriesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(null);
  const { data, isLoading } = useQuery({
    queryKey: ["admin-telegram-inquiries"],
    queryFn: () => getAdminTelegramInquiries(),
  });
  const items = data?.items || [];

  return (
    <div data-testid="admin-telegram-inquiries-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Sales</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-[#02422C]">Telegram inquiries</h1>
          <p className="mt-2 max-w-2xl text-sm text-neutral-500">Review the customer’s cart, complete shipping details, then create a manual-transfer order.</p>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-[#FDF7E9] px-4 py-2 text-xs text-[#02422C]"><MessageCircle className="h-4 w-4" /> Cart inquiry, not checkout</div>
      </div>
      <div className="mt-6 space-y-4">
        {isLoading ? <Skeleton className="h-48 w-full" /> : null}
        {!isLoading && !items.length ? <div className="border border-dashed border-neutral-300 bg-white p-10 text-center text-sm text-neutral-500">Belum ada inquiry Telegram.</div> : null}
        {items.map((inquiry) => {
          const canCreate = !inquiry.order_id && inquiry.snapshot && ["sent", "unknown"].includes(inquiry.status);
          return (
            <article key={inquiry.reference} className="border border-neutral-200 bg-white p-5" data-testid={`telegram-inquiry-${inquiry.reference}`}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2"><h2 className="font-semibold text-[#02422C]">{inquiry.reference}</h2><span className="rounded-full bg-neutral-100 px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-neutral-500">{inquiry.status}</span></div>
                  <p className="mt-1 text-xs text-neutral-500">{fmtDate(inquiry.created_at)} · {inquiry.item_count} item · {fmtMoney(inquiry.subtotal, inquiry.currency)}</p>
                </div>
                {inquiry.order_number ? <Link to={`/orders/${inquiry.order_number}`} className="text-sm font-semibold text-[#145A46] hover:underline">Open order</Link> : null}
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {(inquiry.snapshot?.items || []).map((item) => <div key={`${inquiry.reference}-${item.sku}`} className="rounded border border-neutral-100 bg-neutral-50 p-3 text-sm"><p className="font-medium">{item.name}</p><p className="mt-1 text-xs text-neutral-500">{item.sku} · qty {item.quantity}</p></div>)}
              </div>
              {canCreate ? (
                open === inquiry.reference ? <CreateOrderForm inquiry={inquiry} onDone={(order) => { toast.success("Order dibuat."); queryClient.invalidateQueries({ queryKey: ["admin-telegram-inquiries"] }); navigate(`/orders/${order.order_number}`); }} /> : <button type="button" onClick={() => setOpen(inquiry.reference)} className="mt-4 inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white"><PackageCheck className="h-4 w-4" /> Create order</button>
              ) : null}
            </article>
          );
        })}
      </div>
    </div>
  );
}
