import { useMemo, useState } from "react";
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
const KINDS = ["department", "group", "category"];
const EMPTY_FORM = {
  slug: "",
  kind: "category",
  department: "",
  parent_id: "",
  sort_order: 0,
  media_id: null,
  image_url: "",
  is_active: false,
  names: { en: "", id: "", uz: "", ru: "" },
};

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

const kindLabel = (kind) => ({ department: "Department", group: "Group", category: "Category" }[kind] || kind);

export default function AdminCategoriesPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["admin-categories"], queryFn: getAdminCategories });
  const [editing, setEditing] = useState(null); // null | "new" | node object
  const [form, setForm] = useState(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const raw = data;
  const items = Array.isArray(raw) ? raw : raw?.items || [];
  const departments = items.filter((c) => c.kind === "department");
  const groups = items.filter((c) => c.kind === "group");

  const parentOptions = useMemo(() => {
    if (form.kind === "department") return [];
    const root = departments.find((item) => item.slug === form.department);
    if (!root) return [];
    if (form.kind === "group") return [root];
    return [root, ...groups.filter((item) => item.department === form.department)];
  }, [departments, groups, form.department, form.kind]);

  const setNodeField = (key, value) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "kind") {
        if (value === "department") {
          next.department = next.slug;
          next.parent_id = "";
          next.is_active = false;
        } else {
          if (!next.department) next.department = departments[0]?.slug || "";
          next.parent_id = departments.find((item) => item.slug === next.department)?.id || "";
        }
      }
      if (key === "department" && next.kind !== "department") {
        next.parent_id = departments.find((item) => item.slug === value)?.id || "";
      }
      if (key === "slug" && next.kind === "department") next.department = value;
      return next;
    });
  };

  const openNew = () => {
    const department = departments[0];
    setForm({
      ...EMPTY_FORM,
      department: department?.slug || "",
      parent_id: department?.id || "",
    });
    setEditing("new");
  };

  const openEdit = (node) => {
    setForm({
      slug: node.slug,
      kind: node.kind,
      department: node.department,
      parent_id: node.parent_id || "",
      sort_order: node.sort_order,
      media_id: node.media_id || null,
      image_url: node.image_url || "",
      is_active: node.is_active,
      names: Object.fromEntries(LOCALES.map((locale) => [locale, node.translations?.[locale]?.name || ""])),
    });
    setEditing(node);
    setPickerOpen(false);
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    const translations = Object.fromEntries(
      LOCALES.filter((locale) => form.names[locale]?.trim()).map((locale) => [locale, { name: form.names[locale].trim() }])
    );
    const body = {
      slug: form.slug.trim(),
      kind: form.kind,
      department: form.kind === "department" ? form.slug.trim() : form.department,
      parent_id: form.parent_id || null,
      sort_order: parseInt(form.sort_order, 10) || 0,
      media_id: form.media_id || null,
      is_active: Boolean(form.is_active),
      translations,
    };
    try {
      if (editing === "new") {
        await createAdminCategory(body);
        toast.success("Taxonomy node created");
      } else {
        await updateAdminCategory(editing.id, {
          parent_id: body.parent_id,
          sort_order: body.sort_order,
          media_id: body.media_id,
          is_active: body.is_active,
          translations,
        });
        toast.success("Taxonomy node saved");
      }
      queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
      queryClient.invalidateQueries({ queryKey: ["catalog-tree"] });
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setEditing(null);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.error || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const remove = async (node) => {
    if (!window.confirm(`Delete ${kindLabel(node.kind).toLowerCase()} "${node.slug}"? Only unused nodes can be deleted.`)) return;
    try {
      await deleteAdminCategory(node.id);
      toast.success("Taxonomy node deleted");
      queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.error || "Delete failed");
    }
  };

  const renderNode = (node, depth = 0) => {
    const children = items
      .filter((item) => item.parent_id === node.id)
      .sort((a, b) => (a.sort_order - b.sort_order) || a.slug.localeCompare(b.slug));
    return (
      <div key={node.id} data-testid={`category-tree-node-${node.slug}`}>
        <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-center gap-3 border-b border-neutral-100 px-5 py-3 text-sm" style={{ paddingLeft: `${20 + depth * 24}px` }}>
          <div className="min-w-0">
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate font-medium">{pickLocalized(node.translations, "en", "name") || node.slug}</span>
              <span className="shrink-0 text-xs text-neutral-400">{node.slug}</span>
            </div>
            <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-neutral-400">
              <span>{kindLabel(node.kind)}</span>
              <span>{node.product_count || 0} products</span>
              {node.media_id ? <span>image linked</span> : <span>no image</span>}
            </div>
          </div>
          <span className="text-xs text-neutral-500">sort {node.sort_order}</span>
          <StatusPill value={node.is_active ? "active" : "inactive"} />
          <div className="whitespace-nowrap text-right">
            <button onClick={() => openEdit(node)} className="mr-2 inline-flex h-8 items-center gap-1 border border-neutral-300 px-3 text-xs font-medium hover:border-[#145A46] hover:text-[#145A46]" data-testid={`category-edit-${node.slug}`}>
              <Pencil className="h-3 w-3" aria-hidden="true" /> Edit
            </button>
            <button onClick={() => remove(node)} className="inline-flex h-8 items-center border border-neutral-300 px-3 text-xs font-medium text-neutral-500 hover:border-red-600 hover:text-red-600" data-testid={`category-delete-${node.slug}`}>
              Delete
            </button>
          </div>
        </div>
        {children.map((child) => renderNode(child, depth + 1))}
      </div>
    );
  };

  return (
    <div data-testid="admin-categories-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Catalog taxonomy</h1>
          <p className="mt-1 text-sm text-neutral-500">Manage departments, audience groups, and product categories.</p>
        </div>
        <button onClick={openNew} data-testid="categories-new-button" className="inline-flex h-10 items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90">
          <Plus className="h-4 w-4" aria-hidden="true" />
          New node
        </button>
      </div>

      {editing ? (
        <form onSubmit={save} className="mt-5 border border-[#145A46]/30 bg-white p-5" data-testid="category-form">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">{editing === "new" ? "New taxonomy node" : `Edit: ${editing.slug}`}</h2>
              <p className="mt-1 text-xs text-neutral-500">Product listings can only use leaf categories.</p>
            </div>
            <button type="button" onClick={() => setEditing(null)} aria-label="close" data-testid="category-form-close">
              <X className="h-4 w-4 text-neutral-400 hover:text-neutral-900" />
            </button>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Slug</label>
              <input value={form.slug} onChange={(e) => setNodeField("slug", e.target.value)} required disabled={editing !== "new"} className={inputClass} data-testid="category-slug" placeholder="my-category" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Node type</label>
              <select value={form.kind} onChange={(e) => setNodeField("kind", e.target.value)} required disabled={editing !== "new"} className={inputClass} data-testid="category-kind">
                {KINDS.map((kind) => <option key={kind} value={kind}>{kindLabel(kind)}</option>)}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Department root</label>
              {form.kind === "department" ? (
                <input value={form.slug} readOnly className={inputClass} data-testid="category-department" />
              ) : (
                <select value={form.department} onChange={(e) => setNodeField("department", e.target.value)} required disabled={editing !== "new"} className={inputClass} data-testid="category-department">
                  <option value="" disabled>—</option>
                  {departments.map((department) => <option key={department.id} value={department.slug}>{pickLocalized(department.translations, "en", "name") || department.slug}</option>)}
                </select>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Parent</label>
              {form.kind === "department" ? (
                <input value="None (root)" readOnly className={inputClass} data-testid="category-parent" />
              ) : (
                <select value={form.parent_id} onChange={(e) => setNodeField("parent_id", e.target.value)} required className={inputClass} data-testid="category-parent">
                  <option value="" disabled>—</option>
                  {parentOptions.map((parent) => <option key={parent.id} value={parent.id}>{parent.kind === "group" ? "↳ " : ""}{pickLocalized(parent.translations, "en", "name") || parent.slug}</option>)}
                </select>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Sort order</label>
              <input type="number" min="0" step="1" value={form.sort_order} onChange={(e) => setNodeField("sort_order", e.target.value)} className={inputClass} data-testid="category-sort" />
            </div>
            <div className="sm:col-span-2 xl:col-span-2">
              <label className="mb-1 block text-xs font-medium text-neutral-500">Node image</label>
              <div className="flex flex-wrap items-center gap-3">
                {form.media_id && form.image_url ? <img src={mediaUrl(form.image_url)} alt="" className="h-12 w-12 border border-neutral-200 object-cover" /> : <div className="flex h-12 w-12 items-center justify-center border border-dashed border-neutral-300 text-[10px] text-neutral-400">None</div>}
                <button type="button" onClick={() => setPickerOpen(!pickerOpen)} className="h-10 border border-neutral-300 px-4 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]" data-testid="category-media-choose">
                  {pickerOpen ? "Hide library" : "Choose from library"}
                </button>
                {form.media_id ? <button type="button" onClick={() => setForm({ ...form, media_id: null, image_url: "" })} className="text-xs font-medium text-red-600 hover:underline">Remove</button> : null}
              </div>
              {pickerOpen ? <MediaPicker onClose={() => setPickerOpen(false)} onSelect={(asset) => { setForm({ ...form, media_id: asset.id, image_url: asset.url }); setPickerOpen(false); }} /> : null}
            </div>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {LOCALES.map((locale) => (
              <div key={locale}>
                <label className="mb-1 block text-xs font-medium text-neutral-500">Name ({locale}{locale === "en" ? " — required" : ""})</label>
                <input value={form.names[locale]} onChange={(e) => setForm({ ...form, names: { ...form.names, [locale]: e.target.value } })} required={locale === "en"} className={inputClass} data-testid={`category-name-${locale}`} />
              </div>
            ))}
          </div>
          <label className="mt-4 flex items-center gap-2 text-sm" data-testid="category-active-label">
            <input type="checkbox" checked={Boolean(form.is_active)} onChange={(e) => setNodeField("is_active", e.target.checked)} className="accent-[#145A46]" data-testid="category-active" />
            Active (visible in storefront)
          </label>
          <button type="submit" disabled={saving} data-testid="category-save" className="mt-4 h-10 bg-[#145A46] px-6 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
            {saving ? "Saving…" : "Save node"}
          </button>
        </form>
      ) : null}

      {isLoading ? (
        <Skeleton className="mt-6 h-64 w-full" />
      ) : (
        <div className="mt-6 overflow-x-auto border border-neutral-200 bg-white" data-testid="category-tree">
          {departments.map((department) => renderNode(department))}
          {!departments.length ? <p className="px-5 py-8 text-center text-sm text-neutral-400">No departments yet.</p> : null}
          {items.filter((node) => !node.parent_id && node.kind !== "department").map((node) => renderNode(node))}
        </div>
      )}
    </div>
  );
}
