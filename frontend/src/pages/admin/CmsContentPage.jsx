import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, FilePlus2, Search, Sparkles } from "lucide-react";
import { getCmsContent } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cmsStatusLabel, cmsTypeLabel, CMS_CONTENT_TYPES } from "./cmsContentSchema";

const PAGE_SIZE = 20;

function StatusBadge({ value }) {
  const styles = {
    published: "border-emerald-200 bg-emerald-50 text-emerald-800",
    draft: "border-stone-200 bg-stone-100 text-stone-700",
    archived: "border-amber-200 bg-amber-50 text-amber-800",
  };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${styles[value] || styles.draft}`}>{cmsStatusLabel(value)}</span>;
}

function LocaleState({ entry }) {
  const names = { en: "Inggris", id: "Indonesia", uz: "Uzbek", ru: "Rusia" };
  return (
    <div className="flex flex-wrap gap-1" aria-label="Kelengkapan bahasa">
      {["en", "id", "uz", "ru"].map((locale) => {
        const complete = entry.completeness?.includes(locale);
        return <span key={locale} title={`${names[locale]}${complete ? " lengkap" : " belum diisi"}`} className={`inline-flex h-6 min-w-8 items-center justify-center rounded-md px-1.5 text-[10px] font-bold uppercase ${complete ? "bg-[#02422C]/10 text-[#02422C]" : "bg-stone-100 text-stone-400"}`}>{locale}</span>;
      })}
    </div>
  );
}

export default function CmsContentPage() {
  const [params, setParams] = useSearchParams();
  const type = params.get("type") || "";
  const status = params.get("status") || "";
  const q = params.get("q") || "";
  const page = Math.max(1, Number(params.get("page") || 1));
  const [searchText, setSearchText] = useState(q);

  useEffect(() => setSearchText(q), [q]);
  useEffect(() => {
    if (searchText === q) return undefined;
    const timer = setTimeout(() => setFilter("q", searchText.trim()), 250);
    return () => clearTimeout(timer);
  // setFilter is intentionally local and URL state is the source of truth.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchText, q]);

  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["cms-content", { type, status, q, page }],
    queryFn: () => getCmsContent({
      type: type || undefined,
      status: status || undefined,
      q: q || undefined,
      page,
      page_size: PAGE_SIZE,
    }),
    placeholderData: (previous) => previous,
  });

  function setFilter(key, value) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  }

  const items = data?.items || [];
  const total = data?.total || 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div data-testid="cms-content-page" className="mx-auto max-w-7xl space-y-6">
      <header className="relative overflow-hidden rounded-2xl bg-[#02422C] px-6 py-7 text-white shadow-sm sm:px-8 sm:py-9">
        <div className="absolute -right-10 -top-16 h-56 w-56 rounded-full border border-white/10" />
        <div className="absolute -right-2 -top-8 h-40 w-40 rounded-full border border-[#CD9B3A]/40" />
        <div className="relative flex flex-wrap items-end justify-between gap-5">
          <div>
            <p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#E7C77E]"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" />Ruang editorial</p>
            <h1 className="mt-2 font-brand text-3xl font-semibold sm:text-4xl">Konten toko</h1>
            <p className="mt-2 max-w-xl text-sm leading-6 text-white/75">Kelola cerita, halaman, banner, navigasi, dan seluruh konten yang tampil di ShaniCantik.</p>
          </div>
          <Link to="/cms/new" data-testid="cms-new-button" className="inline-flex h-11 items-center gap-2 rounded-lg bg-[#FDF7E9] px-4 text-sm font-bold text-[#02422C] shadow-sm transition hover:bg-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white">
            <FilePlus2 className="h-4 w-4" aria-hidden="true" />Buat konten
          </Link>
        </div>
      </header>

      <section className="rounded-xl border border-[#E9E3D7] bg-[#FDFBF6] p-4 shadow-sm sm:p-5" aria-label="Filter konten">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_240px_200px_auto]">
          <label className="relative block">
            <span className="sr-only">Cari nama atau slug</span>
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} placeholder="Cari nama atau slug…" className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white pl-10 pr-3 text-sm outline-none transition focus:border-[#02422C] focus:ring-2 focus:ring-[#02422C]/10" data-testid="cms-search" />
          </label>
          <label>
            <span className="sr-only">Jenis konten</span>
            <select value={type} onChange={(event) => setFilter("type", event.target.value)} className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white px-3 text-sm outline-none focus:border-[#02422C]" data-testid="cms-type-filter">
              <option value="">Semua jenis</option>
              {CMS_CONTENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
          </label>
          <label>
            <span className="sr-only">Status publikasi</span>
            <select value={status} onChange={(event) => setFilter("status", event.target.value)} className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white px-3 text-sm outline-none focus:border-[#02422C]" data-testid="cms-status-filter">
              <option value="">Semua status</option>
              <option value="draft">Draft</option>
              <option value="published">Tayang</option>
              <option value="archived">Diarsipkan</option>
            </select>
          </label>
          <div className="flex items-center justify-end text-xs text-stone-500" aria-live="polite">
            {isFetching && !isLoading ? <span className="mr-2 h-2 w-2 animate-pulse rounded-full bg-[#CD9B3A]" /> : null}
            {total} konten
          </div>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-[#E9E3D7] bg-white shadow-sm" aria-label="Daftar konten">
        {isError ? (
          <div className="px-6 py-14 text-center" data-testid="cms-content-error">
            <p className="font-semibold text-stone-800">Konten belum dapat dimuat</p>
            <p className="mt-1 text-sm text-stone-500">Periksa koneksi, lalu coba lagi.</p>
            <button type="button" onClick={() => refetch()} className="mt-4 rounded-lg bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white">Coba lagi</button>
          </div>
        ) : isLoading ? (
          <div className="space-y-3 p-5" data-testid="cms-content-loading">{Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-14 w-full rounded-lg" />)}</div>
        ) : items.length ? (
          <>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left text-sm">
                <thead className="bg-[#F8F5EE] text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-500">
                  <tr><th className="px-5 py-3.5">Nama / slug</th><th className="px-4 py-3.5">Jenis</th><th className="px-4 py-3.5">Status</th><th className="px-4 py-3.5">Bahasa</th><th className="px-4 py-3.5">Terakhir diubah</th><th className="px-5 py-3.5"><span className="sr-only">Aksi</span></th></tr>
                </thead>
                <tbody className="divide-y divide-[#F0ECE4]">
                  {items.map((entry) => (
                    <tr key={entry.id} className="transition-colors hover:bg-[#FDFBF6]" data-testid={`cms-row-${entry.slug || entry.id}`}>
                      <td className="px-5 py-4">
                        <Link to={`/cms/${entry.id}`} className="font-semibold text-[#17392C] transition hover:text-[#8A6420]" data-testid={`cms-edit-${entry.slug || entry.id}`}>{entry.internal_name}</Link>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-stone-400"><span>{entry.slug || "Tanpa slug"}</span>{entry.has_unpublished_changes ? <span className="rounded-full bg-[#FBF1D8] px-2 py-0.5 font-semibold text-[#855E17]">Perubahan belum tayang</span> : null}{!entry.is_visible ? <span className="rounded-full bg-stone-100 px-2 py-0.5 text-stone-500">Disembunyikan</span> : null}</div>
                      </td>
                      <td className="px-4 py-4"><span className="rounded-md bg-[#F4F1E9] px-2.5 py-1.5 text-xs font-medium text-stone-700">{cmsTypeLabel(entry.content_type)}</span></td>
                      <td className="px-4 py-4"><StatusBadge value={entry.status} /></td>
                      <td className="px-4 py-4"><LocaleState entry={entry} /></td>
                      <td className="px-4 py-4 text-xs text-stone-500">{entry.updated_at ? new Date(entry.updated_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" }) : "—"}</td>
                      <td className="px-5 py-4 text-right"><Link to={`/cms/${entry.id}`} className="text-xs font-bold uppercase tracking-wide text-[#02422C] hover:underline">Buka</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[#F0ECE4] bg-[#FDFBF6] px-5 py-3.5">
              <p className="text-xs text-stone-500">Menampilkan {Math.min((page - 1) * PAGE_SIZE + 1, total)}–{Math.min(page * PAGE_SIZE, total)} dari {total}</p>
              <div className="flex items-center gap-2">
                <button type="button" onClick={() => setFilter("page", String(Math.max(1, page - 1)))} disabled={page <= 1} aria-label="Halaman sebelumnya" className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#E4DED2] bg-white text-stone-600 disabled:cursor-not-allowed disabled:opacity-40" data-testid="cms-page-prev"><ChevronLeft className="h-4 w-4" aria-hidden="true" /></button>
                <span className="min-w-20 text-center text-xs font-medium text-stone-600">Halaman {page} / {pageCount}</span>
                <button type="button" onClick={() => setFilter("page", String(Math.min(pageCount, page + 1)))} disabled={page >= pageCount} aria-label="Halaman berikutnya" className="inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[#E4DED2] bg-white text-stone-600 disabled:cursor-not-allowed disabled:opacity-40" data-testid="cms-page-next"><ChevronRight className="h-4 w-4" aria-hidden="true" /></button>
              </div>
            </footer>
          </>
        ) : (
          <div className="px-6 py-16 text-center" data-testid="cms-content-empty">
            <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#F4F1E9] text-[#02422C]"><Search className="h-5 w-5" aria-hidden="true" /></div>
            <h2 className="mt-4 font-brand text-xl font-semibold text-[#17392C]">Belum ada konten yang cocok</h2>
            <p className="mt-1 text-sm text-stone-500">Ubah filter atau buat konten baru untuk toko.</p>
            <Link to="/cms/new" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white"><FilePlus2 className="h-4 w-4" aria-hidden="true" />Buat konten</Link>
          </div>
        )}
      </section>
    </div>
  );
}
