import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Pencil, Plus, X } from "lucide-react";
import { toast } from "sonner";
import {
  createAdminCategory,
  deleteAdminCategory,
  getAdminCategories,
  getCmsMedia,
  updateAdminCategory,
  uploadCmsMedia,
} from "@/lib/api";
import { mediaUrl, pickLocalized } from "@/lib/localize";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];
const EMPTY_FORM = { slug: "", department: "", sort_order: 0, media_id: null, image_url: "", is_active: true, names: { en: "", id: "", uz: "", ru: "" } };

function MediaPicker({ onSelect, onClose }) {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cms-media", "category-picker"],
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
      await refetch();
      onSelect(asset);
      toast.success("Image uploaded and selected");
    } catch {
      toast.error("Image upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="mt-3 border border-neutral-200 bg-neutral-50 p-3" data-testid="category-media-picker">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-semibold uppercase tracking-widest text-neutral-500">Asset Library</p>
        <div className="flex items-center gap-2">
          <label className={`inline-flex h-8 cursor-pointer items-center gap-1 border border-neutral-300 bg-white px-3 text-xs font-semibold hover:border-[#145A46] ${uploading ? "opacity-50" : ""}`}>
            <ImagePlus className="h-3.5 w-3.5" aria-hidden="true" />
            {uploading ? "Uploading…" : "Upload"}
            <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={upload} disabled={uploading} />
          </label>
          <button type="button" onClick={onClose} className="h-8 border border-neutral-300 bg-white px-3 text-xs">Close</button>
        </div>
      </div>
      <div className="mt-3 grid grid-cols-4 gap-2 sm:grid-cols-6">
        {isLoading ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="aspect-square" />) : (data?.items || []).map((m) => (
          <button key={m.id} type="button" onClick={() => onSelect(m)} className="border border-neutral-200 bg-white p-1 text-left hover:border-[#145A46]" data-testid={`category-media-pick-${m.id}`}>
            <img src={mediaUrl(m.url)} alt={m.translations?.en?.alt_text || m.original_filename} className="aspect-square w-full object-cover" />
            <span className="mt-1 block truncate text-[10px] text-neutral-500">{m.original_filename}</span>
          </button>
        ))}
      </div>
      {!isLoading && !(data?.items || []).length ? <p className="py-4 text-center text-xs text-neutral-400">No assets yet. Upload one here.</p> : null}
    </div>
  );
}

export default function AdminCategoriesPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["admin-categories"], queryFn: getAdminCategories });
  const [editing, setEditing] = useState(null); // null | "new" | category object
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const raw = data;
  const items = Array.isArray(raw) ? raw : raw?.items || [];
  const departments = items.filter((c) => c.kind === "department");
  const categories = items.filter((c) => c.kind !== "department");

  const openNew = () => {
    setForm({ ...EMPTY_FORM, department: departments[0]?.slug || "" });
    setEditing("new");
  };
  const openEdit = (c) => {
    setForm({
      slug: c.slug,
      department: c.department,
      sort_order: c.sort_order,
      media_id: c.media_id || null,
      image_url: c.image_url || "",
      is_active: c.is_active,
      names: Object.fromEntries(LOCALES.map((l) => [l, c.translations?.[l]?.name || ""])),
    });
    setEditing(c);
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    const translations = Object.fromEntries(
      LOCALES.filter((l) => form.names[l]?.trim()).map((l) => [l, { name: form.names[l].trim() }])
    );
    try {
      if (editing === "new") {
        await createAdminCategory({
          slug: form.slug.trim(),
          department: form.department,
          sort_order: parseInt(form.sort_order, 10) || 0,
          media_id: form.media_id || null,
          is_active: Boolean(form.is_active),
          translations,
        });
        toast.success("Category created");
      } else {
        await updateAdminCategory(editing.id, {
          sort_order: parseInt(form.sort_order, 10) || 0,
          media_id: form.media_id || null,
          is_active: Boolean(form.is_active),
          translations,
        });
        toast.success("Category saved");
      }
      queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setEditing(null);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : d?.error || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (c) => {
    if (!window.confirm(`Delete category "${c.slug}"? Only empty categories can be deleted.`)) return;
    try {
      await deleteAdminCategory(c.id);
      toast.success("Category deleted");
      queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : d?.error || "Delete failed");
    }
  };

  const grouped = departments.map((d) => ({
    dept: d,
    cats: categories.filter((c) => c.department === d.slug),
  }));
  const orphan = categories.filter((c) => !departments.some((d) => d.slug === c.department));
  if (orphan.length) grouped.push({ dept: null, cats: orphan });

  return (
    <div data-testid="admin-categories-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Categories</h1>
        <button
          onClick={openNew}
          data-testid="categories-new-button"
          className="inline-flex h-10 items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New Category
        </button>
      </div>

      {editing ? (
        <form onSubmit={save} className="mt-5 border border-[#145A46]/30 bg-white p-5" data-testid="category-form">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">{editing === "new" ? "New category" : `Edit: ${editing.slug}`}</h2>
            <button type="button" onClick={() => setEditing(null)} aria-label="close" data-testid="category-form-close">
              <X className="h-4 w-4 text-neutral-400 hover:text-neutral-900" />
            </button>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Slug</label>
              <input value={form.slug} onChange={(e) => setForm({ ...form, slug: e.target.value })} required disabled={editing !== "new"} className={inputClass} data-testid="category-slug" placeholder="my-category" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Department</label>
              <select value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} required disabled={editing !== "new"} className={inputClass} data-testid="category-department">
                <option value="" disabled>—</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.slug}>{pickLocalized(d.translations, "en", "name") || d.slug}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Sort order</label>
              <input type="number" min="0" step="1" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value })} className={inputClass} data-testid="category-sort" />
            </div>
            <div className="sm:col-span-2 xl:col-span-2">
              <label className="mb-1 block text-xs font-medium text-neutral-500">Category image</label>
              <div className="flex flex-wrap items-center gap-3">
                {form.media_id && form.image_url ? <img src={mediaUrl(form.image_url)} alt="" className="h-12 w-12 border border-neutral-200 object-cover" /> : <div className="flex h-12 w-12 items-center justify-center border border-dashed border-neutral-300 text-[10px] text-neutral-400">None</div>}
                <button type="button" onClick={() => setPickerOpen(!pickerOpen)} className="h-10 border border-neutral-300 px-4 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]" data-testid="category-media-choose">
                  {pickerOpen ? "Hide library" : "Choose from library"}
                </button>
                {form.media_id ? <button type="button" onClick={() => setForm({ ...form, media_id: null, image_url: "" })} className="text-xs font-medium text-red-600 hover:underline">Remove</button> : null}
              </div>
              {pickerOpen ? <MediaPicker onClose={() => setPickerOpen(false)} onSelect={(m) => { setForm({ ...form, media_id: m.id, image_url: m.url }); setPickerOpen(false); }} /> : null}
            </div>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {LOCALES.map((loc) => (
              <div key={loc}>
                <label className="mb-1 block text-xs font-medium text-neutral-500">
                  Name ({loc}{loc === "en" ? " — required" : ""})
                </label>
                <input
                  value={form.names[loc]}
                  onChange={(e) => setForm({ ...form, names: { ...form.names, [loc]: e.target.value } })}
                  required={loc === "en"}
                  className={inputClass}
                  data-testid={`category-name-${loc}`}
                />
              </div>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm" data-testid="category-active-label">
            <input type="checkbox" checked={Boolean(form.is_active)} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} className="accent-[#145A46]" data-testid="category-active" />
            Active (visible in storefront)
          </label>
          <button type="submit" disabled={saving} data-testid="category-save" className="mt-4 h-10 bg-[#145A46] px-6 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
            {saving ? "Saving…" : "Save category"}
          </button>
        </form>
      ) : null}

      {isLoading ? (
        <Skeleton className="mt-6 h-64 w-full" />
      ) : (
        grouped.map(({ dept, cats }) => (
          <section key={dept?.id || "orphan"} className="mt-6 border border-neutral-200 bg-white" data-testid={`category-group-${dept?.slug || "other"}`}>
            <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">
              {dept ? pickLocalized(dept.translations, "en", "name") || dept.slug : "Other"}
            </h2>
            <table className="w-full text-sm">
              <tbody>
                {cats.map((c) => (
                  <tr key={c.id} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`category-row-${c.slug}`}>
                    <td className="px-5 py-2.5">
                      <span className="font-medium">{pickLocalized(c.translations, "en", "name") || c.slug}</span>
                      <span className="ml-2 text-xs text-neutral-400">{c.slug}</span>
                    </td>
                    <td className="px-5 py-2.5 text-neutral-500">{c.product_count} products</td>
                    <td className="px-5 py-2.5 text-neutral-500">sort {c.sort_order}</td>
                    <td className="px-5 py-2.5"><StatusPill value={c.is_active ? "active" : "inactive"} /></td>
                    <td className="px-5 py-2.5 text-right">
                      <button onClick={() => openEdit(c)} className="mr-2 inline-flex h-8 items-center gap-1 border border-neutral-300 px-3 text-xs font-medium hover:border-[#145A46] hover:text-[#145A46]" data-testid={`category-edit-${c.slug}`}>
                        <Pencil className="h-3 w-3" aria-hidden="true" /> Edit
                      </button>
                      <button onClick={() => remove(c)} className="inline-flex h-8 items-center border border-neutral-300 px-3 text-xs font-medium text-neutral-500 hover:border-red-600 hover:text-red-600" data-testid={`category-delete-${c.slug}`}>
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
                {!cats.length ? (
                  <tr><td className="px-5 py-6 text-center text-sm text-neutral-400">No categories.</td></tr>
                ) : null}
              </tbody>
            </table>
          </section>
        ))
      )}
    </div>
  );
}
