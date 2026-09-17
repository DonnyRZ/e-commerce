import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, History, ImagePlus } from "lucide-react";
import { toast } from "sonner";
import {
  createCmsContent,
  getCmsContentEntry,
  getCmsMedia,
  getCmsPreviewToken,
  getCmsRevisions,
  restoreCmsRevision,
  setCmsContentStatus,
  updateCmsContent,
  uploadCmsMedia,
} from "@/lib/api";
import { mediaUrl } from "@/lib/localize";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];
const CONTENT_TYPES = [
  "hero", "announcement", "banner", "story", "page", "faq_item",
  "nav_item", "footer_group", "footer_item", "footer_text",
  "homepage_section", "department_visual",
];
const TEXT_FIELDS = ["title", "eyebrow", "subtitle", "cta_label", "secondary_cta_label", "alt_text"];
const AREA_FIELDS = ["description", "body"];
const EMPTY_TR = Object.fromEntries(
  [...TEXT_FIELDS, ...AREA_FIELDS].map((f) => [f, ""])
);

const STATUS_ACTIONS = {
  draft: ["publish", "archive"],
  published: ["unpublish", "archive"],
  archived: ["publish"],
};

function MediaPicker({ onSelect, onClose }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cms-media"],
    queryFn: () => getCmsMedia({ page_size: 48 }),
  });
  const [uploading, setUploading] = useState(false);

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const asset = await uploadCmsMedia(file);
      toast.success("Image uploaded");
      await refetch();
      onSelect(asset);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mt-3 border border-neutral-200 bg-neutral-50 p-4" data-testid="media-picker">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-widest text-neutral-500">Media library</p>
        <div className="flex items-center gap-2">
          <label
            className={`inline-flex h-9 cursor-pointer items-center gap-1.5 border border-neutral-300 bg-white px-3 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46] ${uploading ? "opacity-50" : ""}`}
            data-testid="media-picker-upload"
          >
            <ImagePlus className="h-3.5 w-3.5" aria-hidden="true" />
            {uploading ? "Uploading…" : "Upload"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={upload} disabled={uploading} />
          </label>
          <button type="button" onClick={onClose} className="h-9 border border-neutral-300 bg-white px-3 text-xs font-medium" data-testid="media-picker-close">
            Close
          </button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-3 gap-3 sm:grid-cols-4 lg:grid-cols-6">
        {isLoading
          ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)
          : (data?.items || []).map((m) => (
              <button
                key={m.id}
                type="button"
                onClick={() => onSelect(m)}
                className="group border border-neutral-200 bg-white p-1 text-left hover:border-[#145A46]"
                data-testid={`media-pick-${m.id}`}
              >
                <img src={mediaUrl(m.url)} alt={m.original_filename} className="aspect-square w-full object-cover" />
                <p className="mt-1 truncate text-[10px] text-neutral-500">{m.original_filename}</p>
              </button>
            ))}
        {!isLoading && !(data?.items || []).length ? (
          <p className="col-span-full py-6 text-center text-xs text-neutral-400" data-testid="media-picker-empty">No images yet — upload one.</p>
        ) : null}
      </div>
    </div>
  );
}

export default function CmsContentEditPage() {
  const { entryId } = useParams();
  const isNew = !entryId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [contentType, setContentType] = useState("banner");
  const [form, setForm] = useState({
    internal_name: "", slug: "", placement: "", sort_order: 0,
    is_visible: true, cta_url: "", secondary_cta_url: "", media_id: null,
  });
  const [imagePreview, setImagePreview] = useState("");
  const [tr, setTr] = useState({});
  const [activeLocale, setActiveLocale] = useState("en");
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [basePayload, setBasePayload] = useState({});

  const entryQuery = useQuery({
    queryKey: ["cms-content-entry", entryId],
    queryFn: () => getCmsContentEntry(entryId),
    enabled: !isNew,
  });
  const revisionsQuery = useQuery({
    queryKey: ["cms-revisions", entryId],
    queryFn: () => getCmsRevisions(entryId),
    enabled: !isNew,
  });

  useEffect(() => {
    const e = entryQuery.data;
    if (!e) return;
    setContentType(e.content_type);
    setForm({
      internal_name: e.internal_name, slug: e.slug || "", placement: e.placement || "",
      sort_order: e.sort_order, is_visible: e.is_visible,
      cta_url: e.cta_url || "", secondary_cta_url: e.secondary_cta_url || "",
      media_id: e.media_id,
    });
    setImagePreview(e.image_url || "");
    setBasePayload(e.payload || {});
    setTr(e.translations || {});
  }, [entryQuery.data]);

  const entry = entryQuery.data;
  const status = entry?.status || "draft";

  const setF = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const setT = (key) => (e) =>
    setTr({ ...tr, [activeLocale]: { ...(tr[activeLocale] || EMPTY_TR), [key]: e.target.value } });

  const invalidateCms = () => {
    queryClient.invalidateQueries({ queryKey: ["cms-content"] });
    queryClient.invalidateQueries({ queryKey: ["cms-content-entry", entryId] });
    queryClient.invalidateQueries({ queryKey: ["cms-revisions", entryId] });
    queryClient.invalidateQueries({ queryKey: ["cms"] });
  };

  const buildPayload = () => {
    const translations = Object.fromEntries(
      Object.entries(tr).filter(([, v]) => v && Object.values(v).some((x) => String(x || "").trim()))
    );
    const payload = { ...basePayload };
    // Images are selected from the CMS library; external image URLs are not
    // accepted by the operator workflow.
    delete payload.image_url;
    return {
      internal_name: form.internal_name.trim(),
      slug: form.slug.trim(),
      placement: form.placement.trim(),
      sort_order: parseInt(form.sort_order, 10) || 0,
      is_visible: Boolean(form.is_visible),
      media_id: form.media_id || null,
      cta_url: form.cta_url.trim() || null,
      secondary_cta_url: form.secondary_cta_url.trim() || null,
      payload,
      translations,
    };
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      if (isNew) {
        const created = await createCmsContent({ content_type: contentType, ...buildPayload() });
        toast.success("Draft created");
        invalidateCms();
        navigate(`/cms/${created.id}`, { replace: true });
        return;
      }
      await updateCmsContent(entryId, buildPayload());
      toast.success("Saved");
      invalidateCms();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || (typeof d === "string" ? d : "Save failed"));
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (action) => {
    try {
      await setCmsContentStatus(entryId, action);
      toast.success(`Content ${action === "publish" ? "published" : action === "unpublish" ? "unpublished" : "archived"}`);
      invalidateCms();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || "Status change failed");
    }
  };

  const preview = async () => {
    try {
      const { preview_url } = await getCmsPreviewToken(entryId);
      window.open(mediaUrl(preview_url), "_blank", "noopener");
    } catch {
      toast.error("Could not create preview link");
    }
  };

  const restore = async (revisionId) => {
    try {
      await restoreCmsRevision(entryId, revisionId);
      toast.success("Revision restored as draft");
      invalidateCms();
    } catch {
      toast.error("Restore failed");
    }
  };

  if (!isNew && entryQuery.isLoading) {
    return <div data-testid="cms-editor-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  }

  const tab = { ...EMPTY_TR, ...(tr[activeLocale] || {}) };

  return (
    <div data-testid="cms-content-editor">
      <Link to="/cms" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900" data-testid="cms-editor-back">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Back to content
      </Link>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{isNew ? "New content" : form.internal_name || "Edit content"}</h1>
        {!isNew ? <StatusPill value={status} /> : null}
      </div>

      <form onSubmit={save} className="mt-6 space-y-6">
        <section className="border border-neutral-200 bg-white p-5" data-testid="cms-editor-meta">
          <h2 className="text-sm font-semibold">Settings</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {isNew ? (
              <div>
                <label className="mb-1 block text-xs font-medium text-neutral-500">Content type</label>
                <select value={contentType} onChange={(e) => setContentType(e.target.value)} className={inputClass} data-testid="cms-field-type">
                  {CONTENT_TYPES.map((ct) => (
                    <option key={ct} value={ct}>{ct.replaceAll("_", " ")}</option>
                  ))}
                </select>
              </div>
            ) : null}
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Internal name</label>
              <input value={form.internal_name} onChange={setF("internal_name")} required className={inputClass} data-testid="cms-field-name" maxLength={255} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Slug</label>
              <input value={form.slug} onChange={setF("slug")} className={inputClass} data-testid="cms-field-slug" maxLength={160} placeholder="auto-generated if empty" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Placement</label>
              <input value={form.placement} onChange={setF("placement")} className={inputClass} data-testid="cms-field-placement" maxLength={80} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Sort order</label>
              <input type="number" min="0" step="1" value={form.sort_order} onChange={setF("sort_order")} className={inputClass} data-testid="cms-field-sort" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Primary CTA URL</label>
              <input value={form.cta_url} onChange={setF("cta_url")} className={inputClass} data-testid="cms-field-cta" placeholder="/shop or https://…" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Secondary CTA URL</label>
              <input value={form.secondary_cta_url} onChange={setF("secondary_cta_url")} className={inputClass} data-testid="cms-field-cta2" placeholder="/shop or https://…" />
            </div>
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm" data-testid="cms-field-visible-label">
            <input type="checkbox" checked={Boolean(form.is_visible)} onChange={(e) => setForm({ ...form, is_visible: e.target.checked })} className="accent-[#145A46]" data-testid="cms-field-visible" />
            Visible (published entries only appear on the storefront when visible)
          </label>
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="cms-editor-media">
          <h2 className="text-sm font-semibold">Media</h2>
          <div className="mt-4 flex flex-wrap items-start gap-4">
            {imagePreview ? (
              <img src={mediaUrl(imagePreview)} alt="" className="h-28 w-28 border border-neutral-200 object-cover" data-testid="cms-media-preview" />
            ) : (
              <div className="flex h-28 w-28 items-center justify-center border border-dashed border-neutral-300 text-[10px] uppercase tracking-wide text-neutral-400" data-testid="cms-media-empty">
                No image
              </div>
            )}
            <div className="flex flex-col gap-2">
              <button
                type="button"
                onClick={() => setPickerOpen(!pickerOpen)}
                className="h-10 border border-neutral-300 px-4 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]"
                data-testid="cms-media-choose"
              >
                {pickerOpen ? "Hide library" : "Choose from library"}
              </button>
              {form.media_id ? (
                <button
                  type="button"
                  onClick={() => { setForm({ ...form, media_id: null }); setImagePreview(""); }}
                  className="h-9 text-left text-xs font-medium text-red-600 hover:underline"
                  data-testid="cms-media-remove"
                >
                  Remove selected media
                </button>
              ) : null}
            </div>
          </div>
          {pickerOpen ? (
            <MediaPicker
              onClose={() => setPickerOpen(false)}
              onSelect={(m) => {
                setForm({ ...form, media_id: m.id });
                setImagePreview(m.url);
                setPickerOpen(false);
              }}
            />
          ) : null}
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="cms-editor-translations">
          <h2 className="text-sm font-semibold">Translations</h2>
          <div className="mt-3 flex gap-1" role="tablist">
            {LOCALES.map((loc) => (
              <button
                key={loc}
                type="button"
                role="tab"
                aria-selected={activeLocale === loc}
                data-testid={`cms-locale-${loc}`}
                onClick={() => setActiveLocale(loc)}
                className={`h-9 px-4 text-xs font-semibold uppercase tracking-wide ${
                  activeLocale === loc ? "bg-[#145A46] text-white" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                }`}
              >
                {loc}
                {tr[loc]?.title || tr[loc]?.body ? " •" : ""}
              </button>
            ))}
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            {TEXT_FIELDS.map((field) => (
              <div key={field}>
                <label className="mb-1 block text-xs font-medium text-neutral-500">{field.replaceAll("_", " ")}</label>
                <input value={tab[field]} onChange={setT(field)} className={inputClass} data-testid={`cms-tr-${field}-${activeLocale}`} />
              </div>
            ))}
            {AREA_FIELDS.map((field) => (
              <div key={field} className="sm:col-span-2">
                <label className="mb-1 block text-xs font-medium text-neutral-500">{field}</label>
                <textarea value={tab[field]} onChange={setT(field)} rows={3} className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]" data-testid={`cms-tr-${field}-${activeLocale}`} />
              </div>
            ))}
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            data-testid="cms-save"
            className="h-11 bg-[#145A46] px-8 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving…" : isNew ? "Create draft" : "Save draft changes"}
          </button>
          {!isNew
            ? (STATUS_ACTIONS[status] || []).map((action) => (
                <button
                  key={action}
                  type="button"
                  onClick={() => changeStatus(action)}
                  data-testid={`cms-action-${action}`}
                  className={`h-11 px-6 text-sm font-semibold ${
                    action === "publish"
                      ? "bg-neutral-900 text-white hover:opacity-90"
                      : "border border-neutral-300 text-neutral-600 hover:border-neutral-900"
                  }`}
                >
                  {action.charAt(0).toUpperCase() + action.slice(1)}
                </button>
              ))
            : null}
          {!isNew ? (
            <button
              type="button"
              onClick={preview}
              data-testid="cms-preview"
              className="inline-flex h-11 items-center gap-1.5 border border-neutral-300 px-5 text-sm font-medium text-neutral-600 hover:border-[#145A46] hover:text-[#145A46]"
            >
              <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              Preview (1h link)
            </button>
          ) : null}
        </div>
      </form>

      {!isNew ? (
        <section className="mt-8 border border-neutral-200 bg-white" data-testid="cms-revisions">
          <h2 className="flex items-center gap-2 border-b border-neutral-200 px-5 py-3 text-sm font-semibold">
            <History className="h-4 w-4" aria-hidden="true" />
            Revision history
          </h2>
          <ul className="divide-y divide-neutral-50 text-sm">
            {(revisionsQuery.data || []).map((r) => (
              <li key={r.id} className="flex items-center justify-between px-5 py-2.5" data-testid={`cms-revision-${r.version_number}`}>
                <span>
                  <span className="font-medium">v{r.version_number}</span>
                  <span className="ml-2 text-neutral-500">{r.action}</span>
                  <span className="ml-2 text-xs text-neutral-400">{fmtDate(r.created_at)}</span>
                </span>
                <button
                  type="button"
                  onClick={() => restore(r.id)}
                  className="text-xs font-medium text-[#145A46] hover:underline"
                  data-testid={`cms-restore-${r.version_number}`}
                >
                  Restore as draft
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
