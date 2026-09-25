import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, LockKeyhole, Pencil, Plus, ShieldCheck, X } from "lucide-react";
import { toast } from "sonner";
import {
  createAdminPaymentDestination,
  getAdminAudit,
  getAdminPaymentDestination,
  getAdminPaymentDestinations,
  getAdminSettings,
  updateAdminPaymentDestination,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney } from "./adminUtils";

function Row({ label, value, testId }) {
  return (
    <div className="flex justify-between gap-4 border-b border-neutral-50 py-2.5 text-sm" data-testid={testId}>
      <dt className="text-neutral-500">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

const EMPTY_DESTINATION = {
  bank_name: "",
  destination_type: "card",
  account_number: "",
  holder_name: "",
  is_active: true,
};

function errorCode(error) {
  const detail = error?.response?.data?.detail;
  return typeof detail === "string" ? detail : detail?.error;
}

export default function AdminSettingsPage() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["admin-settings"], queryFn: getAdminSettings });
  const destinationsQuery = useQuery({
    queryKey: ["admin-payment-destinations"],
    queryFn: getAdminPaymentDestinations,
  });
  const auditQuery = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => getAdminAudit({ page_size: 50 }),
  });
  const [editor, setEditor] = useState(null);
  const [loadingEditor, setLoadingEditor] = useState(false);
  const [saving, setSaving] = useState(false);

  const s = settingsQuery.data;
  const destinationData = destinationsQuery.data;
  const destinations = destinationData?.items || [];
  const activeCount = destinationData?.active_count || 0;
  const maxCount = destinationData?.max_count || 4;
  const refreshDestinations = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-payment-destinations"] });
    queryClient.invalidateQueries({ queryKey: ["admin-settings"] });
  };

  const openExistingDestination = async (id) => {
    setLoadingEditor(true);
    try {
      setEditor({ ...(await getAdminPaymentDestination(id)) });
    } catch {
      toast.error("Data rekening tidak dapat dimuat. Coba lagi.");
    } finally {
      setLoadingEditor(false);
    }
  };

  const saveDestination = async (event) => {
    event.preventDefault();
    if (!editor) return;
    setSaving(true);
    const payload = {
      bank_name: editor.bank_name,
      destination_type: editor.destination_type,
      account_number: editor.account_number,
      holder_name: editor.holder_name,
      is_active: Boolean(editor.is_active),
    };
    try {
      if (editor.id) {
        await updateAdminPaymentDestination(editor.id, payload);
        toast.success("Rekening transfer diperbarui.");
      } else {
        await createAdminPaymentDestination(payload);
        toast.success("Rekening transfer ditambahkan.");
      }
      setEditor(null);
      refreshDestinations();
    } catch (error) {
      const messages = {
        payment_destination_limit_reached: "Empat rekening sudah tersimpan. Edit rekening yang ada untuk menggantinya.",
        invalid_card_number_length: "Nomor kartu harus berisi 12–19 digit.",
        invalid_bank_account_length: "Nomor rekening harus berisi 8–34 digit.",
        account_number_digits_only: "Nomor rekening/kartu hanya boleh berisi angka.",
      };
      toast.error(messages[errorCode(error)] || "Rekening transfer gagal disimpan.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div data-testid="admin-settings-page">
      <h1 className="text-xl font-semibold tracking-tight">Settings</h1>

      <section className="mt-6 border border-neutral-200 bg-white p-5" data-testid="settings-store">
        <h2 className="text-sm font-semibold">Store configuration</h2>
        {settingsQuery.isLoading ? (
          <Skeleton className="mt-4 h-48 w-full" />
        ) : (
          <dl className="mt-3">
            <Row label="Store" value={s?.store} testId="setting-store" />
            <Row label="Business model" value={s?.business_model === "single_vendor" ? "Single vendor (this store operates everything)" : s?.business_model} testId="setting-model" />
            <Row label="Base currency" value={s?.currency} testId="setting-currency" />
            <Row label="Payment status" value={activeCount ? `Manual transfer · ${activeCount} active` : "Manual transfer · setup required"} testId="setting-payments" />
            <Row label="Shipping provider" value={s?.shipping_provider} testId="setting-shipping" />
            <Row label="Shipping methods" value={(s?.shipping_methods || []).map((m) => `${m.label} ${fmtMoney(m.amount, s?.currency)} (${m.eta} days)`).join(" · ")} testId="setting-shipping-methods" />
            <Row label="Free standard shipping over" value={fmtMoney(s?.free_standard_threshold, s?.currency)} testId="setting-free-shipping" />
            <Row label="Inventory reservation TTL" value={`${s?.inventory_reservation_ttl_minutes} min`} testId="setting-reservation-ttl" />
            <Row label="Media storage" value={s?.media_storage} testId="setting-media-storage" />
            <Row label="Locales" value={(s?.locales || []).join(", ")} testId="setting-locales" />
          </dl>
        )}
      </section>

      <section className="mt-6 border border-neutral-200 bg-white" data-testid="payment-destinations-section">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-neutral-200 px-5 py-4">
          <div>
            <div className="flex items-center gap-2 text-[#02422C]"><CreditCard className="h-4 w-4" aria-hidden="true" /><h2 className="text-sm font-semibold">Metode transfer</h2></div>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-neutral-500">Rekening aktif akan muncul sebagai pilihan di Telegram setelah order dibuat. Nomor lengkap hanya terlihat saat Anda membuka editor.</p>
          </div>
          <button type="button" onClick={() => setEditor({ id: null, ...EMPTY_DESTINATION })} disabled={Boolean(editor) || loadingEditor || destinations.length >= maxCount} className="inline-flex h-10 items-center gap-2 bg-[#02422C] px-4 text-sm font-semibold text-white transition hover:bg-[#035338] disabled:cursor-not-allowed disabled:opacity-50" data-testid="add-payment-destination"><Plus className="h-4 w-4" aria-hidden="true" /> Tambah rekening</button>
        </div>

        {activeCount === 0 ? (
          <div className="m-5 flex gap-3 border border-amber-300 bg-amber-50 p-4 text-sm text-amber-950" role="status" data-testid="payment-destinations-warning">
            <LockKeyhole className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <p>Belum ada rekening aktif. Order tetap dapat dibuat, tetapi pilihan transfer belum bisa dikirim ke customer.</p>
          </div>
        ) : activeCount < maxCount ? (
          <div className="mx-5 mt-5 flex gap-3 border border-[#CD9B3A]/40 bg-[#FDF7E9] p-3 text-xs text-neutral-700" role="status" data-testid="payment-destinations-warning">
            <ShieldCheck className="h-4 w-4 shrink-0 text-[#9A6A13]" aria-hidden="true" />
            <p>{activeCount} dari {maxCount} rekening aktif. Customer akan melihat rekening yang aktif saja.</p>
          </div>
        ) : null}

        {destinationsQuery.isLoading ? (
          <div className="space-y-3 p-5"><Skeleton className="h-16 w-full" /><Skeleton className="h-16 w-full" /></div>
        ) : destinations.length ? (
          <ol className="divide-y divide-neutral-100" data-testid="payment-destination-list">
            {destinations.map((destination) => (
              <li key={destination.id} className="flex flex-wrap items-center justify-between gap-4 px-5 py-4" data-testid={`payment-destination-${destination.slot}`}>
                <div className="flex min-w-0 items-start gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#F1F7F4] text-sm font-semibold text-[#02422C]">{destination.slot + 1}</span>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-medium text-neutral-900">{destination.bank_name}</h3>
                      <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide ${destination.is_active ? "bg-emerald-50 text-emerald-800" : "bg-neutral-100 text-neutral-500"}`}>{destination.is_active ? "Aktif" : "Nonaktif"}</span>
                    </div>
                    <p className="mt-1 text-sm text-neutral-600">{destination.destination_type === "card" ? "Kartu" : "Rekening bank"} · {destination.masked_account_number}</p>
                    <p className="mt-0.5 text-xs text-neutral-400">Atas nama {destination.holder_name}</p>
                  </div>
                </div>
                <button type="button" onClick={() => openExistingDestination(destination.id)} disabled={Boolean(editor) || loadingEditor} className="inline-flex h-9 items-center gap-2 border border-neutral-300 px-3 text-xs font-medium text-neutral-700 hover:bg-neutral-50 disabled:opacity-50" data-testid={`edit-payment-destination-${destination.slot}`}><Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit</button>
              </li>
            ))}
          </ol>
        ) : (
          <div className="px-5 py-10 text-center" data-testid="payment-destination-empty">
            <CreditCard className="mx-auto h-8 w-8 text-neutral-300" aria-hidden="true" />
            <p className="mt-3 text-sm font-medium text-neutral-700">Belum ada rekening transfer</p>
            <p className="mt-1 text-xs text-neutral-500">Tambahkan rekening pertama agar customer dapat memilih tujuan pembayaran.</p>
          </div>
        )}

        {editor ? (
          <form onSubmit={saveDestination} className="border-t border-neutral-200 bg-[#FAFAF8] p-5" data-testid="payment-destination-editor">
            <div className="flex items-start justify-between gap-4">
              <div><h3 className="text-sm font-semibold text-[#02422C]">{editor.id ? "Edit rekening transfer" : "Tambah rekening transfer"}</h3><p className="mt-1 text-xs text-neutral-500">Pastikan nomor dan nama pemilik sesuai dengan rekening yang akan menerima transfer.</p></div>
              <button type="button" onClick={() => setEditor(null)} className="rounded p-1 text-neutral-500 hover:bg-white hover:text-neutral-900" aria-label="Tutup editor"><X className="h-4 w-4" /></button>
            </div>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="block text-xs font-medium text-neutral-600">Nama bank<input required minLength={2} maxLength={100} autoComplete="organization" value={editor.bank_name} onChange={(event) => setEditor({ ...editor, bank_name: event.target.value })} placeholder="Contoh: Kapitalbank" className="mt-1.5 h-10 w-full border border-neutral-300 bg-white px-3 text-sm text-neutral-900 outline-none focus:border-[#02422C] focus:ring-1 focus:ring-[#02422C]" /></label>
              <label className="block text-xs font-medium text-neutral-600">Jenis tujuan<select value={editor.destination_type} onChange={(event) => setEditor({ ...editor, destination_type: event.target.value })} className="mt-1.5 h-10 w-full border border-neutral-300 bg-white px-3 text-sm text-neutral-900 outline-none focus:border-[#02422C] focus:ring-1 focus:ring-[#02422C]"><option value="card">Kartu</option><option value="bank_account">Rekening bank</option></select></label>
              <label className="block text-xs font-medium text-neutral-600">Nomor kartu/rekening<input required minLength={8} maxLength={64} inputMode="numeric" autoComplete="off" spellCheck="false" value={editor.account_number} onChange={(event) => setEditor({ ...editor, account_number: event.target.value })} placeholder={editor.destination_type === "card" ? "12–19 digit" : "8–34 digit"} className="mt-1.5 h-10 w-full border border-neutral-300 bg-white px-3 font-mono text-sm text-neutral-900 outline-none focus:border-[#02422C] focus:ring-1 focus:ring-[#02422C]" /></label>
              <label className="block text-xs font-medium text-neutral-600">Nama pemilik<input required minLength={2} maxLength={120} autoComplete="name" value={editor.holder_name} onChange={(event) => setEditor({ ...editor, holder_name: event.target.value })} placeholder="Sesuai nama pada rekening" className="mt-1.5 h-10 w-full border border-neutral-300 bg-white px-3 text-sm text-neutral-900 outline-none focus:border-[#02422C] focus:ring-1 focus:ring-[#02422C]" /></label>
            </div>
            <label className="mt-4 flex cursor-pointer items-start gap-3 border border-neutral-200 bg-white p-3 text-sm text-neutral-700">
              <input type="checkbox" checked={Boolean(editor.is_active)} onChange={(event) => setEditor({ ...editor, is_active: event.target.checked })} className="mt-0.5 accent-[#02422C]" />
              <span><span className="block font-medium">Tampilkan sebagai pilihan transfer</span><span className="mt-0.5 block text-xs text-neutral-500">Menonaktifkan rekening akan menghilangkannya dari order baru. Order lama tetap menyimpan detail yang dipilih.</span></span>
            </label>
            <div className="mt-5 flex flex-wrap justify-end gap-2">
              <button type="button" onClick={() => setEditor(null)} className="h-10 border border-neutral-300 bg-white px-4 text-sm text-neutral-700 hover:bg-neutral-50">Batal</button>
              <button type="submit" disabled={saving} className="h-10 bg-[#02422C] px-5 text-sm font-semibold text-white hover:bg-[#035338] disabled:opacity-50">{saving ? "Menyimpan…" : "Simpan rekening"}</button>
            </div>
          </form>
        ) : null}
      </section>

      <section className="mt-6 border border-neutral-200 bg-white" data-testid="settings-audit">
        <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">Audit log</h2>
        <table className="w-full text-sm">
          <thead><tr className="border-b border-neutral-100 text-left text-xs uppercase tracking-wider text-neutral-400"><th className="px-5 py-2 font-medium">When</th><th className="px-5 py-2 font-medium">Actor</th><th className="px-5 py-2 font-medium">Action</th><th className="px-5 py-2 font-medium">Target</th></tr></thead>
          <tbody>
            {auditQuery.isLoading ? Array.from({ length: 5 }).map((_, i) => <tr key={i}><td colSpan={4} className="px-5 py-2.5"><Skeleton className="h-4 w-full" /></td></tr>) : (auditQuery.data?.items || []).map((a) => <tr key={a.id} className="border-b border-neutral-50" data-testid={`audit-row-${a.id}`}><td className="whitespace-nowrap px-5 py-2.5 text-neutral-500">{fmtDate(a.created_at)}</td><td className="px-5 py-2.5 text-neutral-600">{a.actor || "system"}</td><td className="px-5 py-2.5 font-mono text-xs">{a.action}</td><td className="px-5 py-2.5 text-xs text-neutral-500">{a.target_type}</td></tr>)}
            {!auditQuery.isLoading && !(auditQuery.data?.items || []).length ? <tr><td colSpan={4} className="px-5 py-8 text-center text-sm text-neutral-400" data-testid="audit-empty">No audit events yet.</td></tr> : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}
