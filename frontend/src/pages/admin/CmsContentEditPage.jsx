import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ChevronDown, ExternalLink, History, ImagePlus, Info, Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  createCmsContent,
  deleteCmsContent,
  getCatalogTree,
  getCmsContent,
  getCmsContentEntry,
  getCmsMedia,
  getCmsPreviewToken,
  getCmsRevisions,
  restoreCmsRevision,
  setCmsContentStatus,
  updateCmsContent,
  uploadCmsMedia,
} from "@/lib/api";
import { mediaUrl, pickCmsLocalized } from "@/lib/localize";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";
import { inputClass } from "./adminUtils";
import {
  CMS_CONTENT_TYPES,
  CMS_LOCALES,
  CMS_MEDIA_TYPES,
  CMS_SECTION_KEYS,
  CMS_TRANSLATION_FIELDS,
  cmsStatusLabel,
  cmsTypeLabel,
} from "./cmsContentSchema";

const ALL_TRANSLATION_FIELDS = ["title", "eyebrow", "subtitle", "description", "body", "cta_label", "secondary_cta_label", "alt_text"];
const EMPTY_TRANSLATION = Object.fromEntries(ALL_TRANSLATION_FIELDS.map((field) => [field, ""]));
const LABELS = {
  title: "Judul / teks utama",
  eyebrow: "Label kecil (eyebrow)",
  subtitle: "Subjudul",
  description: "Deskripsi singkat",
  body: "Isi konten / jawaban",
  cta_label: "Teks tombol / tautan",
  secondary_cta_label: "Teks tombol kedua",
  alt_text: "Teks alternatif gambar",
};
const LOCALE_LABELS = { en: "English", id: "Indonesia", uz: "O'zbek", ru: "Русский" };
const REVISION_LABELS = { created: "dibuat", saved_draft: "draft disimpan", published: "diterbitkan", unpublished: "dijadikan draft", archived: "diarsipkan", restored: "dipulihkan" };
const TYPE_DESCRIPTIONS = {
  hero: "Area pembuka di beranda. Atur judul, gambar, dan tombol utama.",
  announcement: "Pesan singkat yang muncul di bar paling atas toko.",
  banner: "Materi promosi yang tampil tepat setelah hero beranda.",
  story: "Cerita editorial atau panduan yang tampil di bagian inspirasi.",
  page: "Halaman informasi seperti Tentang, Pengiriman, dan Kebijakan.",
  faq_item: "Satu pertanyaan beserta jawabannya di halaman Tanya Jawab.",
  nav_item: "Tautan di navigasi sekunder pada bagian header toko.",
  footer_group: "Judul kelompok tautan pada footer. Slug-nya menjadi kunci grup.",
  footer_item: "Satu tautan di dalam grup footer yang dipilih.",
  footer_text: "Judul bagian cerita atau kalimat promosi pada footer.",
  homepage_section: "Mengatur urutan bagian beranda. Bagian yang diarsipkan tidak ditampilkan.",
  department_visual: "Gambar pengganti untuk kartu salah satu departemen katalog.",
};
const MEDIA_TYPES = new Set(CMS_MEDIA_TYPES);
const URL_TYPES = new Set(["hero", "banner", "story", "nav_item", "footer_item"]);
const placementForType = (type) => ({
  announcement: "top",
  hero: "home",
  banner: "home_after_hero",
  story: "home_stories",
  nav_item: "secondary",
  footer_group: "footer",
  footer_item: "footer",
  footer_text: "footer",
  department_visual: "department",
}[type] || "");

function FormSection({ title, description, children, testId }) {
  return (
    <section data-testid={testId} className="rounded-xl border border-[#E9E3D7] bg-white p-5 shadow-sm sm:p-6">
      <div className="mb-5 border-b border-[#F0ECE4] pb-4">
        <h2 className="font-brand text-xl font-semibold text-[#17392C]">{title}</h2>
        {description ? <p className="mt-1 text-sm leading-6 text-stone-500">{description}</p> : null}
      </div>
      {children}
    </section>
  );
}

function FormLabel({ htmlFor, children, hint }) {
  return <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-semibold text-stone-700">{children}{hint ? <span className="ml-1 font-normal text-stone-400">{hint}</span> : null}</label>;
}

function MediaPicker({ onSelect, onClose }) {
  const [search, setSearch] = useState("");
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["cms-media", "picker", search],
    queryFn: () => getCmsMedia({ q: search.trim() || undefined, page_size: 48 }),
  });
  const [uploading, setUploading] = useState(false);

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const asset = await uploadCmsMedia(file);
      toast.success("Gambar berhasil diunggah");
      await refetch();
      onSelect(asset);
    } catch (error) {
      const detail = error?.response?.data?.detail;
      const code = typeof detail === "object" ? detail?.error : detail;
      toast.error(code === "file_too_large" ? "Ukuran gambar maksimal 5 MB." : code === "unsupported_media_type" ? "Gunakan gambar JPEG, PNG, atau WebP." : "Gambar gagal diunggah.");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mt-4 rounded-xl border border-[#DDD6C8] bg-[#FDFBF6] p-4" data-testid="media-picker">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div><p className="text-sm font-semibold text-[#17392C]">Pilih dari pustaka media</p><p className="mt-0.5 text-xs text-stone-500">Unggah sekali, gunakan ulang di seluruh CMS.</p></div>
        <div className="flex items-center gap-2">
          <label className={`inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg bg-[#02422C] px-3 text-xs font-semibold text-white transition hover:bg-[#063723] ${uploading ? "pointer-events-none opacity-60" : ""}`} data-testid="media-picker-upload">
            <ImagePlus className="h-3.5 w-3.5" aria-hidden="true" />{uploading ? "Mengunggah…" : "Unggah gambar"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="sr-only" onChange={upload} disabled={uploading} />
          </label>
          <button type="button" onClick={onClose} className="h-9 rounded-lg border border-[#DDD6C8] bg-white px-3 text-xs font-semibold text-stone-600 hover:bg-stone-50" data-testid="media-picker-close">Tutup</button>
        </div>
      </div>
      <input value={search} onChange={(event) => setSearch(event.target.value)} className="mt-4 h-10 w-full rounded-lg border border-[#E4DED2] bg-white px-3 text-sm outline-none focus:border-[#02422C]" placeholder="Cari nama file…" aria-label="Cari gambar" />
      {isError ? <div className="py-8 text-center text-sm text-stone-500">Pustaka media gagal dimuat. <button type="button" onClick={() => refetch()} className="font-semibold text-[#02422C] underline">Coba lagi</button></div> : null}
      <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
        {isLoading ? Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="aspect-square rounded-lg" />) : (data?.items || []).map((asset) => (
          <button key={asset.id} type="button" onClick={() => onSelect(asset)} className="group rounded-lg border border-[#E4DED2] bg-white p-2 text-left transition hover:border-[#02422C] hover:shadow-sm" data-testid={`media-pick-${asset.id}`}>
            <ImageWithFallback src={mediaUrl(asset.url)} alt={asset.translations?.en?.alt_text || asset.original_filename} className="aspect-square w-full rounded-md bg-stone-100 object-cover" loading="lazy" />
            <span className="mt-2 block truncate text-[11px] font-medium text-stone-700">{asset.original_filename}</span>
            <span className="mt-0.5 block text-[10px] text-stone-400">{asset.width && asset.height ? `${asset.width} × ${asset.height}` : "Gambar"} · dipakai {asset.usage_count}×</span>
          </button>
        ))}
      </div>
      {!isLoading && !isError && !(data?.items || []).length ? <p className="py-8 text-center text-sm text-stone-500">Belum ada gambar. Unggah gambar pertama untuk mulai.</p> : null}
    </div>
  );
}

function missingEnglish(type, form, translations) {
  const english = translations.en || {};
  const missing = [];
  if (type === "department_visual") {
    if (!english.alt_text?.trim()) missing.push("Teks alternatif gambar");
  } else if (!english.title?.trim()) missing.push("Judul / teks utama");
  if (type === "page" && !english.body?.trim() && !english.description?.trim()) missing.push("Isi halaman");
  if (type === "faq_item" && !english.body?.trim()) missing.push("Jawaban");
  if (type === "nav_item" && !form.cta_url.trim()) missing.push("Tautan navigasi");
  if (type === "footer_item" && !form.cta_url.trim()) missing.push("URL tautan");
  if (type === "footer_item" && !form.group?.trim()) missing.push("Grup footer");
  if (type === "homepage_section" && !CMS_SECTION_KEYS.includes(form.slug)) missing.push("Bagian homepage");
  if (type === "department_visual" && (!form.slug || !form.media_id)) missing.push("Departemen dan gambar");
  return missing;
}

export default function CmsContentEditPage() {
  const { entryId } = useParams();
  const isNew = !entryId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [contentType, setContentType] = useState("banner");
  const [form, setForm] = useState({ internal_name: "", slug: "", placement: "home_after_hero", sort_order: 0, is_visible: true, cta_url: "", secondary_cta_url: "", media_id: null, group: "" });
  const [translations, setTranslations] = useState({});
  const [activeLocale, setActiveLocale] = useState("en");
  const [payload, setPayload] = useState({});
  const [imagePreview, setImagePreview] = useState("");
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [baseline, setBaseline] = useState("");
  const baselineRef = useRef("");

  const entryQuery = useQuery({ queryKey: ["cms-content-entry", entryId], queryFn: () => getCmsContentEntry(entryId), enabled: !isNew });
  const revisionsQuery = useQuery({ queryKey: ["cms-revisions", entryId], queryFn: () => getCmsRevisions(entryId), enabled: !isNew });
  const groupsQuery = useQuery({ queryKey: ["cms-footer-groups"], queryFn: () => getCmsContent({ type: "footer_group", page_size: 100 }), enabled: contentType === "footer_item" });
  const departmentsQuery = useQuery({ queryKey: ["catalog-tree"], queryFn: getCatalogTree, enabled: contentType === "department_visual" });

  useEffect(() => {
    const entry = entryQuery.data;
    if (!entry) return;
    const working = entry.working_copy || entry;
    const nextType = entry.content_type;
    const nextForm = {
      internal_name: working.internal_name || "",
      slug: working.slug || "",
      placement: working.placement || "",
      sort_order: working.sort_order ?? 0,
      is_visible: working.is_visible !== false,
      cta_url: working.cta_url || "",
      secondary_cta_url: working.secondary_cta_url || "",
      media_id: working.media_id || null,
      group: working.payload?.group || "",
    };
    const nextTranslations = Object.fromEntries(CMS_LOCALES.map((locale) => [locale, { ...EMPTY_TRANSLATION, ...(working.translations?.[locale] || {}) }]));
    const nextPayload = working.payload || {};
    setContentType(nextType);
    setForm(nextForm);
    setTranslations(nextTranslations);
    setPayload(nextPayload);
    setImagePreview(working.image_url || "");
    const nextBaseline = JSON.stringify({ type: nextType, form: nextForm, translations: nextTranslations, payload: nextPayload });
    baselineRef.current = nextBaseline;
    setBaseline(nextBaseline);
  }, [entryQuery.data]);

  const entry = entryQuery.data;
  const status = entry?.status || "draft";
  const localeText = Object.fromEntries(CMS_LOCALES.map((locale) => [locale, { ...EMPTY_TRANSLATION, ...(translations[locale] || {}) }]));
  const formState = JSON.stringify({ type: contentType, form, translations: localeText, payload });
  const dirty = isNew || !baseline || formState !== baseline;
  const required = missingEnglish(contentType, form, localeText);
  const activeFields = CMS_TRANSLATION_FIELDS[contentType] || ["title"];

  const setFormValue = (key, value) => setForm((current) => ({ ...current, [key]: value }));
  const setTranslation = (field, value) => setTranslations((current) => ({
    ...current,
    [activeLocale]: { ...EMPTY_TRANSLATION, ...(current[activeLocale] || {}), [field]: value },
  }));

  function invalidateCms() {
    queryClient.invalidateQueries({ queryKey: ["cms-content"] });
    queryClient.invalidateQueries({ queryKey: ["cms-content-entry", entryId] });
    queryClient.invalidateQueries({ queryKey: ["cms-revisions", entryId] });
    queryClient.invalidateQueries({ queryKey: ["cms"] });
    queryClient.invalidateQueries({ queryKey: ["cms-footer-groups"] });
  }

  function buildPayload() {
    const nextPayload = { ...payload };
    delete nextPayload.image_url;
    if (contentType === "footer_item") nextPayload.group = form.group;
    else delete nextPayload.group;
    return {
      internal_name: form.internal_name.trim(),
      slug: form.slug.trim(),
      placement: contentType === "footer_text" ? form.placement : placementForType(contentType),
      sort_order: Number.parseInt(form.sort_order, 10) || 0,
      is_visible: Boolean(form.is_visible),
      media_id: form.media_id || null,
      cta_url: URL_TYPES.has(contentType) ? form.cta_url.trim() || null : null,
      secondary_cta_url: contentType === "hero" ? form.secondary_cta_url.trim() || null : null,
      payload: nextPayload,
      translations: Object.fromEntries(CMS_LOCALES.map((locale) => [locale, { ...EMPTY_TRANSLATION, ...(localeText[locale] || {}) }])),
    };
  }

  const errorMessage = (error) => {
    const detail = error?.response?.data?.detail;
    const code = typeof detail === "object" ? detail?.error : detail;
    const messages = {
      duplicate_slug: "Slug ini sudah digunakan oleh konten sejenis.",
      invalid_footer_group: "Pilih grup footer yang masih aktif.",
      footer_group_not_published: "Terbitkan grup footer sebelum tautannya.",
      footer_group_in_use: "Arsipkan atau pindahkan tautan footer yang masih memakai grup ini.",
      hero_already_published: "Arsipkan atau jadikan hero yang sedang tayang sebagai draft terlebih dahulu.",
      announcement_already_published: "Arsipkan atau jadikan pengumuman yang sedang tayang sebagai draft terlebih dahulu.",
      invalid_department: "Pilih departemen katalog yang tersedia.",
      invalid_homepage_section: "Pilih bagian homepage yang tersedia.",
      invalid_url: "URL harus berupa rute toko atau alamat HTTP/HTTPS yang aman.",
      content_must_be_archived: "Arsipkan konten terlebih dahulu sebelum menghapus permanen.",
      no_unpublished_changes: "Tidak ada perubahan tertunda untuk diterbitkan.",
    };
    if (code === "incomplete_english") return `Lengkapi konten wajib berbahasa Inggris: ${(detail.missing || []).join(", ")}.`;
    return messages[code] || (typeof detail === "string" ? detail : "Terjadi kesalahan. Periksa isian lalu coba lagi.");
  };

  async function persistDraft() {
    const saved = isNew
      ? await createCmsContent({ content_type: contentType, ...buildPayload() })
      : await updateCmsContent(entryId, buildPayload());
    if (isNew) {
      toast.success("Draft konten berhasil dibuat");
      invalidateCms();
      navigate(`/cms/${saved.id}`, { replace: true });
      return saved;
    }
    const currentFormState = JSON.stringify({ type: contentType, form, translations: localeText, payload });
    baselineRef.current = currentFormState;
    setBaseline(currentFormState);
    toast.success(status === "published" ? "Perubahan tersimpan sebagai draft; versi tayang tetap sama." : "Draft berhasil disimpan.");
    invalidateCms();
    await entryQuery.refetch();
    return saved;
  }

  async function save(event) {
    event?.preventDefault();
    if (saving) return;
    if (!form.internal_name.trim()) {
      toast.error("Nama internal wajib diisi.");
      return;
    }
    setSaving(true);
    try { await persistDraft(); }
    catch (error) { toast.error(errorMessage(error)); }
    finally { setSaving(false); }
  }

  async function changeStatus(action) {
    if (saving) return;
    const question = action === "publish"
      ? `Terbitkan ${entry?.has_unpublished_changes ? "perubahan ini" : "konten ini"}? Konten akan terlihat di toko.`
      : action === "archive"
        ? "Arsipkan konten ini? Konten tidak akan tampil di toko."
        : "Jadikan konten ini sebagai draft dan sembunyikan dari toko?";
    if (!window.confirm(question)) return;
    setSaving(true);
    try {
      if (dirty) await updateCmsContent(entryId, buildPayload());
      await setCmsContentStatus(entryId, action);
      toast.success(action === "publish" ? "Konten berhasil diterbitkan." : action === "archive" ? "Konten berhasil diarsipkan." : "Konten menjadi draft dan tidak tampil di toko.");
      invalidateCms();
      await entryQuery.refetch();
    } catch (error) { toast.error(errorMessage(error)); }
    finally { setSaving(false); }
  }

  async function removeContent() {
    if (!entry || status !== "archived") return;
    if (!window.confirm(`Hapus permanen “${form.internal_name}”? Revisi dan terjemahannya ikut dihapus. Tindakan ini tidak dapat dibatalkan.`)) return;
    setSaving(true);
    try {
      await deleteCmsContent(entryId);
      toast.success("Konten dihapus permanen.");
      invalidateCms();
      navigate("/cms", { replace: true });
    } catch (error) { toast.error(errorMessage(error)); }
    finally { setSaving(false); }
  }

  async function preview() {
    if (dirty) {
      toast.error("Simpan perubahan terlebih dahulu agar pratinjau sesuai dengan form.");
      return;
    }
    try {
      const { preview_page_url: previewUrl } = await getCmsPreviewToken(entryId);
      if (!previewUrl) throw new Error("preview_url_missing");
      window.open(new URL(previewUrl, window.location.origin).toString(), "_blank", "noopener,noreferrer");
    } catch { toast.error("Tautan pratinjau tidak dapat dibuat."); }
  }

  async function restore(revision) {
    if (!window.confirm(`Pulihkan versi ${revision.version_number} sebagai draft kerja? Versi yang sedang tayang tidak akan berubah.`)) return;
    setSaving(true);
    try {
      await restoreCmsRevision(entryId, revision.id);
      toast.success("Versi dipulihkan sebagai draft kerja.");
      invalidateCms();
      await entryQuery.refetch();
    } catch (error) { toast.error(errorMessage(error)); }
    finally { setSaving(false); }
  }

  if (!isNew && entryQuery.isLoading) return <div data-testid="cms-editor-loading" className="mx-auto max-w-6xl space-y-4"><Skeleton className="h-16 w-full rounded-xl" /><Skeleton className="h-96 w-full rounded-xl" /></div>;
  if (!isNew && entryQuery.isError) return <div className="rounded-xl border border-red-200 bg-white p-8 text-center"><p className="font-semibold">Konten gagal dimuat.</p><button type="button" onClick={() => entryQuery.refetch()} className="mt-3 rounded-lg bg-[#02422C] px-4 py-2 text-sm font-semibold text-white">Coba lagi</button></div>;

  const groups = (groupsQuery.data?.items || []).filter((group) => group.status !== "archived");
  const departments = departmentsQuery.data || [];
  const statusClasses = {
    draft: "bg-stone-100 text-stone-700",
    published: "bg-emerald-50 text-emerald-800",
    archived: "bg-amber-50 text-amber-800",
  };
  const localeMissing = activeLocale !== "en" && !Object.values(localeText[activeLocale] || {}).some((value) => String(value || "").trim());
  const statusActions = status === "draft" ? ["publish", "archive"] : status === "published" ? [...(entry?.has_unpublished_changes ? ["publish"] : []), "unpublish", "archive"] : ["publish"];

  return (
    <div data-testid="cms-content-editor" className="mx-auto max-w-7xl space-y-6 pb-28">
      <header className="relative overflow-hidden rounded-2xl bg-[#02422C] px-5 py-6 text-white shadow-sm sm:px-8 sm:py-8">
        <div className="absolute -right-8 -top-12 h-48 w-48 rounded-full border border-white/10" />
        <div className="relative">
          <Link to="/cms" className="inline-flex items-center gap-2 text-xs font-semibold text-white/75 transition hover:text-white" data-testid="cms-editor-back"><ArrowLeft className="h-4 w-4" aria-hidden="true" />Kembali ke konten</Link>
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <div><p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#E7C77E]">{isNew ? "Konten baru" : cmsTypeLabel(contentType)}</p><h1 className="mt-1 font-brand text-3xl font-semibold sm:text-4xl">{isNew ? "Rancang cerita toko" : form.internal_name || "Edit konten"}</h1></div>
            {!isNew ? <span className={`rounded-full px-3 py-1 text-xs font-bold ${statusClasses[status] || statusClasses.draft}`}>{cmsStatusLabel(status)}</span> : null}
            {entry?.has_unpublished_changes ? <span className="rounded-full bg-[#CD9B3A]/20 px-3 py-1 text-xs font-semibold text-[#F5D994]">Ada draft perubahan</span> : null}
          </div>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-white/75">{TYPE_DESCRIPTIONS[contentType]}</p>
        </div>
      </header>

      <form onSubmit={save} className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-5">
          <FormSection title="Identitas & penempatan" description="Tentukan nama internal dan lokasi konten ini di toko." testId="cms-editor-meta">
            <div className="grid gap-4 sm:grid-cols-2">
              {isNew ? <div className="sm:col-span-2"><FormLabel htmlFor="cms-type">Jenis konten</FormLabel><select id="cms-type" value={contentType} onChange={(event) => { const nextType = event.target.value; setContentType(nextType); setForm((current) => ({ ...current, placement: placementForType(nextType), slug: "", group: "" })); setPayload({}); }} className={inputClass} data-testid="cms-field-type">{CMS_CONTENT_TYPES.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></div> : null}
              <div className="sm:col-span-2"><FormLabel htmlFor="cms-name">Nama internal <span className="text-red-600">*</span></FormLabel><input id="cms-name" value={form.internal_name} onChange={(event) => setFormValue("internal_name", event.target.value)} required maxLength={255} className={inputClass} placeholder="Contoh: Banner koleksi Idulfitri" data-testid="cms-field-name" /></div>
              {contentType === "homepage_section" ? (
                <div><FormLabel htmlFor="cms-slug">Bagian homepage</FormLabel><select id="cms-slug" value={form.slug} onChange={(event) => setFormValue("slug", event.target.value)} className={inputClass} data-testid="cms-field-slug"><option value="">Pilih bagian</option>{CMS_SECTION_KEYS.map((key) => <option key={key} value={key}>{key.replaceAll("_", " ")}</option>)}</select></div>
              ) : contentType === "department_visual" ? (
                <div><FormLabel htmlFor="cms-slug">Departemen katalog</FormLabel><select id="cms-slug" value={form.slug} onChange={(event) => setFormValue("slug", event.target.value)} className={inputClass} data-testid="cms-field-slug"><option value="">Pilih departemen</option>{departments.map((department) => <option key={department.id} value={department.slug}>{pickCmsLocalized(department.translations, "en") || department.slug}</option>)}</select>{departmentsQuery.isLoading ? <p className="mt-1 text-[11px] text-stone-400">Memuat departemen…</p> : null}</div>
              ) : (
                <div><FormLabel htmlFor="cms-slug">Slug / alamat konten</FormLabel><input id="cms-slug" value={form.slug} onChange={(event) => setFormValue("slug", event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, "-"))} maxLength={160} className={inputClass} placeholder="Dibuat otomatis jika dikosongkan" data-testid="cms-field-slug" /></div>
              )}
              <div><FormLabel htmlFor="cms-order">Urutan tampil</FormLabel><input id="cms-order" type="number" min="0" max="100000" step="1" value={form.sort_order} onChange={(event) => setFormValue("sort_order", event.target.value)} className={inputClass} data-testid="cms-field-sort" /></div>
              {contentType === "footer_text" ? <div><FormLabel htmlFor="cms-placement">Lokasi teks</FormLabel><select id="cms-placement" value={form.placement} onChange={(event) => setFormValue("placement", event.target.value)} className={inputClass} data-testid="cms-field-placement"><option value="footer">Promosi footer</option><option value="home_stories">Judul bagian cerita</option></select></div> : null}
              {contentType === "footer_item" ? <div className="sm:col-span-2"><FormLabel htmlFor="cms-group">Grup footer <span className="text-red-600">*</span></FormLabel><select id="cms-group" value={form.group} onChange={(event) => setFormValue("group", event.target.value)} className={inputClass} data-testid="cms-field-group"><option value="">Pilih grup footer</option>{groups.map((group) => <option key={group.id} value={group.slug}>{group.internal_name} · {group.slug}{group.status === "draft" ? " (draft)" : ""}</option>)}</select>{groupsQuery.isLoading ? <p className="mt-1 text-[11px] text-stone-400">Memuat grup footer…</p> : null}</div> : null}
              {URL_TYPES.has(contentType) ? <div className="sm:col-span-2"><FormLabel htmlFor="cms-cta">{contentType === "nav_item" ? "Tujuan tautan" : contentType === "footer_item" ? "URL tautan" : "Tujuan tombol utama"}</FormLabel><input id="cms-cta" value={form.cta_url} onChange={(event) => setFormValue("cta_url", event.target.value)} maxLength={500} className={inputClass} placeholder="/shop, https://…, atau mailto:…" data-testid="cms-field-cta" /></div> : null}
              {contentType === "hero" ? <div className="sm:col-span-2"><FormLabel htmlFor="cms-cta2">Tujuan tombol kedua</FormLabel><input id="cms-cta2" value={form.secondary_cta_url} onChange={(event) => setFormValue("secondary_cta_url", event.target.value)} maxLength={500} className={inputClass} placeholder="/shop" data-testid="cms-field-cta2" /></div> : null}
              {contentType === "banner" ? <div className="sm:col-span-2 rounded-lg bg-[#F8F5EE] px-4 py-3 text-xs leading-5 text-stone-600"><Info className="mr-2 inline h-4 w-4 text-[#8A6420]" aria-hidden="true" />Banner published akan tampil di slot tetap tepat setelah hero homepage.</div> : null}
            </div>
            <label className="mt-5 flex cursor-pointer items-start gap-3 rounded-lg border border-[#E9E3D7] bg-[#FDFBF6] p-3.5 text-sm" data-testid="cms-field-visible-label"><input type="checkbox" checked={Boolean(form.is_visible)} onChange={(event) => setFormValue("is_visible", event.target.checked)} className="mt-0.5 h-4 w-4 accent-[#02422C]" data-testid="cms-field-visible" /><span><span className="block font-semibold text-stone-800">Tampilkan saat published</span><span className="mt-0.5 block text-xs text-stone-500">Matikan untuk menyembunyikan dari storefront tanpa menghapus konten.</span></span></label>
          </FormSection>

          {MEDIA_TYPES.has(contentType) ? (
            <FormSection title="Gambar & media" description="Gunakan gambar lokal agar cepat, aman, dan bisa dikelola dari satu pustaka." testId="cms-editor-media">
              <div className="flex flex-wrap items-center gap-4">
                {imagePreview ? <ImageWithFallback src={mediaUrl(imagePreview)} alt="Pratinjau media terpilih" className="h-28 w-28 rounded-lg border border-[#E4DED2] bg-stone-100 object-cover" data-testid="cms-media-preview" /> : <div className="flex h-28 w-28 items-center justify-center rounded-lg border border-dashed border-[#D8D0C1] bg-[#FDFBF6] px-3 text-center text-[10px] font-semibold uppercase tracking-wide text-stone-400" data-testid="cms-media-empty">Belum ada gambar</div>}
                <div className="space-y-2"><button type="button" onClick={() => setPickerOpen((open) => !open)} className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#CFC7B7] bg-white px-4 text-sm font-semibold text-[#02422C] transition hover:border-[#02422C]" data-testid="cms-media-choose"><ImagePlus className="h-4 w-4" aria-hidden="true" />{pickerOpen ? "Tutup pustaka" : "Pilih gambar"}</button>{form.media_id ? <button type="button" onClick={() => { setFormValue("media_id", null); setImagePreview(""); }} className="block text-left text-xs font-medium text-red-700 hover:underline" data-testid="cms-media-remove">Lepas gambar</button> : <p className="text-xs text-stone-500">Belum ada gambar dipilih.</p>}</div>
              </div>
              {pickerOpen ? <MediaPicker onClose={() => setPickerOpen(false)} onSelect={(asset) => { setFormValue("media_id", asset.id); setImagePreview(asset.url); setPickerOpen(false); }} /> : null}
            </FormSection>
          ) : null}

          <FormSection title="Konten & bahasa" description="English wajib lengkap untuk publish. Bahasa lain opsional; toko akan memakai teks English bila terjemahan belum tersedia." testId="cms-editor-translations">
            <div className="flex flex-wrap gap-2" role="tablist" aria-label="Bahasa konten">
              {CMS_LOCALES.map((locale) => {
                const hasContent = activeFields.some((field) => localeText[locale]?.[field]?.trim());
                return <button key={locale} type="button" role="tab" aria-selected={activeLocale === locale} onClick={() => setActiveLocale(locale)} className={`inline-flex h-10 items-center gap-2 rounded-lg border px-3.5 text-xs font-bold transition ${activeLocale === locale ? "border-[#02422C] bg-[#02422C] text-white" : "border-[#E4DED2] bg-white text-stone-600 hover:border-[#02422C]"}`} data-testid={`cms-locale-${locale}`}><span>{LOCALE_LABELS[locale]}</span>{hasContent ? <Check className="h-3.5 w-3.5" aria-hidden="true" /> : null}</button>;
              })}
            </div>
            {activeLocale === "en" && required.length ? <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900"><strong>Belum siap publish:</strong> lengkapi {required.join(", ")}.</div> : null}
            {localeMissing ? <p className="mt-4 rounded-lg bg-[#F8F5EE] px-4 py-3 text-xs text-stone-600">Terjemahan {LOCALE_LABELS[activeLocale]} masih kosong. Storefront akan menggunakan bahasa Inggris.</p> : null}
            <div className="mt-5 grid gap-4 sm:grid-cols-2">
              {activeFields.map((field) => {
                const multiline = ["description", "body"].includes(field);
                return <div key={field} className={multiline ? "sm:col-span-2" : ""}>
                  <FormLabel htmlFor={`cms-tr-${field}-${activeLocale}`}>{LABELS[field]}{activeLocale === "en" && (["title", "body"].includes(field) || (contentType === "department_visual" && field === "alt_text")) ? <span className="ml-1 text-[#8A6420]">• wajib publish</span> : null}</FormLabel>
                  {multiline ? <textarea id={`cms-tr-${field}-${activeLocale}`} value={localeText[activeLocale]?.[field] || ""} onChange={(event) => setTranslation(field, event.target.value)} rows={field === "body" ? 7 : 4} maxLength={10000} className="w-full rounded-lg border border-[#E4DED2] bg-white px-3.5 py-3 text-sm leading-6 outline-none transition focus:border-[#02422C] focus:ring-2 focus:ring-[#02422C]/10" data-testid={`cms-tr-${field}-${activeLocale}`} /> : <input id={`cms-tr-${field}-${activeLocale}`} value={localeText[activeLocale]?.[field] || ""} onChange={(event) => setTranslation(field, event.target.value)} maxLength={field === "alt_text" ? 255 : field.includes("cta") ? 120 : field === "eyebrow" ? 255 : 500} className={inputClass} data-testid={`cms-tr-${field}-${activeLocale}`} />}
                </div>;
              })}
            </div>
          </FormSection>
        </div>

        <aside className="space-y-5 xl:sticky xl:top-20 xl:self-start">
          <section className="rounded-xl border border-[#E9E3D7] bg-[#FDFBF6] p-5 shadow-sm">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#8A6420]">Alur publikasi</p>
            <h2 className="mt-2 font-brand text-xl font-semibold text-[#17392C]">{status === "published" ? "Versi tayang aman" : status === "archived" ? "Konten diarsipkan" : "Siapkan untuk toko"}</h2>
            <p className="mt-2 text-xs leading-5 text-stone-600">{status === "published" ? "Simpan perubahan sebagai draft. Versi tayang tidak berubah sampai Anda memilih Terbitkan." : status === "archived" ? "Konten tidak terlihat oleh pelanggan. Anda bisa mengedit draft atau menerbitkannya kembali." : "Simpan sebagai draft kapan saja. Publish hanya aktif setelah teks English dan relasi wajib lengkap."}</p>
            {entry?.published_at ? <p className="mt-4 border-t border-[#E9E3D7] pt-3 text-[11px] text-stone-500">Terakhir tayang: {new Date(entry.published_at).toLocaleDateString("id-ID", { day: "numeric", month: "long", year: "numeric" })}</p> : null}
            <div className="mt-4 flex items-center gap-2 text-xs"><span className={`h-2 w-2 rounded-full ${dirty ? "bg-[#CD9B3A]" : "bg-emerald-600"}`} /><span className="text-stone-600">{dirty ? "Perubahan belum disimpan" : "Semua perubahan tersimpan"}</span></div>
          </section>

          {!isNew ? <section className="rounded-xl border border-[#E9E3D7] bg-white p-5 shadow-sm"><h2 className="font-brand text-lg font-semibold text-[#17392C]">Pratinjau storefront</h2><p className="mt-1 text-xs leading-5 text-stone-500">Pratinjau menampilkan draft kerja, termasuk perubahan yang belum diterbitkan.</p><button type="button" onClick={preview} disabled={dirty || saving} className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-[#CFC7B7] px-3 text-sm font-semibold text-[#02422C] hover:border-[#02422C] disabled:cursor-not-allowed disabled:opacity-50" data-testid="cms-preview"><ExternalLink className="h-4 w-4" aria-hidden="true" />Buka pratinjau aman</button>{dirty ? <p className="mt-2 text-center text-[10px] text-amber-700">Simpan dulu untuk mengaktifkan pratinjau.</p> : null}</section> : null}

          {!isNew && status === "archived" ? <section className="rounded-xl border border-red-200 bg-white p-5 shadow-sm"><h2 className="font-brand text-lg font-semibold text-red-900">Zona hapus</h2><p className="mt-1 text-xs leading-5 text-stone-500">Hanya konten archived yang bisa dihapus permanen. Riwayat revisi dan terjemahan ikut terhapus.</p><button type="button" onClick={removeContent} disabled={saving} className="mt-4 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-red-200 text-sm font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50" data-testid="cms-delete"><Trash2 className="h-4 w-4" aria-hidden="true" />Hapus permanen</button></section> : null}
        </aside>

        <div className="fixed inset-x-0 bottom-0 z-30 border-t border-[#DED7C9] bg-[#FDFBF6]/95 px-4 py-3 shadow-[0_-8px_28px_rgba(20,30,20,0.08)] backdrop-blur sm:px-6 xl:left-56">
          <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3">
            <div className="hidden text-xs text-stone-500 sm:block">{dirty ? "Perubahan belum disimpan" : "Tersimpan"}{isNew ? ` · ${cmsTypeLabel(contentType)}` : ""}</div>
            <div className="ml-auto flex flex-wrap items-center gap-2">
              {!isNew ? statusActions.map((action) => (
                <button key={action} type="button" onClick={() => changeStatus(action)} disabled={saving || !form.internal_name.trim() || (action === "publish" && required.length > 0)} className={`h-10 rounded-lg px-4 text-xs font-bold transition disabled:cursor-not-allowed disabled:opacity-45 ${action === "publish" ? "bg-[#02422C] text-white hover:bg-[#063723]" : action === "archive" ? "border border-amber-200 bg-amber-50 text-amber-900 hover:bg-amber-100" : "border border-[#DDD6C8] bg-white text-stone-700 hover:bg-stone-100"}`} data-testid={`cms-action-${action}`}>{action === "publish" ? "Terbitkan" : action === "archive" ? "Arsipkan" : "Jadikan draft"}</button>
              )) : null}
              <button type="submit" disabled={saving || !form.internal_name.trim()} data-testid="cms-save" className="inline-flex h-10 items-center gap-2 rounded-lg border border-[#02422C] bg-white px-4 text-xs font-bold text-[#02422C] transition hover:bg-[#02422C]/5 disabled:opacity-50"><Save className="h-4 w-4" aria-hidden="true" />{saving ? "Menyimpan…" : isNew ? "Simpan draft" : status === "published" ? "Simpan perubahan" : "Simpan draft"}</button>
            </div>
          </div>
        </div>
      </form>

      {!isNew ? <section className="rounded-xl border border-[#E9E3D7] bg-white shadow-sm" data-testid="cms-revisions"><details><summary className="flex cursor-pointer list-none items-center gap-2 px-5 py-4 font-brand text-lg font-semibold text-[#17392C]"><History className="h-4 w-4" aria-hidden="true" />Riwayat revisi <ChevronDown className="ml-auto h-4 w-4" aria-hidden="true" /></summary><ul className="divide-y divide-[#F0ECE4] border-t border-[#F0ECE4]">{(revisionsQuery.data || []).map((revision) => <li key={revision.id} className="flex flex-wrap items-center justify-between gap-3 px-5 py-3" data-testid={`cms-revision-${revision.version_number}`}><span className="text-xs"><strong className="text-stone-800">Versi {revision.version_number}</strong><span className="ml-2 text-stone-500">{REVISION_LABELS[revision.action] || revision.action}</span><span className="ml-2 text-stone-400">{revision.created_at ? new Date(revision.created_at).toLocaleString("id-ID") : ""}</span></span><button type="button" onClick={() => restore(revision)} disabled={saving} className="text-xs font-bold text-[#02422C] underline-offset-2 hover:underline" data-testid={`cms-restore-${revision.version_number}`}>Pulihkan sebagai draft</button></li>)}</ul></details></section> : null}
    </div>
  );
}
