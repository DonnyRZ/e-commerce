import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, Folder, ImagePlus, Info, MoreHorizontal, Pencil, Plus, Power, Trash2 } from "lucide-react";
import { useSearchParams } from "react-router-dom";
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
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { StatusPill, inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];

const makeEmptyForm = () => ({
  slug: "",
  kind: "category",
  department: "",
  parent_id: "",
  sort_order: 0,
  media_id: null,
  image_url: "",
  // A category created from the CMS should be immediately usable when its
  // parent is already active. The backend still validates the parent chain.
  is_active: true,
  names: { en: "", id: "", uz: "", ru: "" },
});

const kindLabel = (kind) => ({ department: "Department", category: "Category" }[kind] || kind);
const nodeName = (node) => pickLocalized(node?.translations, "en", "name") || node?.slug || "Unnamed";
const sortNodes = (nodes) => [...nodes].sort((a, b) => (a.sort_order - b.sort_order) || nodeName(a).localeCompare(nodeName(b)));
const slugify = (value) => String(value || "")
  .normalize("NFKD")
  .replace(/[\u0300-\u036f]/g, "")
  .toLowerCase()
  .replace(/[^a-z0-9]+/g, "-")
  .replace(/^-+|-+$/g, "")
  .slice(0, 120);

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
            <ImageWithFallback src={mediaUrl(m.url)} alt={m.translations?.en?.alt_text || m.original_filename} className="aspect-square w-full object-cover" />
            <span className="mt-1 block truncate text-[10px] text-neutral-500">{m.original_filename}</span>
          </button>
        ))}
      </div>
      {!isLoading && !(data?.items || []).length ? <p className="py-4 text-center text-xs text-neutral-400">No assets yet. Upload one here.</p> : null}
    </div>
  );
}

function NodeActions({ node, onEdit, onToggle, onDelete }) {
  const canDelete = !node.child_count && !node.product_count;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button type="button" className="inline-flex h-9 w-9 items-center justify-center rounded-md text-neutral-400 hover:bg-neutral-100 hover:text-neutral-800" aria-label={`Actions for ${nodeName(node)}`} data-testid={`category-actions-${node.slug}`}>
          <MoreHorizontal className="h-5 w-5" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-48">
        <DropdownMenuItem onSelect={onEdit}>
          <Pencil className="h-4 w-4" aria-hidden="true" />
          Edit
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onToggle}>
          <Power className="h-4 w-4" aria-hidden="true" />
          {node.is_active ? "Deactivate" : "Activate"}
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          disabled={!canDelete}
          title={canDelete ? "Delete permanently" : "This node still has products or child categories."}
          onSelect={(event) => {
            if (canDelete) onDelete(event);
          }}
          className="text-red-600 focus:text-red-700"
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          Delete
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function CategoryRow({ node, onEdit, onToggle, onDelete }) {
  return (
    <div className={`flex items-center gap-3 border-t border-neutral-100 px-4 py-3 sm:px-5 ${node.is_active ? "" : "bg-neutral-50/80"}`} data-testid={`category-row-${node.slug}`}>
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-[#145A46]/[0.07] text-[#145A46]">
        <Folder className="h-4 w-4" aria-hidden="true" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-semibold text-neutral-800">{nodeName(node)}</span>
          {!node.is_active ? <StatusPill value="inactive" /> : null}
        </div>
        <p className="mt-0.5 text-xs text-neutral-400">{node.product_count || 0} products</p>
      </div>
      <NodeActions node={node} onEdit={onEdit} onToggle={onToggle} onDelete={onDelete} />
    </div>
  );
}

export default function AdminCategoriesPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { data, isLoading, isError, refetch } = useQuery({ queryKey: ["admin-categories"], queryFn: getAdminCategories });
  const [editing, setEditing] = useState(null); // null | "new" | node object
  const [form, setForm] = useState(makeEmptyForm);
  const [saving, setSaving] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);

  const raw = data;
  const items = useMemo(() => (Array.isArray(raw) ? raw : raw?.items || []), [raw]);
  const departments = useMemo(() => sortNodes(items.filter((c) => c.kind === "department")), [items]);
  const requestedDepartment = searchParams.get("department");
  const activeDepartment = departments.find((department) => department.slug === requestedDepartment) || departments[0] || null;
  const directCategories = useMemo(
    () => activeDepartment ? sortNodes(items.filter((item) => item.parent_id === activeDepartment.id && item.kind === "category")) : [],
    [activeDepartment, items],
  );

  useEffect(() => {
    if (!departments.length) return;
    if (!departments.some((department) => department.slug === requestedDepartment)) {
      setSearchParams({ department: departments[0].slug }, { replace: true });
    }
  }, [departments, requestedDepartment, setSearchParams]);

  const refreshCatalog = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-categories"] });
    queryClient.invalidateQueries({ queryKey: ["catalog-tree"] });
    queryClient.invalidateQueries({ queryKey: ["categories"] });
  };

  const departmentNode = form.department ? departments.find((d) => d.slug === form.department) : null;
  const placementLabel = form.kind === "department"
    ? "Top-level department"
    : nodeName(departmentNode);

  const setName = (locale, value) => {
    setForm((current) => ({ ...current, names: { ...current.names, [locale]: value } }));
  };

  const openNew = (kind = "department", parent = null) => {
    const department = kind === "department" ? null : activeDepartment;
    const parentId = kind === "department" ? "" : (parent?.id || department?.id || "");
    const placementParent = parent || department;
    setForm({
      ...makeEmptyForm(),
      kind,
      department: department?.slug || "",
      parent_id: parentId,
      // New departments have no parent. For categories, only default
      // to active when the selected parent is active; otherwise the server
      // would correctly reject the create with parent_inactive.
      is_active: kind === "department" || Boolean(placementParent?.is_active),
    });
    setAdvancedOpen(false);
    setPickerOpen(false);
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
    setAdvancedOpen(false);
    setPickerOpen(false);
    setEditing(node);
  };

  const closeEditor = () => {
    setEditing(null);
    setPickerOpen(false);
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    const generatedSlug = slugify(form.names.en);
    const slug = (form.slug || generatedSlug).trim();
    if (!slug) {
      toast.error("English name is required to create this node.");
      return;
    }
    const translations = Object.fromEntries(
      LOCALES.filter((locale) => form.names[locale]?.trim()).map((locale) => [locale, { name: form.names[locale].trim() }]),
    );
    setSaving(true);
    try {
      const body = {
        slug,
        kind: form.kind,
        department: form.kind === "department" ? slug : form.department,
        parent_id: form.parent_id || null,
        sort_order: parseInt(form.sort_order, 10) || 0,
        media_id: form.media_id || null,
        image_url: form.media_id ? null : (form.image_url || null),
        is_active: Boolean(form.is_active),
        translations,
      };
      if (editing === "new") {
        await createAdminCategory(body);
        toast.success(`${kindLabel(form.kind)} created`);
      } else {
        await updateAdminCategory(editing.id, {
          parent_id: body.parent_id,
          sort_order: body.sort_order,
          media_id: body.media_id,
          image_url: body.image_url,
          is_active: body.is_active,
          translations,
        });
        toast.success(`${kindLabel(form.kind)} saved`);
      }
      refreshCatalog();
      closeEditor();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.error || "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const toggleActive = async (node) => {
    try {
      await updateAdminCategory(node.id, { is_active: !node.is_active });
      toast.success(`${nodeName(node)} ${node.is_active ? "deactivated" : "activated"}`);
      refreshCatalog();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.error || "Status update failed");
    }
  };

  const remove = async (node) => {
    if (node.child_count || node.product_count) {
      toast.error("This node still has products or child categories.");
      return;
    }
    if (!window.confirm(`Delete ${kindLabel(node.kind).toLowerCase()} "${nodeName(node)}"?`)) return;
    try {
      await deleteAdminCategory(node.id);
      toast.success(`${kindLabel(node.kind)} deleted`);
      refreshCatalog();
    } catch (err) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === "string" ? detail : detail?.error || "Delete failed");
    }
  };

  const renderDirectCategories = () => (
    <article className="overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-sm" data-testid="catalog-direct-categories">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4 sm:p-5">
        <div>
          <h2 className="text-base font-semibold text-neutral-900">Categories</h2>
          <p className="mt-1 text-xs text-neutral-400">Product categories in this department</p>
        </div>
        <button type="button" onClick={() => openNew("category", activeDepartment)} className="inline-flex h-9 items-center gap-1.5 rounded-md bg-[#145A46] px-3 text-xs font-semibold text-white hover:bg-[#0f4938]" data-testid="catalog-add-direct-category">
          <Plus className="h-4 w-4" aria-hidden="true" />
          Add category
        </button>
      </div>
      <div>
        {directCategories.length ? directCategories.map((category) => <CategoryRow key={category.id} node={category} onEdit={() => openEdit(category)} onToggle={() => toggleActive(category)} onDelete={() => remove(category)} />) : (
          <div className="border-t border-neutral-100 px-5 py-6 text-sm text-neutral-400">Belum ada category. Tambahkan category pertama untuk department ini.</div>
        )}
      </div>
    </article>
  );

  return (
    <div data-testid="admin-categories-page">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[#17392C]">Catalog</h1>
          <p className="mt-1 text-sm text-neutral-500">Atur katalog dengan urutan Department → Category</p>
        </div>
        <div className="flex items-start gap-2 rounded-lg border border-[#CD9B3A]/20 bg-[#FDF7E9] px-3 py-2.5 text-xs text-[#5e4a26] sm:max-w-md">
          <Info className="mt-0.5 h-4 w-4 shrink-0 text-[#CD9B3A]" aria-hidden="true" />
          <span>Product masuk langsung ke category.</span>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 text-xs text-neutral-400" aria-label="Breadcrumb">
        <span>Catalog</span>
        <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="font-medium text-neutral-700">{activeDepartment ? nodeName(activeDepartment) : "—"}</span>
      </div>

      {isLoading ? <Skeleton className="mt-4 h-96 w-full" /> : isError ? (
        <div className="mt-4 rounded-xl border border-red-200 bg-red-50 px-6 py-10 text-center" data-testid="catalog-error-state">
          <h2 className="text-sm font-semibold text-red-900">Catalog gagal dimuat</h2>
          <p className="mt-1 text-sm text-red-700">Periksa koneksi lalu coba lagi.</p>
          <button type="button" onClick={() => refetch()} className="mt-4 h-9 rounded-md bg-[#145A46] px-4 text-xs font-semibold text-white hover:bg-[#0f4938]">Coba lagi</button>
        </div>
      ) : (
        <div className="mt-4 grid gap-4 lg:grid-cols-[230px_minmax(0,1fr)]">
          <aside className="h-fit rounded-xl border border-neutral-200 bg-white shadow-sm" data-testid="catalog-departments">
            <div className="border-b border-neutral-100 px-4 py-4">
              <h2 className="text-sm font-semibold text-neutral-900">Departments</h2>
              <p className="mt-1 text-xs text-neutral-400">Pilih satu branch untuk dikelola.</p>
            </div>
            <div className="p-2">
              {departments.map((department) => {
                const selected = activeDepartment?.id === department.id;
                return (
                  <button key={department.id} type="button" onClick={() => setSearchParams({ department: department.slug })} className={`flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-sm transition-colors ${selected ? "bg-[#145A46]/10 font-semibold text-[#145A46]" : "text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900"}`} aria-pressed={selected} data-testid={`catalog-department-${department.slug}`}>
                    <span className="min-w-0 truncate">{nodeName(department)}</span>
                    {!department.is_active ? <StatusPill value="inactive" /> : null}
                  </button>
                );
              })}
            </div>
            <div className="border-t border-neutral-100 p-3">
              <button type="button" onClick={() => openNew("department")} className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-md border border-neutral-300 text-xs font-semibold text-neutral-700 hover:border-[#145A46] hover:text-[#145A46]" data-testid="catalog-add-department">
                <Plus className="h-4 w-4" aria-hidden="true" />
                Add department
              </button>
            </div>
          </aside>

          <section className="min-w-0" data-testid="catalog-detail">
            {activeDepartment ? (
              <>
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <h2 className="text-2xl font-semibold tracking-tight text-[#17392C]">{nodeName(activeDepartment)}</h2>
                    <p className="mt-1 text-xs text-neutral-400">Kelola category untuk department ini.</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <NodeActions node={activeDepartment} onEdit={() => openEdit(activeDepartment)} onToggle={() => toggleActive(activeDepartment)} onDelete={() => remove(activeDepartment)} />
                  </div>
                </div>
                <div className="space-y-4">
                  {renderDirectCategories()}
                </div>
              </>
            ) : (
              <div className="rounded-xl border border-dashed border-neutral-300 bg-white px-6 py-12 text-center text-sm text-neutral-400">No departments yet.</div>
            )}
          </section>
        </div>
      )}

      <Dialog open={Boolean(editing)} onOpenChange={(open) => { if (!open) closeEditor(); }}>
        <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto bg-white p-5 sm:p-6">
          <DialogHeader>
            <DialogTitle>{editing === "new" ? `New ${kindLabel(form.kind).toLowerCase()}` : `Edit ${kindLabel(form.kind).toLowerCase()}`}</DialogTitle>
            <DialogDescription>Isi informasi yang diperlukan saja. Detail teknis ada di bagian Advanced.</DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space-y-5" data-testid="category-form">
            <div className="rounded-lg bg-neutral-50 px-3 py-2.5 text-xs text-neutral-500">
              <span className="font-semibold text-neutral-700">Placement:</span> {placementLabel}
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              {LOCALES.map((locale) => (
                <div key={locale}>
                  <label className="mb-1 block text-xs font-medium text-neutral-500">Name ({locale}{locale === "en" ? " — required" : ""})</label>
                  <input value={form.names[locale]} onChange={(e) => setName(locale, e.target.value)} required={locale === "en"} className={inputClass} data-testid={`category-name-${locale}`} />
                </div>
              ))}
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-3">
                {form.media_id && form.image_url ? <ImageWithFallback src={mediaUrl(form.image_url)} alt="" className="h-12 w-12 rounded-md border border-neutral-200 object-cover" /> : <div className="flex h-12 w-12 items-center justify-center rounded-md border border-dashed border-neutral-300 text-[10px] text-neutral-400">No image</div>}
                <div>
                  <p className="text-xs font-medium text-neutral-700">Image</p>
                  <p className="mt-0.5 text-xs text-neutral-400">Optional reusable asset for this node.</p>
                </div>
                <button type="button" onClick={() => setPickerOpen(!pickerOpen)} className="ml-auto h-9 rounded-md border border-neutral-300 px-3 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]" data-testid="category-media-choose">
                  {pickerOpen ? "Hide library" : "Choose image"}
                </button>
                {form.media_id ? <button type="button" onClick={() => setForm((current) => ({ ...current, media_id: null, image_url: "" }))} className="text-xs font-medium text-red-600 hover:underline">Remove</button> : null}
              </div>
              {pickerOpen ? <MediaPicker onClose={() => setPickerOpen(false)} onSelect={(asset) => { setForm((current) => ({ ...current, media_id: asset.id, image_url: asset.url })); setPickerOpen(false); }} /> : null}
            </div>
            <label className="flex items-center gap-2 text-sm" data-testid="category-active-label">
              <input type="checkbox" checked={Boolean(form.is_active)} onChange={(e) => setForm((current) => ({ ...current, is_active: e.target.checked }))} className="accent-[#145A46]" data-testid="category-active" />
              Visible in storefront
            </label>
            <div className="border-t border-neutral-100 pt-3">
              <button type="button" onClick={() => setAdvancedOpen(!advancedOpen)} className="text-xs font-semibold text-neutral-500 hover:text-neutral-900" aria-expanded={advancedOpen}>
                {advancedOpen ? "Hide advanced settings" : "Show advanced settings"}
              </button>
              {advancedOpen ? (
                <div className="mt-3 grid gap-4 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs font-medium text-neutral-500">Stable slug</label>
                    <input value={form.slug || slugify(form.names.en)} onChange={(e) => setForm((current) => ({ ...current, slug: e.target.value }))} disabled={editing !== "new"} className={inputClass} data-testid="category-slug" />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs font-medium text-neutral-500">Sort order</label>
                    <input type="number" min="0" step="1" value={form.sort_order} onChange={(e) => setForm((current) => ({ ...current, sort_order: e.target.value }))} className={inputClass} data-testid="category-sort" />
                  </div>
                </div>
              ) : null}
            </div>
            <DialogFooter>
              <button type="button" onClick={closeEditor} className="h-10 rounded-md border border-neutral-300 px-4 text-sm font-semibold text-neutral-700">Cancel</button>
              <button type="submit" disabled={saving} data-testid="category-save" className="h-10 rounded-md bg-[#145A46] px-5 text-sm font-semibold text-white hover:bg-[#0f4938] disabled:opacity-50">
                {saving ? "Saving…" : "Save"}
              </button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
