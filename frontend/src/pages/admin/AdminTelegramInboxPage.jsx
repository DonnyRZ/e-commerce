import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  ArrowLeft,
  Check,
  CheckCircle2,
  ImagePlus,
  LoaderCircle,
  MessageCircle,
  PackageSearch,
  Paperclip,
  Search,
  Send,
  ShieldAlert,
  ShoppingBag,
  X,
} from "lucide-react";
import { toast } from "sonner";
import {
  createAdminTelegramOrder,
  getAdminTelegramConversation,
  getAdminTelegramInbox,
  reviewAdminTelegramCandidate,
  searchAdminTelegramProducts,
  sendAdminTelegramCandidate,
  sendAdminTelegramPhoto,
  sendAdminTelegramText,
  updateAdminTelegramConversation,
} from "@/lib/api";

const FILTERS = [
  { id: "needs_admin", label: "Perlu dibalas" },
  { id: "waiting_customer", label: "Menunggu customer" },
  { id: "ready_for_order", label: "Siap dibuat order" },
  { id: "archived", label: "Diarsipkan" },
];

const STATUS_LABELS = {
  needs_admin: "Perlu dibalas",
  waiting_customer: "Menunggu customer",
  ready_for_order: "Siap dibuat order",
  archived: "Diarsipkan",
  pending: "Menunggu konfirmasi",
  confirmed: "Terkonfirmasi",
  rejected: "Tidak cocok",
  ordered: "Masuk order",
  send_failed: "Gagal dikirim",
  send_unknown: "Status pengiriman belum pasti",
};
const EMPTY_LIST = [];

function errorMessage(error) {
  const code = error?.response?.data?.detail?.error;
  const messages = {
    telegram_reply_window_expired: "Batas balas bot 24 jam sudah lewat. Lanjutkan chat dari aplikasi Telegram.",
    telegram_business_reply_unavailable: "Bot tidak memiliki izin untuk membalas chat ini.",
    conversation_archived: "Buka arsip chat ini sebelum mengirim pesan.",
    only_confirmed_candidates_can_be_ordered: "Order hanya dapat dibuat dari produk yang sudah dikonfirmasi.",
    catalog_item_unavailable: "Produk atau variannya sudah tidak aktif.",
    candidate_delivery_unknown: "Telegram belum memberi kepastian apakah konfirmasi terkirim. Jangan kirim ulang dulu.",
  };
  return messages[code] || error?.response?.data?.detail?.error || "Tindakan gagal. Coba lagi.";
}

function shortTime(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }).format(new Date(value));
}

function formatPrice(value, currency = "UZS") {
  return `${new Intl.NumberFormat("id-ID").format(value || 0)} ${currency}`;
}

function StatusBadge({ value }) {
  const ready = value === "ready_for_order" || value === "confirmed";
  return (
    <span className={`inline-flex shrink-0 items-center rounded-full px-2 py-1 text-[10px] font-semibold ${ready ? "bg-emerald-50 text-emerald-800" : value === "archived" || value === "rejected" ? "bg-neutral-100 text-neutral-500" : "bg-amber-50 text-amber-800"}`}>
      {STATUS_LABELS[value] || value}
    </span>
  );
}

function ConversationList({ items, selectedId, onSelect, loading, status, onStatus }) {
  return (
    <section className="flex h-full min-h-0 flex-col border-r border-neutral-200 bg-white lg:w-[290px] lg:shrink-0" data-testid="telegram-inbox-list">
      <div className="border-b border-neutral-200 p-4">
        <div className="flex items-center justify-between">
          <div><h2 className="font-semibold text-[#02422C]">Percakapan</h2><p className="mt-0.5 text-xs text-neutral-500">Chat Telegram Business</p></div>
          <MessageCircle className="h-5 w-5 text-[#CD9B3A]" aria-hidden="true" />
        </div>
        <label className="mt-4 flex h-11 items-center gap-2 border border-neutral-200 px-2.5 focus-within:border-[#145A46]">
          <Search className="h-4 w-4 text-neutral-400" aria-hidden="true" />
            <input className="min-w-0 flex-1 text-sm outline-none" value={status.q} onChange={(event) => status.setQ(event.target.value)} placeholder="Cari nama atau username" aria-label="Cari percakapan" />
        </label>
        <div className="mt-3 flex gap-1 overflow-x-auto overscroll-x-contain pb-1 lg:flex-wrap">
          {FILTERS.map((filter) => (
            <button key={filter.id} type="button" onClick={() => onStatus(filter.id)} className={`min-h-11 whitespace-nowrap rounded-full px-3 text-[11px] font-medium transition-colors ${status.filter === filter.id ? "bg-[#02422C] text-white" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"}`}>
              {filter.label}
            </button>
          ))}
        </div>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {loading ? <div className="p-5 text-xs text-neutral-400">Memuat percakapan…</div> : null}
        {!loading && !items.length ? <div className="px-5 py-12 text-center text-xs leading-5 text-neutral-400">Belum ada chat di filter ini.<br />Pesan baru tercatat setelah sinkronisasi Inbox aktif.</div> : null}
        {items.map((item) => (
          <button key={item.id} type="button" onClick={() => onSelect(item.id)} className={`block w-full border-b border-neutral-100 px-4 py-3 text-left transition-colors hover:bg-neutral-50 ${selectedId === item.id ? "bg-[#F2F7F4]" : ""}`} data-testid={`telegram-conversation-${item.id}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="truncate text-sm font-semibold text-neutral-800">{item.customer_name || "Telegram customer"}</span>
              <span className="shrink-0 text-[10px] text-neutral-400">{shortTime(item.last_message_at)}</span>
            </div>
            <p className="mt-0.5 truncate text-[11px] text-neutral-500">{item.customer_username ? `@${item.customer_username}` : `Telegram · ${item.chat_id}`}</p>
            <div className="mt-2 flex items-center justify-between gap-2"><span className="min-w-0 truncate text-xs text-neutral-500">{item.last_message?.type === "photo" ? "📷 Foto" : item.last_message?.text || "Belum ada pesan"}</span><StatusBadge value={item.status} /></div>
          </button>
        ))}
      </div>
      <p className="border-t border-neutral-200 px-4 py-2 text-[10px] leading-4 text-neutral-400">Bot hanya merekam pesan baru sejak Inbox diaktifkan.</p>
    </section>
  );
}

function OrderForm({ conversation, candidateIds, onClose, onCreated }) {
  const [form, setForm] = useState({ recipient: conversation.customer_name || "", phone: "", email: "", address: "", city: "", shippingAmount: "0" });
  const [key] = useState(() => `inbox-${crypto.randomUUID()}`);
  const [busy, setBusy] = useState(false);
  const update = (name, value) => setForm((current) => ({ ...current, [name]: value }));
  const submit = async (event) => {
    event.preventDefault();
    if (!candidateIds.length || !form.recipient.trim() || !form.phone.trim() || !form.address.trim() || !form.city.trim()) return;
    setBusy(true);
    try {
      const result = await createAdminTelegramOrder(conversation.id, {
        candidate_ids: candidateIds,
        guest_email: form.email.trim() || undefined,
        shipping_method: "manual",
        shipping_amount: Number(form.shippingAmount) || 0,
        shipping_address: { recipient_name: form.recipient.trim(), phone: form.phone.trim(), address_line_1: form.address.trim(), city: form.city.trim(), country_code: "UZ" },
      }, key);
      onCreated(result);
    } catch (error) {
      toast.error(errorMessage(error));
      setBusy(false);
    }
  };
  return (
    <form onSubmit={submit} className="border-t border-neutral-200 bg-[#FDFBF6] p-3" data-testid="telegram-inbox-order-form">
      <div className="flex items-start justify-between gap-2"><div><p className="text-sm font-semibold text-[#02422C]">Data pengiriman</p><p className="mt-1 text-[10px] leading-4 text-neutral-500">Order baru dibuat setelah produk dikonfirmasi customer.</p></div><button type="button" onClick={onClose} aria-label="Tutup form order"><X className="h-4 w-4" /></button></div>
      <div className="mt-3 space-y-2">
        <input required className="h-9 w-full border border-neutral-300 bg-white px-2.5 text-xs" placeholder="Nama penerima *" value={form.recipient} onChange={(event) => update("recipient", event.target.value)} />
        <input required className="h-9 w-full border border-neutral-300 bg-white px-2.5 text-xs" placeholder="Nomor telepon *" value={form.phone} onChange={(event) => update("phone", event.target.value)} />
        <input className="h-9 w-full border border-neutral-300 bg-white px-2.5 text-xs" placeholder="Email (opsional)" value={form.email} onChange={(event) => update("email", event.target.value)} />
        <input required className="h-9 w-full border border-neutral-300 bg-white px-2.5 text-xs" placeholder="Alamat lengkap *" value={form.address} onChange={(event) => update("address", event.target.value)} />
        <div className="grid grid-cols-2 gap-2"><input required className="h-9 min-w-0 border border-neutral-300 bg-white px-2.5 text-xs" placeholder="Kota *" value={form.city} onChange={(event) => update("city", event.target.value)} /><input className="h-9 min-w-0 border border-neutral-300 bg-white px-2.5 text-xs" inputMode="numeric" aria-label="Ongkir UZS" placeholder="Ongkir UZS" value={form.shippingAmount} onChange={(event) => update("shippingAmount", event.target.value.replace(/[^0-9]/g, ""))} /></div>
      </div>
      <button type="submit" disabled={busy || !candidateIds.length} className="mt-3 inline-flex h-10 w-full items-center justify-center gap-2 bg-[#02422C] px-3 text-xs font-semibold text-white disabled:opacity-50">
        {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <ShoppingBag className="h-4 w-4" />}{busy ? "Membuat order…" : "Buat order menunggu pembayaran"}
      </button>
    </form>
  );
}

function ProductWorkspace({ conversation, detail, onInvalidate, onOrderCreated, sourceMessageId, setSourceMessageId, compact = false }) {
  const [search, setSearch] = useState("");
  const [selectedProduct, setSelectedProduct] = useState(null);
  const [variantId, setVariantId] = useState("");
  const [quantity, setQuantity] = useState(1);
  const [makeOrder, setMakeOrder] = useState(false);
  const [selectedCandidates, setSelectedCandidates] = useState([]);
  const [sending, setSending] = useState(false);
  const selectedCandidatesInitialized = useRef(false);
  const previousConfirmedCandidates = useRef([]);
  const { data, isFetching } = useQuery({
    queryKey: ["admin-telegram-product-search", search, conversation.locale],
    queryFn: () => searchAdminTelegramProducts({ q: search.trim(), locale: conversation.locale }),
    enabled: search.trim().length >= 2,
  });
  const candidates = detail?.candidates ?? EMPTY_LIST;
  const confirmed = useMemo(() => candidates.filter((item) => item.status === "confirmed"), [candidates]);
  const confirmedKey = confirmed.map((item) => item.id).join("|");
  useEffect(() => {
    setSelectedCandidates((current) => {
      const available = confirmedKey ? confirmedKey.split("|") : [];
      if (!selectedCandidatesInitialized.current) {
        selectedCandidatesInitialized.current = true;
        previousConfirmedCandidates.current = available;
        return available;
      }
      const newlyConfirmed = available.filter((id) => !previousConfirmedCandidates.current.includes(id));
      previousConfirmedCandidates.current = available;
      return [...current.filter((id) => available.includes(id)), ...newlyConfirmed];
    });
  }, [confirmedKey]);
  const sendCandidate = async () => {
    if (!selectedProduct || !variantId) return;
    setSending(true);
    try {
      await sendAdminTelegramCandidate(conversation.id, { product_id: selectedProduct.id, variant_id: variantId, quantity: Number(quantity), source_message_id: sourceMessageId || undefined });
      toast.success("Kartu konfirmasi dikirim ke customer.");
      setSelectedProduct(null);
      setVariantId("");
      setSearch("");
      setSourceMessageId(null);
      onInvalidate();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  };
  const reviewCandidate = async (candidate, status) => {
    try {
      await reviewAdminTelegramCandidate(conversation.id, candidate.id, status);
      toast.success(status === "confirmed" ? "Produk ditandai terkonfirmasi." : "Produk ditandai tidak cocok.");
      onInvalidate();
    } catch (error) {
      toast.error(errorMessage(error));
    }
  };
  const onCreated = (result) => {
    toast.success(`Order ${result.order_number} berhasil dibuat.`);
    onOrderCreated(result);
  };

  return (
    <section className={`flex min-h-0 flex-col bg-white ${compact ? "border-t border-neutral-200" : "border-l border-neutral-200 lg:w-[320px] lg:shrink-0"}`} data-testid="telegram-inbox-products">
      <div className="border-b border-neutral-200 p-4"><div className="flex items-center gap-2"><PackageSearch className="h-4 w-4 text-[#CD9B3A]" /><div><h2 className="text-sm font-semibold text-[#02422C]">Produk & order</h2><p className="text-[10px] text-neutral-500">Cari berdasarkan nama, brand, slug, atau SKU</p></div></div></div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="p-3">
          <label className="flex h-11 items-center gap-2 border border-neutral-200 px-2.5 focus-within:border-[#145A46]"><Search className="h-4 w-4 text-neutral-400" /><input value={search} onChange={(event) => { setSearch(event.target.value); setSelectedProduct(null); }} placeholder="Cari produk…" className="min-w-0 flex-1 text-sm outline-none" data-testid="telegram-product-search" /></label>
          {sourceMessageId ? <div className="mt-2 flex items-center justify-between rounded bg-emerald-50 px-2 py-1.5 text-[10px] text-emerald-800"><span>Permintaan produk ditandai</span><button type="button" onClick={() => setSourceMessageId(null)} aria-label="Hapus pesan sumber"><X className="h-3 w-3" /></button></div> : null}
          {isFetching ? <p className="py-3 text-center text-xs text-neutral-400">Mencari…</p> : null}
          {!isFetching && search.trim().length >= 2 && !data?.items?.length ? <p className="py-3 text-xs text-neutral-400">Produk aktif tidak ditemukan.</p> : null}
          <div className="mt-2 space-y-2">
            {(data?.items || []).map((product) => (
              <div key={product.id} className={`rounded border p-2.5 ${selectedProduct?.id === product.id ? "border-[#145A46] bg-[#F5FAF7]" : "border-neutral-200"}`}>
                <button type="button" onClick={() => { setSelectedProduct(product); setVariantId(product.variants[0]?.id || ""); }} className="flex min-h-11 w-full items-center gap-2 text-left">
                  {product.image_url ? <img src={product.image_url} alt="" className="h-12 w-12 rounded border border-neutral-100 object-contain" /> : <div className="flex h-12 w-12 items-center justify-center rounded bg-neutral-100"><ShoppingBag className="h-4 w-4 text-neutral-400" /></div>}
                  <span className="min-w-0 flex-1"><span className="block line-clamp-2 text-xs font-semibold text-neutral-800">{product.name}</span><span className="mt-1 block truncate text-[10px] text-neutral-500">{product.brand} · {product.variants.length} varian</span></span>
                  {selectedProduct?.id === product.id ? <Check className="h-4 w-4 text-[#145A46]" /> : null}
                </button>
                {selectedProduct?.id === product.id ? <div className="mt-2 space-y-2 border-t border-neutral-100 pt-2">
                  <select className="h-11 w-full border border-neutral-200 bg-white px-2 text-sm" value={variantId} onChange={(event) => setVariantId(event.target.value)} aria-label="Pilih varian">
                    {product.variants.map((variant) => <option key={variant.id} value={variant.id}>{variant.option_label || variant.sku} · {variant.sku} · {formatPrice(variant.unit_price, product.currency)}</option>)}
                  </select>
                  <div className="flex flex-wrap items-center justify-between gap-2"><label className="text-xs text-neutral-600">Jumlah <input type="number" min="1" max="99" value={quantity} onChange={(event) => setQuantity(event.target.value)} className="ml-2 h-11 w-20 border border-neutral-200 px-2 text-sm" /></label><button type="button" onClick={sendCandidate} disabled={sending || !variantId} className="inline-flex min-h-11 items-center gap-1.5 bg-[#02422C] px-3 text-xs font-semibold text-white disabled:opacity-50">{sending ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}Kirim konfirmasi</button></div>
                </div> : null}
              </div>
            ))}
          </div>
        </div>
        <div className="border-t border-neutral-200 p-3">
          <div className="flex items-center justify-between"><h3 className="text-xs font-semibold text-[#02422C]">Kandidat produk</h3><span className="text-[10px] text-neutral-400">{candidates.length}</span></div>
          {!candidates.length ? <p className="mt-2 text-[11px] leading-4 text-neutral-400">Pilih produk yang cocok lalu minta konfirmasi customer di chat.</p> : null}
          <div className="mt-2 space-y-2">
            {candidates.map((candidate) => (
              <div key={candidate.id} className="rounded border border-neutral-200 p-2.5" data-testid={`telegram-candidate-${candidate.id}`}>
                <div className="flex items-start justify-between gap-2"><p className="text-xs font-semibold text-neutral-800">{candidate.product_name}</p><StatusBadge value={candidate.status} /></div>
                <p className="mt-1 text-[10px] text-neutral-500">{candidate.sku} · qty {candidate.quantity}{candidate.option_values && Object.keys(candidate.option_values).length ? ` · ${Object.values(candidate.option_values).join(" / ")}` : ""}</p>
                {candidate.status === "confirmed" ? <p className="mt-1 text-[10px] text-emerald-700">Dikonfirmasi oleh {candidate.confirmation_source === "customer" ? "customer di Telegram" : "admin setelah verifikasi chat"}</p> : null}
                {["pending", "send_unknown"].includes(candidate.status) ? <div className="mt-2 rounded bg-amber-50 p-2 text-[10px] leading-4 text-amber-900"><p>{candidate.status === "send_unknown" ? "Status kirim tidak pasti. Cek chat Telegram dahulu; jika customer membalas teks, verifikasi lalu catat hasilnya." : "Jika customer menjawab lewat teks, verifikasi jawabannya lalu catat di sini."}</p><div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => reviewCandidate(candidate, "confirmed")} className="inline-flex min-h-11 items-center gap-1 rounded bg-[#02422C] px-3 text-white"><CheckCircle2 className="h-3 w-3" />Konfirmasi</button><button type="button" onClick={() => reviewCandidate(candidate, "rejected")} className="inline-flex min-h-11 items-center gap-1 rounded border border-amber-300 bg-white px-3 text-amber-900"><X className="h-3 w-3" />Tidak cocok</button></div></div> : null}
                {candidate.status === "confirmed" ? <label className="mt-2 flex items-center gap-2 text-[10px] text-neutral-600"><input type="checkbox" checked={selectedCandidates.includes(candidate.id)} onChange={(event) => setSelectedCandidates((current) => event.target.checked ? [...current, candidate.id] : current.filter((id) => id !== candidate.id))} />Masukkan ke order</label> : null}
              </div>
            ))}
          </div>
          {confirmed.length ? <button type="button" onClick={() => setMakeOrder((value) => !value)} disabled={!selectedCandidates.length} className="mt-3 inline-flex h-9 w-full items-center justify-center gap-2 border border-[#145A46] text-xs font-semibold text-[#145A46] disabled:opacity-40"><ShoppingBag className="h-4 w-4" />{makeOrder ? "Tutup form order" : `Buat order (${selectedCandidates.length} produk)`}</button> : null}
        </div>
        {makeOrder ? <OrderForm conversation={conversation} candidateIds={selectedCandidates} onClose={() => setMakeOrder(false)} onCreated={onCreated} /> : null}
      </div>
    </section>
  );
}

export default function AdminTelegramInboxPage() {
  const [filter, setFilter] = useState("needs_admin");
  const [q, setQ] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState(null);
  const [photoCaption, setPhotoCaption] = useState("");
  const [productPanelOpen, setProductPanelOpen] = useState(false);
  const [sourceMessageId, setSourceMessageId] = useState(null);
  const [mobileThread, setMobileThread] = useState(false);
  const [sending, setSending] = useState(false);
  const bottomRef = useRef(null);
  const queryClient = useQueryClient();

  const inboxQuery = useQuery({
    queryKey: ["admin-telegram-inbox", filter, q],
    queryFn: () => getAdminTelegramInbox({ status: filter, q: q.trim() || undefined }),
    refetchInterval: 5000,
    refetchIntervalInBackground: false,
  });
  const detailQuery = useQuery({
    queryKey: ["admin-telegram-conversation", selectedId],
    queryFn: () => getAdminTelegramConversation(selectedId),
    enabled: Boolean(selectedId),
    refetchInterval: 4000,
    refetchIntervalInBackground: false,
  });
  const items = inboxQuery.data?.items ?? EMPTY_LIST;
  const detail = detailQuery.data;
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [detail?.messages?.length, selectedId]);

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-telegram-inbox"] });
    queryClient.invalidateQueries({ queryKey: ["admin-telegram-conversation", selectedId] });
  };
  const sendMessage = async (event) => {
    event.preventDefault();
    if (!detail?.can_send || sending) return;
    if (!text.trim() && !photo) return;
    setSending(true);
    try {
      if (photo) {
        await sendAdminTelegramPhoto(selectedId, photo, photoCaption.trim());
        setPhoto(null);
        setPhotoCaption("");
      } else {
        await sendAdminTelegramText(selectedId, text.trim());
        setText("");
      }
      invalidate();
    } catch (error) {
      toast.error(errorMessage(error));
    } finally {
      setSending(false);
    }
  };
  const handleOrderCreated = (result) => {
    setSelectedId(null);
    setMobileThread(false);
    queryClient.invalidateQueries({ queryKey: ["admin-telegram-inbox"] });
    window.location.assign(`/admin/orders/${result.order_number}`);
  };
  const setConversationStatus = async (status) => {
    try {
      await updateAdminTelegramConversation(selectedId, { status });
      toast.success(status === "archived" ? "Percakapan diarsipkan." : "Percakapan dibuka kembali.");
      invalidate();
    } catch (error) { toast.error(errorMessage(error)); }
  };
  const currentList = (
    <ConversationList
      items={items}
      selectedId={selectedId}
      onSelect={(id) => { setSelectedId(id); setSourceMessageId(null); setMobileThread(true); setProductPanelOpen(false); }}
      loading={inboxQuery.isLoading}
      status={{ filter, q, setQ }}
      onStatus={(value) => { setFilter(value); setSelectedId(null); setMobileThread(false); }}
    />
  );

  return (
    <div className="-m-4 flex min-h-[calc(100dvh-3.5rem)] flex-col bg-white lg:-m-8 lg:min-h-[calc(100dvh-3.5rem)]" data-testid="admin-telegram-inbox-page">
      <header className="flex min-h-[62px] items-center justify-between border-b border-neutral-200 px-4 py-3 lg:px-6">
        <div><p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#CD9B3A]">Sales · Telegram Business</p><h1 className="mt-0.5 text-lg font-semibold tracking-tight text-[#02422C]">Inbox Telegram</h1></div>
        <span className="hidden items-center gap-1.5 text-[11px] text-neutral-500 sm:inline-flex"><span className="h-2 w-2 rounded-full bg-emerald-500" />Tampilan diperbarui otomatis</span>
      </header>
      <div className="flex min-h-0 flex-1 overflow-hidden lg:grid lg:grid-cols-[290px_minmax(0,1fr)_320px]">
        <div className={`${mobileThread ? "hidden" : "flex"} min-h-0 w-full flex-col lg:flex lg:w-auto lg:min-w-0`}>{currentList}</div>
        {!selectedId ? (
          <div className="hidden flex-1 flex-col items-center justify-center bg-[#FAFBFA] px-8 text-center lg:flex">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-[#EAF3EF]"><MessageCircle className="h-6 w-6 text-[#145A46]" /></div>
            <h2 className="mt-4 text-base font-semibold text-[#02422C]">Pilih percakapan</h2>
            <p className="mt-1 max-w-sm text-xs leading-5 text-neutral-500">Chat baru yang diterima Telegram Business akan muncul di sini. Admin bisa bantu customer mencari produk dan membuat order secara manual.</p>
          </div>
        ) : null}
        {selectedId ? (
          <section className={`${mobileThread ? "flex" : "hidden lg:flex"} min-h-0 min-w-0 flex-1 flex-col bg-[#F7F8F7] lg:col-start-2 lg:col-end-3`} data-testid="telegram-inbox-thread">
            {detailQuery.isError && !detail ? (
              <div className="flex flex-1 flex-col items-center justify-center px-6 text-center" role="alert">
                <p className="text-sm font-medium text-neutral-700">Percakapan gagal dimuat.</p>
                <p className="mt-1 text-xs text-neutral-500">Pesan tetap tersimpan. Coba muat detail chat sekali lagi.</p>
                <button type="button" onClick={() => detailQuery.refetch()} className="mt-3 border border-[#145A46] px-3 py-2 text-xs font-medium text-[#145A46] hover:bg-white">Coba lagi</button>
              </div>
            ) : detailQuery.isLoading || !detail ? <div className="flex flex-1 items-center justify-center text-sm text-neutral-400"><LoaderCircle className="mr-2 h-4 w-4 animate-spin" />Memuat chat…</div> : <>
              <div className="flex flex-col gap-2 border-b border-neutral-200 bg-white px-3 py-3 sm:flex-row sm:items-center sm:justify-between lg:px-4">
                <div className="flex min-w-0 items-center gap-2"><button type="button" className="inline-flex h-11 w-11 shrink-0 items-center justify-center lg:hidden" onClick={() => setMobileThread(false)} aria-label="Kembali ke daftar chat"><ArrowLeft className="h-5 w-5" /></button><div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#EAF3EF] text-xs font-semibold text-[#145A46]">{detail.customer_name?.slice(0, 1)?.toUpperCase() || "T"}</div><div className="min-w-0"><h2 className="truncate text-sm font-semibold text-[#02422C]">{detail.customer_name}</h2><p className="truncate text-[10px] text-neutral-500">{detail.customer_username ? `@${detail.customer_username}` : `ID ${detail.chat_id}`} · {detail.locale.toUpperCase()}</p></div></div>
                <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:w-auto"><select aria-label="Bahasa konfirmasi" value={detail.locale} onChange={async (event) => { try { await updateAdminTelegramConversation(selectedId, { locale: event.target.value }); invalidate(); } catch (error) { toast.error(errorMessage(error)); } }} className="h-11 border border-neutral-200 bg-white px-2 text-xs uppercase text-neutral-600"><option value="id">ID</option><option value="en">EN</option><option value="uz">UZ</option><option value="ru">RU</option></select><StatusBadge value={detail.status} /><button type="button" onClick={() => setConversationStatus(detail.status === "archived" ? "needs_admin" : "archived")} className="inline-flex h-11 items-center gap-1 border border-neutral-200 px-3 text-xs text-neutral-600 hover:bg-neutral-50" title={detail.status === "archived" ? "Buka kembali" : "Arsipkan chat"}>{detail.status === "archived" ? <MessageCircle className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}<span className="hidden sm:inline">{detail.status === "archived" ? "Buka kembali" : "Arsipkan"}</span></button></div>
              </div>
              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-3 py-4 lg:px-5" data-testid="telegram-inbox-messages">
                {!detail.messages?.length ? <div className="py-10 text-center text-xs text-neutral-400">Belum ada transkrip tersimpan untuk chat ini.</div> : null}
                {(detail.messages || []).map((message) => (
                  <div key={message.id} className={`flex ${message.direction === "outbound" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[86%] rounded-lg px-3 py-2 shadow-sm sm:max-w-[78%] ${message.direction === "outbound" ? "bg-[#E5F4EA] text-neutral-800" : "border border-neutral-100 bg-white text-neutral-800"}`}>
                      {message.photo_url ? <img src={message.photo_url} alt="Foto dari chat Telegram" className="mb-2 max-h-64 max-w-full rounded object-contain" loading="lazy" /> : null}
                      {message.text ? <p className="whitespace-pre-wrap break-words text-xs leading-5">{message.text}</p> : null}
                      {message.is_deleted ? <p className="text-xs italic text-neutral-400">Pesan dihapus</p> : null}
                      <div className="mt-1 flex items-center justify-end gap-1 text-[9px] text-neutral-400">{message.edited_at ? <span>diedit</span> : null}{message.source === "cms" ? <span>· CMS</span> : null}<span>{shortTime(message.created_at)}</span></div>
                      {message.direction === "inbound" && !message.is_deleted ? <button type="button" onClick={() => { setSourceMessageId(message.id); setProductPanelOpen(true); }} className="mt-1 min-h-11 border-t border-neutral-100 pt-2 text-left text-xs font-medium text-[#145A46] hover:underline">Tandai sebagai permintaan produk</button> : null}
                    </div>
                  </div>
                ))}
                <div ref={bottomRef} />
              </div>
              {detail.can_send ? (
                <form onSubmit={sendMessage} className="border-t border-neutral-200 bg-white p-3 lg:px-4" data-testid="telegram-inbox-composer">
                  {photo ? <div className="mb-2 flex items-center gap-2 rounded bg-neutral-50 p-2"><ImagePlus className="h-4 w-4 text-[#145A46]" /><span className="min-w-0 flex-1 truncate text-[11px]">{photo.name}</span><button type="button" onClick={() => setPhoto(null)} aria-label="Hapus foto"><X className="h-4 w-4" /></button></div> : null}
                  <div className="flex items-end gap-2"><label className="flex h-11 w-11 shrink-0 cursor-pointer items-center justify-center border border-neutral-200 text-neutral-500 hover:bg-neutral-50" title="Kirim foto"><Paperclip className="h-4 w-4" /><input className="sr-only" type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { setPhoto(event.target.files?.[0] || null); event.target.value = ""; }} /></label>{photo ? <input className="h-11 min-w-0 flex-1 border border-neutral-200 px-3 text-sm outline-none focus:border-[#145A46]" value={photoCaption} onChange={(event) => setPhotoCaption(event.target.value)} placeholder="Caption foto (opsional)" maxLength={1024} /> : <textarea rows={1} value={text} onChange={(event) => setText(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(event); } }} className="max-h-28 min-h-11 min-w-0 flex-1 resize-y border border-neutral-200 px-3 py-2.5 text-sm outline-none focus:border-[#145A46]" placeholder="Tulis pesan…" maxLength={4096} data-testid="telegram-inbox-message-input" />}<button type="submit" disabled={sending || (!photo && !text.trim())} className="flex h-11 w-11 shrink-0 items-center justify-center bg-[#02422C] text-white disabled:opacity-40" aria-label="Kirim pesan">{sending ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}</button></div>
                  <p className="mt-1.5 text-[9px] text-neutral-400">Balasan bot tersedia hingga 24 jam setelah pesan terakhir customer.</p>
                </form>
              ) : (
                <div className="border-t border-amber-200 bg-amber-50 px-3 py-3 text-[11px] leading-5 text-amber-900"><div className="flex gap-2"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" /><p>{detail.status === "archived" ? "Chat ini diarsipkan. Buka kembali untuk melanjutkan dari Inbox." : "Batas balas bot 24 jam telah lewat atau izin Business tidak tersedia. Lanjutkan percakapan dari aplikasi Telegram."}</p></div></div>
              )}
              <div className="border-t border-neutral-200 bg-white p-2 lg:hidden"><button type="button" onClick={() => setProductPanelOpen((value) => !value)} className="flex min-h-11 w-full items-center justify-center gap-2 text-sm font-semibold text-[#145A46]"><PackageSearch className="h-4 w-4" />{productPanelOpen ? "Tutup panel produk" : "Cari produk / buat order"}</button></div>
              {productPanelOpen ? <div className="max-h-[55vh] overflow-y-auto lg:hidden"><ProductWorkspace conversation={detail} detail={detail} onInvalidate={invalidate} onOrderCreated={handleOrderCreated} sourceMessageId={sourceMessageId} setSourceMessageId={setSourceMessageId} compact /></div> : null}
            </>}
          </section>
        ) : null}
        {selectedId && detail ? <div className="hidden min-h-0 lg:col-start-3 lg:col-end-4 lg:flex"><ProductWorkspace conversation={detail} detail={detail} onInvalidate={invalidate} onOrderCreated={handleOrderCreated} sourceMessageId={sourceMessageId} setSourceMessageId={setSourceMessageId} /></div> : null}
      </div>
    </div>
  );
}
