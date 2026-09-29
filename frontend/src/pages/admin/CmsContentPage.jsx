import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight, BookOpen, ChevronLeft, ChevronRight, FilePlus2, FileText,
  Image, LayoutDashboard, Menu, Search, Sparkles, Store,
} from "lucide-react";
import { getCmsContent, getCmsMedia } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { CMS_CONTENT_TYPES, CMS_PRODUCT_SECTION_KEYS, cmsStatusLabel, cmsTypeLabel } from "./cmsContentSchema";

const PAGE_SIZE = 20;
const LOCALES = ["id", "en", "uz", "ru"];

const HUB_GROUPS = [
  { key: "homepage", title: "Homepage", description: "Atur tampilan halaman utama toko", icon: LayoutDashboard, tone: "bg-emerald-50 text-[#02422C]", hints: ["Hero utama", "Department", "Terlaris", "Koleksi Terbaru", "Rawat Kulitmu", "Gaya Sehari-hari"], action: "Kelola homepage" },
  { key: "store", title: "Toko", description: "Informasi yang membantu pelanggan", icon: Store, tone: "bg-[#F8F1DE] text-[#8A6420]", hints: ["Pengumuman", "FAQ", "Halaman informasi"], action: "Kelola" },
  { key: "stories", title: "Stories & Editorial", description: "Inspirasi, artikel, dan panduan untuk pelanggan", icon: BookOpen, tone: "bg-violet-50 text-violet-800", hints: ["Inspirasi", "Panduan", "Cerita"], action: "Kelola" },
  { key: "navigation", title: "Navigasi & Footer", description: "Atur menu, tautan, dan informasi footer", icon: Menu, tone: "bg-sky-50 text-sky-800", hints: ["Menu utama", "Grup footer", "Tautan bantuan"], action: "Kelola" },
  { key: "media", title: "Pustaka Media", description: "Gambar dan aset visual toko", icon: Image, tone: "bg-amber-50 text-[#8A6420]", hints: [], action: "Buka pustaka media" },
];

function StatusBadge({ value }) {
  const styles = { published: "border-emerald-200 bg-emerald-50 text-emerald-800", draft: "border-stone-200 bg-stone-100 text-stone-700", archived: "border-amber-200 bg-amber-50 text-amber-800" };
  return <span className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold ${styles[value] || styles.draft}`}>{cmsStatusLabel(value)}</span>;
}

function LocaleState({ entry }) {
  return <div className="flex flex-wrap gap-1" aria-label="Kelengkapan bahasa">{LOCALES.map((locale) => <span key={locale} className={`inline-flex h-6 min-w-8 items-center justify-center rounded-md px-1.5 text-[10px] font-bold uppercase ${entry.completeness?.includes(locale) ? "bg-[#02422C]/10 text-[#02422C]" : "bg-stone-100 text-stone-400"}`}>{locale}</span>)}</div>;
}

function formatDate(value) {
  if (!value) return "Belum ada perubahan";
  return new Date(value).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" });
}

function countTypes(items, types) { return items.filter((entry) => types.includes(entry.content_type)).length; }
function countHomepageSections(items) { return items.filter((entry) => entry.content_type === "homepage_section" && CMS_PRODUCT_SECTION_KEYS.includes(entry.slug)).length; }
function recentEntries(items) { return [...items].sort((a, b) => new Date(b.updated_at || 0) - new Date(a.updated_at || 0)).slice(0, 3); }

function HubCard({ group, count, mediaCount, onOpen }) {
  const Icon = group.icon;
  const isMedia = group.key === "media";
  const unit = group.key === "homepage" ? "section produk" : group.key === "navigation" ? "item" : "konten";
  return (
    <article className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#02422C]/30 hover:shadow-md" data-testid={`cms-hub-card-${group.key}`}>
      <div className="flex items-start gap-4">
        <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl ${group.tone}`}><Icon className="h-6 w-6" aria-hidden="true" /></div>
        <div className="min-w-0 flex-1"><div className="flex items-start justify-between gap-3"><div><h2 className="font-brand text-xl font-semibold text-[#17392C]">{group.title}</h2><p className="mt-1 text-sm leading-5 text-stone-500">{group.description}</p></div><span className="shrink-0 rounded-full bg-[#F0F5EF] px-3 py-1 text-xs font-semibold text-[#02422C]">{isMedia ? `${mediaCount} aset` : `${count} ${unit}`}</span></div></div>
      </div>
      {group.hints.length ? <div className="mt-4 flex flex-wrap gap-2">{group.hints.map((hint) => <span key={hint} className="rounded-full bg-[#F5F3ED] px-3 py-1.5 text-xs text-[#315347]">{hint}</span>)}</div> : <p className="mt-4 text-xs text-stone-400">Unggah sekali, gunakan ulang di seluruh CMS.</p>}
      <button type="button" onClick={() => onOpen(group.key)} className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-xl bg-[#02422C] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#063723]" data-testid={`cms-hub-open-${group.key}`}>{group.action}<ArrowRight className="h-4 w-4" aria-hidden="true" /></button>
    </article>
  );
}

function HubOverview({ items, mediaCount, isLoading, isMediaLoading, isError, onRetry, onOpen }) {
  const counts = useMemo(() => ({ homepage: countHomepageSections(items), store: countTypes(items, ["announcement", "faq_item", "page"]), stories: countTypes(items, ["story"]), navigation: countTypes(items, ["nav_item", "footer_group", "footer_item", "footer_text"]) }), [items]);
  const recent = recentEntries(items);
  return (
    <div data-testid="cms-content-page" data-cms-view="hub" className="mx-auto max-w-7xl space-y-6 pb-8">
      <header className="flex flex-wrap items-end justify-between gap-5"><div><p className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8A6420]"><Sparkles className="h-3.5 w-3.5" aria-hidden="true" />CMS</p><h1 className="mt-2 font-brand text-3xl font-semibold tracking-tight text-[#17392C] sm:text-4xl">Konten toko</h1><p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500">Kelola tampilan dan informasi yang pelanggan lihat di toko.</p></div><Link to="/cms/new" data-testid="cms-new-button" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-[#063723]"><FilePlus2 className="h-4 w-4" aria-hidden="true" />Buat konten</Link></header>
      <label className="relative block" data-testid="cms-hub-search"><span className="sr-only">Cari konten</span><Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-stone-400" aria-hidden="true" /><input placeholder="Cari konten, halaman, atau topik…" className="h-12 w-full rounded-xl border border-[#E4DED2] bg-white pl-12 pr-4 text-sm outline-none transition focus:border-[#02422C] focus:ring-2 focus:ring-[#02422C]/10" onKeyDown={(event) => { if (event.key === "Enter" && event.currentTarget.value.trim()) onOpen("search", event.currentTarget.value.trim()); }} /></label>
      {isLoading || isMediaLoading ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="h-64 rounded-2xl" />)}</div> : isError ? <section className="rounded-2xl border border-red-200 bg-white px-6 py-14 text-center" data-testid="cms-content-error"><p className="font-semibold text-red-900">Konten toko belum dapat dimuat</p><p className="mt-1 text-sm text-stone-500">Periksa koneksi, lalu coba lagi. Data tidak diganti dengan angka nol.</p><button type="button" onClick={onRetry} className="mt-4 rounded-xl bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white">Coba lagi</button></section> : <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{HUB_GROUPS.map((group) => <HubCard key={group.key} group={group} count={counts[group.key] || 0} mediaCount={mediaCount} onOpen={onOpen} />)}</div>}
      <section className="rounded-2xl border border-[#E9E3D7] bg-white shadow-sm" data-testid="cms-recent-content"><div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#F0ECE4] px-5 py-4 sm:px-6"><div><h2 className="font-brand text-xl font-semibold text-[#17392C]">Terakhir diubah</h2><p className="mt-1 text-sm text-stone-500">Akses cepat ke konten yang baru diperbarui.</p></div><button type="button" onClick={() => onOpen("all")} className="inline-flex items-center gap-1 text-sm font-semibold text-[#02422C] hover:underline">Lihat semua <ArrowRight className="h-4 w-4" aria-hidden="true" /></button></div><div className="divide-y divide-[#F0ECE4]">{recent.length ? recent.map((entry) => <Link key={entry.id} to={`/cms/${entry.id}`} className="flex items-center gap-4 px-5 py-4 transition hover:bg-[#FDFBF6] sm:px-6" data-testid={`cms-recent-${entry.id}`}><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[#F0F5EF] text-[#02422C]"><FileText className="h-5 w-5" aria-hidden="true" /></div><div className="min-w-0 flex-1"><p className="truncate text-sm font-semibold text-[#17392C]">{entry.internal_name}</p><p className="mt-1 text-xs text-stone-500">{cmsTypeLabel(entry.content_type)} · {formatDate(entry.updated_at)}</p></div><ChevronRight className="h-4 w-4 shrink-0 text-stone-400" aria-hidden="true" /></Link>) : <div className="px-6 py-12 text-center text-sm text-stone-500">Belum ada konten.</div>}</div></section>
    </div>
  );
}

function LegacyContentList({ setFilter, type, status, page, searchText, setSearchText, data, isLoading, isError, refetch, isFetching }) {
  const items = data?.items || [];
  const total = data?.total || 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  return (
    <div data-testid="cms-content-list" className="mx-auto max-w-7xl space-y-5 pb-8">
      <div className="flex flex-wrap items-end justify-between gap-4"><div><button type="button" onClick={() => setFilter("view", "")} className="mb-3 inline-flex items-center gap-2 text-sm font-semibold text-[#02422C] hover:underline"><ChevronLeft className="h-4 w-4" aria-hidden="true" />Kembali ke Content Hub</button><p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8A6420]">CMS</p><h1 className="mt-1 font-brand text-3xl font-semibold text-[#17392C]">Semua konten</h1><p className="mt-1 text-sm text-stone-500">Kelola konten berdasarkan jenis, status, dan bahasa.</p></div><Link to="/cms/new" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white"><FilePlus2 className="h-4 w-4" aria-hidden="true" />Buat konten</Link></div>
      <section className="rounded-xl border border-[#E9E3D7] bg-[#FDFBF6] p-4 shadow-sm"><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-[minmax(240px,1fr)_240px_200px_auto]"><label className="relative block"><span className="sr-only">Cari nama atau slug</span><Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" /><input value={searchText} onChange={(event) => { setSearchText(event.target.value); if (!event.target.value) setFilter("q", ""); }} onKeyDown={(event) => { if (event.key === "Enter") setFilter("q", searchText.trim()); }} placeholder="Cari nama atau slug…" className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white pl-10 pr-3 text-sm outline-none focus:border-[#02422C]" data-testid="cms-search" /></label><label><span className="sr-only">Jenis konten</span><select value={type} onChange={(event) => setFilter("type", event.target.value)} className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white px-3 text-sm" data-testid="cms-type-filter"><option value="">Semua jenis</option>{CMS_CONTENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label><label><span className="sr-only">Status publikasi</span><select value={status} onChange={(event) => setFilter("status", event.target.value)} className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white px-3 text-sm" data-testid="cms-status-filter"><option value="">Semua status</option><option value="draft">Draft</option><option value="published">Tayang</option><option value="archived">Diarsipkan</option></select></label><div className="flex items-center justify-end text-xs text-stone-500" aria-live="polite">{isFetching && !isLoading ? <span className="mr-2 h-2 w-2 animate-pulse rounded-full bg-[#CD9B3A]" /> : null}{total} konten</div></div></section>
      <section className="overflow-hidden rounded-xl border border-[#E9E3D7] bg-white shadow-sm" aria-label="Daftar konten">
        {isError ? <div className="px-6 py-14 text-center" data-testid="cms-content-error"><p className="font-semibold text-stone-800">Konten belum dapat dimuat</p><p className="mt-1 text-sm text-stone-500">Periksa koneksi, lalu coba lagi.</p><button type="button" onClick={() => refetch()} className="mt-4 rounded-lg bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white">Coba lagi</button></div> : null}
        {isLoading ? <div className="space-y-3 p-5" data-testid="cms-content-loading">{Array.from({ length: 6 }).map((_, index) => <Skeleton key={index} className="h-14 w-full rounded-lg" />)}</div> : null}
        {!isLoading && !isError && items.length ? <>
          <div className="space-y-3 p-3 md:hidden" data-testid="cms-content-mobile-list">
            {items.map((entry) => (
              <article key={entry.id} className="rounded-lg border border-[#E9E3D7] p-3" data-testid={`cms-mobile-row-${entry.slug || entry.id}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link to={`/cms/${entry.id}`} className="break-words text-sm font-semibold text-[#17392C] hover:text-[#8A6420]" data-testid={`cms-mobile-edit-${entry.slug || entry.id}`}>{entry.internal_name}</Link>
                    <p className="mt-1 break-all text-xs text-stone-500">{entry.slug || "Tanpa slug"}</p>
                  </div>
                  <StatusBadge value={entry.status} />
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-[#F0ECE4] pt-3 text-xs">
                  <span className="rounded-md bg-[#F4F1E9] px-2 py-1 font-medium text-stone-700">{cmsTypeLabel(entry.content_type)}</span>
                  <LocaleState entry={entry} />
                  <span className="text-stone-500">{formatDate(entry.updated_at)}</span>
                  {entry.has_unpublished_changes ? <span className="rounded-full bg-[#FBF1D8] px-2 py-1 font-semibold text-[#855E17]">Belum tayang</span> : null}
                  {!entry.is_visible ? <span className="rounded-full bg-stone-100 px-2 py-1 text-stone-500">Disembunyikan</span> : null}
                </div>
                <Link to={`/cms/${entry.id}`} className="mt-3 inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-[#02422C]/25 text-sm font-semibold text-[#02422C]">Buka konten</Link>
              </article>
            ))}
          </div>
          <div className="hidden overflow-x-auto md:block"><table className="w-full min-w-[760px] text-left text-sm"><thead className="bg-[#F8F5EE] text-[10px] font-semibold uppercase tracking-[0.16em] text-stone-500"><tr><th className="px-5 py-3.5">Nama / slug</th><th className="px-4 py-3.5">Jenis</th><th className="px-4 py-3.5">Status</th><th className="px-4 py-3.5">Bahasa</th><th className="px-4 py-3.5">Terakhir diubah</th><th className="px-5 py-3.5"><span className="sr-only">Aksi</span></th></tr></thead><tbody className="divide-y divide-[#F0ECE4]">{items.map((entry) => <tr key={entry.id} className="transition-colors hover:bg-[#FDFBF6]" data-testid={`cms-row-${entry.slug || entry.id}`}><td className="px-5 py-4"><Link to={`/cms/${entry.id}`} className="font-semibold text-[#17392C] hover:text-[#8A6420]" data-testid={`cms-edit-${entry.slug || entry.id}`}>{entry.internal_name}</Link><div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-stone-400"><span>{entry.slug || "Tanpa slug"}</span>{entry.has_unpublished_changes ? <span className="rounded-full bg-[#FBF1D8] px-2 py-0.5 font-semibold text-[#855E17]">Perubahan belum tayang</span> : null}{!entry.is_visible ? <span className="rounded-full bg-stone-100 px-2 py-0.5 text-stone-500">Disembunyikan</span> : null}</div></td><td className="px-4 py-4"><span className="rounded-md bg-[#F4F1E9] px-2.5 py-1.5 text-xs font-medium text-stone-700">{cmsTypeLabel(entry.content_type)}</span></td><td className="px-4 py-4"><StatusBadge value={entry.status} /></td><td className="px-4 py-4"><LocaleState entry={entry} /></td><td className="px-4 py-4 text-xs text-stone-500">{formatDate(entry.updated_at)}</td><td className="px-5 py-4 text-right"><Link to={`/cms/${entry.id}`} className="text-xs font-bold uppercase tracking-wide text-[#02422C] hover:underline">Buka</Link></td></tr>)}</tbody></table></div>
          <footer className="flex flex-wrap items-center justify-between gap-3 border-t border-[#F0ECE4] bg-[#FDFBF6] px-4 py-3.5 sm:px-5"><p className="text-xs text-stone-500">Menampilkan {Math.min((page - 1) * PAGE_SIZE + 1, total)}–{Math.min(page * PAGE_SIZE, total)} dari {total}</p><div className="ml-auto flex items-center gap-2"><button type="button" onClick={() => setFilter("page", String(Math.max(1, page - 1)))} disabled={page <= 1} aria-label="Halaman sebelumnya" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-[#E4DED2] bg-white text-stone-600 disabled:cursor-not-allowed disabled:opacity-40" data-testid="cms-page-prev"><ChevronLeft className="h-4 w-4" aria-hidden="true" /></button><span className="min-w-20 text-center text-xs font-medium text-stone-600">Halaman {page} / {pageCount}</span><button type="button" onClick={() => setFilter("page", String(Math.min(pageCount, page + 1)))} disabled={page >= pageCount} aria-label="Halaman berikutnya" className="inline-flex h-11 w-11 items-center justify-center rounded-lg border border-[#E4DED2] bg-white text-stone-600 disabled:cursor-not-allowed disabled:opacity-40" data-testid="cms-page-next"><ChevronRight className="h-4 w-4" aria-hidden="true" /></button></div></footer>
        </> : null}
        {!isLoading && !isError && !items.length ? <div className="px-6 py-16 text-center" data-testid="cms-content-empty"><div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#F4F1E9] text-[#02422C]"><Search className="h-5 w-5" aria-hidden="true" /></div><h2 className="mt-4 font-brand text-xl font-semibold text-[#17392C]">Belum ada konten yang cocok</h2><p className="mt-1 text-sm text-stone-500">Ubah filter atau buat konten baru untuk toko.</p><Link to="/cms/new" className="mt-4 inline-flex items-center gap-2 rounded-lg bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white"><FilePlus2 className="h-4 w-4" aria-hidden="true" />Buat konten</Link></div> : null}
      </section>
    </div>
  );
}

export default function CmsContentPage() {
  const [params, setParams] = useSearchParams();
  const type = params.get("type") || "";
  const status = params.get("status") || "";
  const q = params.get("q") || "";
  const view = params.get("view") || "";
  const page = Math.max(1, Number(params.get("page") || 1));
  const showList = view === "all" || Boolean(type || status || q);
  const [searchText, setSearchText] = useState(q);
  function setFilter(key, value) { const next = new URLSearchParams(params); if (value) next.set(key, value); else next.delete(key); if (key !== "page") next.delete("page"); setParams(next); }
  const contentQuery = useQuery({ queryKey: ["cms-content", { type, status, q, page, showList }], queryFn: () => getCmsContent({ type: type || undefined, status: status || undefined, q: q || undefined, page: showList ? page : 1, page_size: showList ? PAGE_SIZE : 100 }), placeholderData: (previous) => previous });
  const mediaQuery = useQuery({ queryKey: ["cms-media-summary"], queryFn: () => getCmsMedia({ page: 1, page_size: 1 }), enabled: !showList });
  function openGroup(key, value) {
    if (key === "media") { window.location.assign("/admin/media"); return; }
    if (key === "search") { setParams(new URLSearchParams({ view: "all", q: value })); return; }
    if (key === "all") { setParams(new URLSearchParams({ view: "all" })); return; }
    if (key === "homepage") { window.location.assign("/admin/cms/homepage"); return; }
    if (key === "stories") { window.location.assign("/admin/cms/stories"); return; }
    if (key === "store") { window.location.assign("/admin/cms/help"); return; }
    if (key === "navigation") { window.location.assign("/admin/cms/navigation"); return; }
    const next = new URLSearchParams({ view: "all" });
    if (key === "stories") next.set("type", "story");
    if (key === "store") next.set("type", "page");
    if (key === "navigation") next.set("type", "nav_item");
    setParams(next);
  }
  if (showList) return <LegacyContentList setFilter={setFilter} type={type} status={status} page={page} searchText={searchText} setSearchText={setSearchText} data={contentQuery.data} isLoading={contentQuery.isLoading} isError={contentQuery.isError} refetch={contentQuery.refetch} isFetching={contentQuery.isFetching} />;
  return <HubOverview items={contentQuery.data?.items || []} mediaCount={mediaQuery.data?.total || 0} isLoading={contentQuery.isLoading} isMediaLoading={mediaQuery.isLoading} isError={contentQuery.isError} onRetry={contentQuery.refetch} onOpen={openGroup} />;
}
