import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, Eye, ImageOff } from "lucide-react";
import { getCmsPreviewEntry } from "@/lib/api";
import { mediaUrl, pickCmsLocalized } from "@/lib/localize";
import { cmsTypeLabel } from "@/pages/admin/cmsContentSchema";
import { Skeleton } from "@/components/ui/skeleton";
import ImageWithFallback from "@/components/common/ImageWithFallback";

function PreviewLink({ href, children, className = "" }) {
  if (!href) return null;
  return href.startsWith("/")
    ? <Link to={href} className={className}>{children}</Link>
    : <a href={href} target="_blank" rel="noreferrer" className={className}>{children}</a>;
}

function PreviewBody({ entry, locale }) {
  const tr = entry.translations || {};
  const title = pickCmsLocalized(tr, locale);
  const eyebrow = pickCmsLocalized(tr, locale, "eyebrow");
  const subtitle = pickCmsLocalized(tr, locale, "subtitle");
  const description = pickCmsLocalized(tr, locale, "description");
  const body = pickCmsLocalized(tr, locale, "body") || description;
  const cta = pickCmsLocalized(tr, locale, "cta_label");
  const image = mediaUrl(entry.image_url);
  const imageAlt = pickCmsLocalized(tr, locale, "alt_text") || title;

  if (entry.content_type === "hero") return (
    <section className="relative isolate flex min-h-[28rem] items-end overflow-hidden bg-[#02422C] text-white sm:min-h-[36rem]" data-testid="cms-preview-hero">
      {image ? <ImageWithFallback src={image} alt={imageAlt} className="absolute inset-0 h-full w-full object-cover" /> : null}
      <div className="absolute inset-0 bg-gradient-to-t from-black/75 via-black/15 to-transparent" />
      <div className="relative max-w-3xl px-6 pb-10 pt-24 sm:px-12 sm:pb-14">
        {eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.2em] text-[#E7C77E]">{eyebrow}</p> : null}
        <h1 className="mt-3 font-brand text-4xl font-semibold leading-tight sm:text-6xl">{title}</h1>
        {subtitle ? <p className="mt-3 max-w-xl text-sm leading-6 text-white/80 sm:text-base">{subtitle}</p> : null}
        <div className="mt-6 flex flex-wrap gap-3"><PreviewLink href={entry.cta_url} className="inline-flex rounded-full bg-[#FDF7E9] px-5 py-3 text-sm font-bold text-[#17392C]">{cta || "Tombol utama"}<ArrowUpRight className="ml-2 h-4 w-4" /></PreviewLink>{entry.secondary_cta_url ? <PreviewLink href={entry.secondary_cta_url} className="rounded-full border border-white/70 px-5 py-3 text-sm font-semibold">{pickCmsLocalized(tr, locale, "secondary_cta_label") || "Tombol kedua"}</PreviewLink> : null}</div>
      </div>
    </section>
  );

  if (entry.content_type === "banner") return (
    <section className="relative isolate flex min-h-72 items-center overflow-hidden rounded-xl bg-[#02422C] text-white" data-testid="cms-preview-banner">
      {image ? <ImageWithFallback src={image} alt={imageAlt} className="absolute inset-0 h-full w-full object-cover" /> : null}
      <div className="absolute inset-0 bg-gradient-to-r from-[#02422C]/95 via-[#02422C]/65 to-transparent" />
      <div className="relative max-w-xl px-7 py-10 sm:px-12"><p className="text-xs font-bold uppercase tracking-[0.2em] text-[#E7C77E]">{eyebrow || "Promosi"}</p><h1 className="mt-2 font-brand text-3xl font-semibold sm:text-4xl">{title}</h1>{description ? <p className="mt-3 text-sm leading-6 text-white/80">{description}</p> : null}{cta ? <PreviewLink href={entry.cta_url} className="mt-5 inline-flex items-center border-b border-[#CD9B3A] pb-1 text-xs font-bold uppercase tracking-wider">{cta}<ArrowUpRight className="ml-2 h-4 w-4" /></PreviewLink> : null}</div>
    </section>
  );

  if (entry.content_type === "announcement") return <div className="rounded-lg bg-[#10231D] px-5 py-4 text-center text-sm font-medium text-white" data-testid="cms-preview-announcement">{title}</div>;

  if (entry.content_type === "nav_item" || entry.content_type === "footer_item") return <div className="flex items-center justify-between rounded-xl border border-[#E9E3D7] bg-white p-5" data-testid={`cms-preview-${entry.content_type}`}><span className="font-semibold text-[#17392C]">{title}</span><PreviewLink href={entry.cta_url} className="inline-flex items-center text-sm font-semibold text-[#02422C]">{cta || "Buka tautan"}<ArrowUpRight className="ml-2 h-4 w-4" /></PreviewLink></div>;

  if (entry.content_type === "footer_group") return <section className="rounded-xl border border-[#E9E3D7] bg-white p-6" data-testid="cms-preview-footer-group"><h1 className="font-brand text-2xl font-semibold text-[#17392C]">{title}</h1><p className="mt-2 text-sm text-stone-500">Grup ini akan menjadi judul untuk tautan footer yang memilih slug <code className="rounded bg-stone-100 px-1.5 py-0.5">{entry.slug}</code>.</p></section>;

  if (entry.content_type === "footer_text" || entry.content_type === "homepage_section") return <section className="rounded-xl border border-[#E9E3D7] bg-[#FDFBF6] p-8 text-center" data-testid={`cms-preview-${entry.content_type}`}><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#8A6420]">{entry.content_type === "footer_text" ? entry.placement === "home_stories" ? "Judul bagian cerita" : "Teks promosi footer" : `Urutan beranda · ${entry.sort_order + 1}`}</p><h1 className="mt-2 font-brand text-3xl font-semibold text-[#17392C]">{title}</h1>{description ? <p className="mt-3 text-sm text-stone-600">{description}</p> : null}</section>;

  if (entry.content_type === "department_visual") return <article className="max-w-sm overflow-hidden rounded-xl border border-[#E9E3D7] bg-white" data-testid="cms-preview-department-visual">{image ? <ImageWithFallback src={image} alt={imageAlt} className="aspect-[4/5] w-full object-cover" /> : <div className="flex aspect-[4/5] items-center justify-center bg-stone-100 text-stone-400"><ImageOff className="h-8 w-8" /></div>}<div className="p-4"><h1 className="font-semibold text-[#17392C]">{imageAlt || entry.slug}</h1><p className="mt-1 text-xs text-stone-500">Departemen: {entry.slug}</p></div></article>;

  if (entry.content_type === "faq_item") return <details open className="rounded-xl border border-[#E9E3D7] bg-white p-5" data-testid="cms-preview-faq"><summary className="cursor-pointer list-none text-base font-semibold text-[#17392C]">{title}</summary><p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-stone-600">{body}</p></details>;

  return <article className="mx-auto max-w-3xl rounded-xl border border-[#E9E3D7] bg-white p-6 sm:p-10" data-testid={`cms-preview-${entry.content_type}`}>
    {image ? <ImageWithFallback src={image} alt={imageAlt} className="mb-7 max-h-[28rem] w-full rounded-lg object-cover" /> : null}
    {eyebrow ? <p className="text-xs font-bold uppercase tracking-[0.18em] text-[#8A6420]">{eyebrow}</p> : null}
    <h1 className="mt-2 font-brand text-3xl font-semibold text-[#17392C] sm:text-4xl">{title}</h1>
    {subtitle ? <p className="mt-3 text-base text-stone-500">{subtitle}</p> : null}
    {body ? <div className="mt-6 whitespace-pre-wrap text-sm leading-7 text-stone-700">{body}</div> : null}
    {cta ? <PreviewLink href={entry.cta_url} className="mt-6 inline-flex items-center rounded-full bg-[#02422C] px-5 py-3 text-sm font-semibold text-white">{cta}<ArrowUpRight className="ml-2 h-4 w-4" /></PreviewLink> : null}
  </article>;
}

export default function CmsPreviewPage() {
  const { token } = useParams();
  const query = useQuery({ queryKey: ["cms", "preview", token], queryFn: () => getCmsPreviewEntry(token), enabled: Boolean(token), retry: false });
  const locale = new URLSearchParams(window.location.search).get("locale") || "en";

  useEffect(() => {
    const prior = document.title;
    document.title = query.data ? `Pratinjau: ${query.data.internal_name || "Konten"} · ShaniCantik` : "Pratinjau CMS · ShaniCantik";
    return () => { document.title = prior; };
  }, [query.data]);

  return (
    <div className="min-h-[70vh] bg-[#F7F4ED] px-4 py-8 sm:px-6 sm:py-12" data-testid="cms-preview-page">
      <div className="mx-auto max-w-5xl">
        <header className="mb-5 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#E9E3D7] bg-white px-4 py-3 shadow-sm sm:px-5">
          <div className="flex items-center gap-3"><span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#02422C]/10 text-[#02422C]"><Eye className="h-4 w-4" aria-hidden="true" /></span><div><p className="text-xs font-bold text-[#17392C]">Pratinjau privat</p><p className="text-[10px] text-stone-500">Hanya untuk pemeriksaan · belum tentu sudah tayang</p></div></div>
          <Link to="/" className="inline-flex items-center gap-1.5 text-xs font-semibold text-[#02422C] hover:underline"><ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />Kembali ke toko</Link>
        </header>
        {query.isLoading ? <div className="space-y-4"><Skeleton className="h-8 w-52" /><Skeleton className="h-96 w-full rounded-xl" /></div> : null}
        {query.isError ? <section className="rounded-xl border border-amber-200 bg-white px-6 py-16 text-center"><h1 className="font-brand text-2xl font-semibold text-[#17392C]">Pratinjau tidak tersedia</h1><p className="mx-auto mt-2 max-w-md text-sm leading-6 text-stone-500">Tautan mungkin sudah kedaluwarsa atau kontennya sudah dihapus. Kembali ke CMS untuk membuat tautan baru.</p><Link to="/" className="mt-5 inline-flex rounded-lg bg-[#02422C] px-4 py-2.5 text-sm font-semibold text-white">Kembali ke toko</Link></section> : null}
        {query.data ? <><div className="mb-3 flex flex-wrap items-center justify-between gap-2 px-1"><div><p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#8A6420]">{cmsTypeLabel(query.data.content_type)}</p><p className="text-xs text-stone-500">{query.data.internal_name} · {query.data.slug}</p></div><select value={locale} onChange={(event) => { const next = new URL(window.location.href); next.searchParams.set("locale", event.target.value); window.location.assign(next.toString()); }} aria-label="Bahasa pratinjau" className="h-9 rounded-lg border border-[#E4DED2] bg-white px-3 text-xs"><option value="en">English</option><option value="id">Indonesia</option><option value="uz">O'zbek</option><option value="ru">Русский</option></select></div><PreviewBody entry={query.data} locale={locale} /></> : null}
      </div>
    </div>
  );
}
