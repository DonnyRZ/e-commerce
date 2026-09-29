import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronRight,
  FilePlus2,
  FileText,
  HelpCircle,
  LayoutDashboard,
  Menu,
  Search,
  Store,
} from "lucide-react";
import { getCmsContent } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import {
  CMS_PRODUCT_SECTION_KEYS,
  cmsSectionLabel,
  cmsStatusLabel,
  cmsTypeLabel,
} from "./cmsContentSchema";

function useContent(type) {
  return useQuery({
    queryKey: ["cms-workspace", type],
    queryFn: () => getCmsContent({ type, page: 1, page_size: 100 }),
  });
}

function StatusPill({ status }) {
  const color =
    status === "published"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800"
      : status === "draft"
        ? "border-stone-200 bg-stone-100 text-stone-700"
        : "border-amber-200 bg-amber-50 text-amber-800";
  return (
    <span className={"inline-flex rounded-full border px-2.5 py-1 text-[11px] font-semibold " + color}>
      {cmsStatusLabel(status)}
    </span>
  );
}

function PageFrame({ eyebrow = "CMS", title, description, back = true, action, children, testId }) {
  return (
    <div data-testid={testId} className="mx-auto max-w-7xl space-y-6 pb-8">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          {back ? (
            <Link to="/cms" className="mb-4 inline-flex items-center gap-2 text-sm font-semibold text-[#02422C] hover:underline">
              <ArrowLeft className="h-4 w-4" aria-hidden="true" />
              Kembali ke Content Hub
            </Link>
          ) : null}
          <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#8A6420]">{eyebrow}</p>
          <h1 className="mt-2 font-brand text-3xl font-semibold tracking-tight text-[#17392C] sm:text-4xl">{title}</h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500">{description}</p>
        </div>
        {action}
      </header>
      {children}
    </div>
  );
}

function LoadingCards({ count = 4 }) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      {Array.from({ length: count }).map((_, index) => (
        <Skeleton key={index} className="h-32 rounded-2xl" />
      ))}
    </div>
  );
}

function ErrorCard({ onRetry }) {
  return (
    <div className="rounded-2xl border border-red-200 bg-white px-6 py-12 text-center">
      <p className="font-semibold text-red-900">Konten gagal dimuat.</p>
      <p className="mt-1 text-sm text-stone-500">Periksa koneksi, lalu coba lagi.</p>
      <button type="button" onClick={onRetry} className="mt-4 rounded-xl bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white">
        Coba lagi
      </button>
    </div>
  );
}

function EntryLink({ entry, createType = "homepage_section", createSlug = "", children = "Buka" }) {
  const query = createSlug ? "&slug=" + encodeURIComponent(createSlug) : "";
  const to = entry ? "/cms/" + entry.id : "/cms/new?type=" + createType + query;
  return (
    <Link to={to} className="inline-flex items-center gap-1 text-sm font-semibold text-[#02422C] hover:underline">
      {children}
      <ArrowRight className="h-4 w-4" aria-hidden="true" />
    </Link>
  );
}

function HomepageRow({ icon: Icon, label, description, entry, createType, createSlug, number, testId, meta }) {
  return (
    <div data-testid={testId} className="flex items-center gap-4 rounded-xl border border-[#E9E3D7] bg-white p-4">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#F4F1E9] text-[#8A6420]">
        <Icon className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          {number ? <span className="text-xs font-semibold text-stone-400">{number}.</span> : null}
          <p className="font-semibold text-[#17392C]">{label}</p>
        </div>
        <p className="mt-1 text-xs text-stone-500">{description}</p>
        {meta ? <p className="mt-1 text-xs font-medium text-[#8A6420]">{meta}</p> : null}
      </div>
      {entry ? <StatusPill status={entry.status} /> : <span className="text-xs font-medium text-stone-400">Belum dibuat</span>}
      <EntryLink entry={entry} createType={createType} createSlug={createSlug}>{entry ? "Edit" : "Buat"}</EntryLink>
    </div>
  );
}

export function CmsHomepageWorkspace() {
  const query = useQuery({
    queryKey: ["cms-homepage-workspace"],
    queryFn: () => getCmsContent({ page: 1, page_size: 100 }),
  });
  const entries = useMemo(() => query.data?.items || [], [query.data?.items]);
  const hero = entries.find((entry) => entry.content_type === "hero");
  const departmentVisuals = useMemo(
    () => entries.filter((entry) => entry.content_type === "department_visual"),
    [entries],
  );
  const productSections = useMemo(() => {
    const bySlug = new Map(
      entries
        .filter((entry) => entry.content_type === "homepage_section" && CMS_PRODUCT_SECTION_KEYS.includes(entry.slug))
        .map((entry) => [entry.slug, entry]),
    );
    return CMS_PRODUCT_SECTION_KEYS.map((key) => ({ key, entry: bySlug.get(key) }));
  }, [entries]);
  const department = departmentVisuals[0];

  if (query.isLoading) {
    return (
      <PageFrame title="Homepage" description="Atur tampilan halaman utama toko" testId="cms-homepage-workspace">
        <LoadingCards count={6} />
      </PageFrame>
    );
  }
  if (query.isError) {
    return (
      <PageFrame title="Homepage" description="Atur tampilan halaman utama toko" testId="cms-homepage-workspace">
        <ErrorCard onRetry={query.refetch} />
      </PageFrame>
    );
  }

  return (
    <PageFrame
      title="Homepage"
      description="Atur konten utama yang pelanggan lihat saat membuka toko."
      testId="cms-homepage-workspace"
      action={
        <div className="flex flex-wrap gap-2">
          <a href="/" target="_blank" rel="noreferrer" className="inline-flex h-11 items-center gap-2 rounded-xl border border-[#D9D0C0] bg-white px-4 text-sm font-semibold text-[#17392C]">
            Lihat toko
          </a>
          <Link to="/cms?view=all" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white">
            <FileText className="h-4 w-4" aria-hidden="true" />
            Semua konten
          </Link>
        </div>
      }
    >
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(320px,0.8fr)]">
        <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm sm:p-6">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="font-brand text-2xl font-semibold text-[#17392C]">Susunan homepage</h2>
              <p className="mt-1 text-sm text-stone-500">Atur konten sesuai urutan tampil di halaman utama.</p>
            </div>
            <span className="rounded-full bg-[#F0F5EF] px-3 py-1.5 text-xs font-semibold text-[#02422C]">6 area utama</span>
          </div>

          <div className="mt-5 space-y-3">
            <HomepageRow
              icon={LayoutDashboard}
              label="Hero utama"
              description="Pesan utama yang tampil paling atas."
              entry={hero}
              createType="hero"
              createSlug="home-hero"
              testId="cms-homepage-row-hero"
            />
            <HomepageRow
              icon={Store}
              label="Department"
              description="Visual kartu departemen yang tampil di homepage."
              entry={department}
              createType="department_visual"
              meta={departmentVisuals.length ? departmentVisuals.length + " visual departemen" : null}
              testId="cms-homepage-row-department"
            />
            {productSections.map(({ key, entry }, index) => (
              <HomepageRow
                key={key}
                icon={Store}
                label={cmsSectionLabel(key)}
                description="Daftar produk pilihan yang diatur manual dari katalog."
                entry={entry}
                createType="homepage_section"
                createSlug={key}
                number={index + 1}
                meta={entry?.payload?.product_ids ? entry.payload.product_ids.length + " produk" : null}
                testId={"cms-homepage-row-" + key}
              />
            ))}
          </div>

          <div className="mt-5 rounded-xl border border-dashed border-[#D9D0C0] bg-[#FDFBF6] p-5 text-center text-sm text-stone-500">
            Hero dan Department berada di bagian atas, lalu empat section produk tampil sesuai urutan merchandising.
          </div>
        </section>

        <aside className="space-y-5">
          <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm">
            <h2 className="font-brand text-xl font-semibold text-[#17392C]">Pengaturan cepat</h2>
            <p className="mt-1 text-sm leading-5 text-stone-500">Buka editor untuk area homepage yang paling sering diperbarui.</p>
            <div className="mt-5 space-y-3">
              {hero ? (
                <Link to={"/cms/" + hero.id} className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-3 transition hover:bg-[#FDFBF6]">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#F0F5EF] text-[#02422C]">
                    <LayoutDashboard className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <span className="flex-1 text-sm font-semibold text-[#17392C]">Edit hero utama</span>
                  <ChevronRight className="h-4 w-4 text-stone-400" aria-hidden="true" />
                </Link>
              ) : null}
              {department ? (
                <Link to={"/cms/" + department.id} className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-3 transition hover:bg-[#FDFBF6]">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-[#F8F1DE] text-[#8A6420]">
                    <Store className="h-4 w-4" aria-hidden="true" />
                  </div>
                  <span className="flex-1 text-sm font-semibold text-[#17392C]">Edit department</span>
                  <ChevronRight className="h-4 w-4 text-stone-400" aria-hidden="true" />
                </Link>
              ) : null}
              <a href="/" target="_blank" rel="noreferrer" className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-3 transition hover:bg-[#FDFBF6]">
                <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-sky-50 text-sky-800">
                  <Check className="h-4 w-4" aria-hidden="true" />
                </div>
                <span className="flex-1 text-sm font-semibold text-[#17392C]">Pratinjau homepage</span>
                <ChevronRight className="h-4 w-4 text-stone-400" aria-hidden="true" />
              </a>
            </div>
          </section>
          <section className="rounded-2xl border border-[#E9E3D7] bg-[#FDFBF6] p-5">
            <p className="text-sm leading-6 text-stone-600">Perubahan disimpan sebagai draft dan baru tampil di toko setelah dipublikasikan dari editor.</p>
          </section>
        </aside>
      </div>
    </PageFrame>
  );
}

export function CmsStoriesWorkspace() {
  const query = useContent("story");
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const items = (query.data?.items || []).filter(
    (entry) =>
      (filter === "all" || entry.status === filter) &&
      entry.internal_name.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <PageFrame
      title="Stories & Editorial"
      description="Kelola inspirasi dan panduan untuk pelanggan"
      testId="cms-stories-workspace"
      action={
        <Link to="/cms/new" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white">
          <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          Buat story
        </Link>
      }
    >
      <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-[#E9E3D7] bg-white p-4 shadow-sm">
        <label className="relative min-w-0 w-full flex-1 sm:min-w-60">
          <span className="sr-only">Cari judul atau topik</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-stone-400" aria-hidden="true" />
          <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Cari judul atau topik…" className="h-11 w-full rounded-lg border border-[#E4DED2] bg-white pl-9 pr-3 text-sm" />
        </label>
        <div className="flex rounded-lg bg-[#F5F3ED] p-1">
          <button type="button" onClick={() => setFilter("all")} className={"min-h-11 rounded-md px-3 text-xs font-semibold " + (filter === "all" ? "bg-white text-[#02422C] shadow-sm" : "text-stone-500")}>Semua ({query.data?.total || 0})</button>
          <button type="button" onClick={() => setFilter("published")} className={"min-h-11 rounded-md px-3 text-xs font-semibold " + (filter === "published" ? "bg-white text-[#02422C] shadow-sm" : "text-stone-500")}>Tayang</button>
          <button type="button" onClick={() => setFilter("draft")} className={"min-h-11 rounded-md px-3 text-xs font-semibold " + (filter === "draft" ? "bg-white text-[#02422C] shadow-sm" : "text-stone-500")}>Draft</button>
        </div>
      </div>
      {query.isLoading ? (
        <LoadingCards count={4} />
      ) : query.isError ? (
        <ErrorCard onRetry={query.refetch} />
      ) : (
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          {items.map((entry, index) => (
            <article key={entry.id} className="overflow-hidden rounded-2xl border border-[#E9E3D7] bg-white shadow-sm">
              <div className={"flex h-32 items-end bg-gradient-to-br " + (index % 3 === 0 ? "from-[#DCE8DF] to-[#F6EFE1]" : index % 3 === 1 ? "from-[#EEE4D7] to-[#E4E9E0]" : "from-[#E7DFED] to-[#F7F1E4]") + " p-4"}>
                <span className="rounded-full bg-white/85 px-2.5 py-1 text-[11px] font-semibold text-[#315347]">{entry.content_type === "story" ? "Editorial" : cmsTypeLabel(entry.content_type)}</span>
              </div>
              <div className="p-5">
                <h2 className="font-brand text-xl font-semibold leading-tight text-[#17392C]">{entry.internal_name}</h2>
                <p className="mt-3 text-xs text-stone-500">Diperbarui {new Date(entry.updated_at).toLocaleDateString("id-ID", { day: "numeric", month: "short", year: "numeric" })}</p>
                <div className="mt-4 flex items-center justify-between"><StatusPill status={entry.status} /><EntryLink entry={entry}>{entry.status === "draft" ? "Edit" : "Buka"}</EntryLink></div>
              </div>
            </article>
          ))}
          {!items.length ? <div className="col-span-full rounded-2xl border border-dashed border-[#D9D0C0] bg-white p-12 text-center text-sm text-stone-500">Belum ada story yang cocok.</div> : null}
        </div>
      )}
      <p className="rounded-xl border border-[#D6E8DF] bg-[#F7FBF8] px-5 py-4 text-sm text-[#315347]">Story yang tayang dapat muncul di homepage dan halaman Stories.</p>
    </PageFrame>
  );
}

export function CmsHelpWorkspace() {
  const faq = useContent("faq_item");
  const pages = useContent("page");
  const loading = faq.isLoading || pages.isLoading;
  const error = faq.isError || pages.isError;
  return (
    <PageFrame
      title="FAQ & Halaman informasi"
      description="Kelola jawaban dan informasi yang membantu pelanggan"
      testId="cms-help-workspace"
      action={
        <Link to="/cms/new" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white">
          <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          Buat konten
        </Link>
      }
    >
      {loading ? (
        <LoadingCards count={4} />
      ) : error ? (
        <ErrorCard onRetry={() => { faq.refetch(); pages.refetch(); }} />
      ) : (
        <div className="grid gap-6 lg:grid-cols-2">
          <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-50 text-[#02422C]"><HelpCircle className="h-5 w-5" aria-hidden="true" /></div><div><h2 className="font-brand text-2xl font-semibold text-[#17392C]">FAQ</h2><p className="mt-1 text-sm text-stone-500">Pertanyaan yang sering diajukan pelanggan.</p></div></div>
            <div className="mt-5 space-y-3">{(faq.data?.items || []).map((entry) => <Link key={entry.id} to={"/cms/" + entry.id} className="block rounded-xl border border-[#E9E3D7] p-4 transition hover:bg-[#FDFBF6]"><div className="flex items-start justify-between gap-3"><p className="font-semibold text-[#17392C]">{entry.internal_name}</p><ChevronRight className="h-4 w-4 shrink-0 text-stone-400" aria-hidden="true" /></div><div className="mt-3"><StatusPill status={entry.status} /></div></Link>)}</div>
          </section>
          <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F8F1DE] text-[#8A6420]"><FileText className="h-5 w-5" aria-hidden="true" /></div><div><h2 className="font-brand text-2xl font-semibold text-[#17392C]">Halaman informasi</h2><p className="mt-1 text-sm text-stone-500">Informasi penting untuk pelanggan.</p></div></div>
            <div className="mt-5 space-y-3">{(pages.data?.items || []).map((entry) => <Link key={entry.id} to={"/cms/" + entry.id} className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-4 transition hover:bg-[#FDFBF6]"><div className="min-w-0 flex-1"><p className="font-semibold text-[#17392C]">{entry.internal_name}</p><p className="mt-2 text-xs text-stone-500"><StatusPill status={entry.status} /></p></div><ChevronRight className="h-4 w-4 shrink-0 text-stone-400" aria-hidden="true" /></Link>)}</div>
          </section>
        </div>
      )}
      <p className="rounded-xl border border-[#E9E3D7] bg-[#FDFBF6] px-5 py-4 text-sm text-stone-600">Konten yang tayang dapat ditampilkan di footer, halaman bantuan, dan area informasi toko.</p>
    </PageFrame>
  );
}

export function CmsNavigationWorkspace() {
  const nav = useContent("nav_item");
  const groups = useContent("footer_group");
  const links = useContent("footer_item");
  const loading = nav.isLoading || groups.isLoading || links.isLoading;
  const error = nav.isError || groups.isError || links.isError;
  return (
    <PageFrame
      title="Navigasi & Footer"
      description="Atur menu dan tautan yang membantu pelanggan menjelajahi toko"
      testId="cms-navigation-workspace"
      action={
        <Link to="/cms/new" className="inline-flex h-11 items-center gap-2 rounded-xl bg-[#02422C] px-4 text-sm font-semibold text-white">
          <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          Buat konten
        </Link>
      }
    >
      {loading ? (
        <LoadingCards count={4} />
      ) : error ? (
        <ErrorCard onRetry={() => { nav.refetch(); groups.refetch(); links.refetch(); }} />
      ) : (
        <>
          <div className="grid gap-6 lg:grid-cols-2">
            <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm">
              <div className="flex items-start gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-sky-50 text-sky-800"><Menu className="h-5 w-5" aria-hidden="true" /></div><div><h2 className="font-brand text-2xl font-semibold text-[#17392C]">Menu utama</h2><p className="mt-1 text-sm text-stone-500">Urutkan menu yang tampil di header toko.</p></div></div>
              <div className="mt-5 space-y-3">{(nav.data?.items || []).map((entry, index) => <Link key={entry.id} to={"/cms/" + entry.id} className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-4 transition hover:bg-[#FDFBF6]"><span className="text-xs font-semibold text-stone-400">{index + 1}</span><div className="min-w-0 flex-1"><p className="font-semibold text-[#17392C]">{entry.internal_name}</p><p className="mt-1 text-xs text-stone-500">Navigasi toko</p></div><StatusPill status={entry.status} /><ChevronRight className="h-4 w-4 shrink-0 text-stone-400" aria-hidden="true" /></Link>)}</div>
            </section>
            <section className="rounded-2xl border border-[#E9E3D7] bg-white p-5 shadow-sm">
              <div className="flex items-start gap-3"><div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#F8F1DE] text-[#8A6420]"><FileText className="h-5 w-5" aria-hidden="true" /></div><div><h2 className="font-brand text-2xl font-semibold text-[#17392C]">Footer</h2><p className="mt-1 text-sm text-stone-500">Kelompokkan tautan di bagian bawah toko.</p></div></div>
              <div className="mt-5 space-y-3">{(groups.data?.items || []).map((entry) => <Link key={entry.id} to={"/cms/" + entry.id} className="flex items-center gap-3 rounded-xl border border-[#E9E3D7] p-4 transition hover:bg-[#FDFBF6]"><div className="min-w-0 flex-1"><p className="font-semibold text-[#17392C]">{entry.internal_name}</p><p className="mt-1 text-xs text-stone-500">Tautan footer</p></div><StatusPill status={entry.status} /><ChevronRight className="h-4 w-4 shrink-0 text-stone-400" aria-hidden="true" /></Link>)}</div>
            </section>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900">Tautan yang disembunyikan tidak tampil di storefront, tetapi tetap tersimpan.</div>
        </>
      )}
    </PageFrame>
  );
}
