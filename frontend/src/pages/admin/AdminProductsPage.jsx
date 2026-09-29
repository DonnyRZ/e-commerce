import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, Plus, Ruler, Search, Settings2, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  applyAdminProductSizePresets,
  deleteAdminProduct,
  getAdminProductSizePresets,
  getAdminProducts,
  previewAdminProductSizePresets,
  saveAdminProductSizePresets,
  updateAdminProduct,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, adminDeleteError, fmtMoney, inputClass } from "./adminUtils";

export default function AdminProductsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [deletingId, setDeletingId] = useState(null);
  const [updatingStatusId, setUpdatingStatusId] = useState(null);
  const [clothingSizes, setClothingSizes] = useState("");
  const [footwearSizes, setFootwearSizes] = useState("");
  const [sizePreview, setSizePreview] = useState(null);
  const [savingSizePresets, setSavingSizePresets] = useState(false);
  const [previewingSizePresets, setPreviewingSizePresets] = useState(false);
  const [applyingSizePresets, setApplyingSizePresets] = useState(false);
  const queryClient = useQueryClient();
  const page = parseInt(params.get("page") || "1", 10);
  const status = params.get("status") || "";
  const inventory = params.get("inventory") || "";

  const sizePresetsQuery = useQuery({
    queryKey: ["admin-product-size-presets"],
    queryFn: getAdminProductSizePresets,
  });

  useEffect(() => {
    if (!sizePresetsQuery.data) return;
    setClothingSizes(sizePresetsQuery.data.clothing_sizes.join(", "));
    setFootwearSizes(sizePresetsQuery.data.footwear_sizes.join(", "));
  }, [sizePresetsQuery.data]);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-products", { q: params.get("q") || "", status, inventory, page }],
    queryFn: () =>
      getAdminProducts({ q: params.get("q") || undefined, status: status || undefined, inventory: inventory || undefined, page }),
  });

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  };

  const items = data?.items || [];
  const total = data?.total || 0;
  const pageSize = data?.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const parseSizes = (value) => value.split(/[,;\n]+/).map((item) => item.trim()).filter(Boolean);
  const savedPresets = sizePresetsQuery.data;
  const presetsDirty = Boolean(savedPresets) && (
    parseSizes(clothingSizes).join("|") !== savedPresets.clothing_sizes.join("|") ||
    parseSizes(footwearSizes).join("|") !== savedPresets.footwear_sizes.join("|")
  );

  const saveSizePresets = async () => {
    const clothing = parseSizes(clothingSizes);
    const footwear = parseSizes(footwearSizes);
    if (!clothing.length || !footwear.length) {
      toast.error("Isi minimal satu ukuran untuk pakaian dan alas kaki.");
      return;
    }
    setSavingSizePresets(true);
    try {
      const result = await saveAdminProductSizePresets({
        clothing_sizes: clothing,
        footwear_sizes: footwear,
      });
      queryClient.setQueryData(["admin-product-size-presets"], result);
      setSizePreview(null);
      toast.success("Preset ukuran tersimpan. Toko tetap memakai preset yang terakhir diterapkan sampai proses penerapan selesai.");
    } catch (err) {
      const code = err?.response?.data?.detail?.error || err?.response?.data?.detail;
      toast.error(code === "invalid_size_preset" ? "Ukuran harus unik, tidak kosong, maksimal 32 karakter, dan paling banyak 24 ukuran." : "Preset ukuran gagal disimpan.");
    } finally {
      setSavingSizePresets(false);
    }
  };

  const previewSizePresets = async () => {
    setPreviewingSizePresets(true);
    try {
      setSizePreview(await previewAdminProductSizePresets());
    } catch {
      toast.error("Pratinjau ukuran gagal dimuat. Coba lagi.");
    } finally {
      setPreviewingSizePresets(false);
    }
  };

  const applySizePresets = async () => {
    if (!sizePreview || applyingSizePresets) return;
    const confirmed = window.confirm(
      `Terapkan ukuran ke ${sizePreview.product_count} produk? ${sizePreview.variants_to_add} varian baru akan dibuat. Stok varian baru 0; varian dan order lama tidak dihapus.`
    );
    if (!confirmed) return;
    setApplyingSizePresets(true);
    try {
      const result = await applyAdminProductSizePresets(sizePreview.preview_digest);
      queryClient.setQueryData(["admin-product-size-presets"], result);
      setSizePreview(null);
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
      queryClient.invalidateQueries({ queryKey: ["product"] });
      toast.success(`Preset diterapkan: ${result.variants_added} varian ditambahkan pada ${result.products_changed} produk.`);
    } catch (err) {
      const code = err?.response?.data?.detail?.error;
      if (code === "size_preset_preview_stale") {
        setSizePreview(null);
        toast.error("Katalog berubah setelah pratinjau. Muat pratinjau baru sebelum menerapkan.");
      } else {
        toast.error("Preset tidak diterapkan. Tidak ada perubahan parsial yang disimpan.");
      }
    } finally {
      setApplyingSizePresets(false);
    }
  };

  const removeProduct = async (product) => {
    if (deletingId || updatingStatusId || !window.confirm(`Delete product "${product.name}" permanently?`)) return;
    setDeletingId(product.id);
    try {
      await deleteAdminProduct(product.id);
      toast.success("Product deleted");
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
    } catch (err) {
      toast.error(adminDeleteError(err, "Produk"));
    } finally {
      setDeletingId(null);
    }
  };

  const toggleProductStatus = async (product) => {
    if (deletingId || updatingStatusId || !["active", "inactive"].includes(product.status)) return;
    const nextStatus = product.status === "active" ? "inactive" : "active";
    const action = nextStatus === "inactive" ? "deactivate" : "activate";
    if (!window.confirm(`${action === "deactivate" ? "Deactivate" : "Activate"} product "${product.name}"?`)) return;

    setUpdatingStatusId(product.id);
    try {
      await updateAdminProduct(product.id, { status: nextStatus });
      toast.success(nextStatus === "inactive" ? "Product deactivated" : "Product activated");
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "string" ? detail : detail?.error;
      toast.error(
        code === "invalid_category"
          ? "Product must use an active leaf category before it can be activated."
          : code === "product_type_category_mismatch"
            ? "Product type and category must match before activation."
            : "Product status could not be updated. Open the product to review its fields."
      );
    } finally {
      setUpdatingStatusId(null);
    }
  };

  return (
    <div data-testid="admin-products-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">Products</h1>
        <Link
          to="/products/new"
          data-testid="products-new-button"
          className="inline-flex h-10 items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New Product
        </Link>
      </div>

      <section className="mt-5 border border-neutral-200 bg-white p-4 sm:p-5" data-testid="product-size-presets">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 inline-flex h-9 w-9 items-center justify-center bg-[#eff6f3] text-[#145A46]"><Ruler className="h-4 w-4" aria-hidden="true" /></span>
            <div>
              <h2 className="text-sm font-semibold">Preset ukuran katalog</h2>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-neutral-500">CMS menyimpan ukuran; toko membaca ukuran dari varian produk. Pratinjau dulu sebelum menambah varian ke produk lama. Varian lama tidak dihapus.</p>
            </div>
          </div>
          <span className="text-[11px] text-neutral-500">
            Pakaian: {savedPresets?.applied_clothing_sizes ? "diterapkan" : "belum diterapkan"} · Alas kaki: {savedPresets?.applied_footwear_sizes ? "diterapkan" : "belum diterapkan"}
          </span>
        </div>

        {sizePresetsQuery.isLoading ? (
          <Skeleton className="mt-4 h-16 w-full" />
        ) : sizePresetsQuery.isError ? (
          <p className="mt-4 text-xs text-red-700">Preset ukuran gagal dimuat. Muat ulang halaman atau periksa akses admin.</p>
        ) : (
          <>
            <div className="mt-4 grid gap-3 md:grid-cols-2">
              <label className="text-xs font-medium text-neutral-600">Pakaian
                <input value={clothingSizes} onChange={(event) => { setClothingSizes(event.target.value); setSizePreview(null); }} disabled={savingSizePresets || previewingSizePresets || applyingSizePresets} className={`${inputClass} mt-1`} placeholder="Pisahkan tiap ukuran dengan koma" data-testid="size-preset-clothing" />
              </label>
              <label className="text-xs font-medium text-neutral-600">Alas kaki
                <input value={footwearSizes} onChange={(event) => { setFootwearSizes(event.target.value); setSizePreview(null); }} disabled={savingSizePresets || previewingSizePresets || applyingSizePresets} className={`${inputClass} mt-1`} placeholder="Pisahkan tiap ukuran dengan koma" data-testid="size-preset-footwear" />
              </label>
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button type="button" onClick={saveSizePresets} disabled={!presetsDirty || savingSizePresets || previewingSizePresets || applyingSizePresets} className="inline-flex h-9 items-center gap-1.5 border border-neutral-300 px-3 text-xs font-semibold hover:border-[#145A46] disabled:cursor-not-allowed disabled:opacity-45" data-testid="size-presets-save">
                <Check className="h-3.5 w-3.5" aria-hidden="true" />{savingSizePresets ? "Menyimpan…" : "Simpan preset"}
              </button>
              <button type="button" onClick={previewSizePresets} disabled={presetsDirty || savingSizePresets || previewingSizePresets || applyingSizePresets} className="inline-flex h-9 items-center gap-1.5 border border-neutral-300 px-3 text-xs font-semibold hover:border-[#145A46] disabled:cursor-not-allowed disabled:opacity-45" data-testid="size-presets-preview">
                <Eye className="h-3.5 w-3.5" aria-hidden="true" />{previewingSizePresets ? "Memuat…" : "Pratinjau produk"}
              </button>
              {presetsDirty ? <span className="text-[11px] text-amber-700">Simpan perubahan sebelum membuat pratinjau.</span> : null}
            </div>
            {sizePreview ? (
              <div className="mt-4 border border-amber-200 bg-amber-50/60 p-3" data-testid="size-presets-preview-result">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-semibold text-neutral-800">Pratinjau penerapan</p>
                    <p className="mt-1 text-xs text-neutral-600">{sizePreview.variants_to_add} varian baru untuk {sizePreview.products_changed} dari {sizePreview.product_count} produk. Varian baru memakai harga dasar dan stok 0.</p>
                  </div>
                  <button type="button" onClick={applySizePresets} disabled={presetsDirty || applyingSizePresets || previewingSizePresets} className="inline-flex h-9 items-center gap-1.5 bg-[#145A46] px-3 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50" data-testid="size-presets-apply">
                    <Settings2 className="h-3.5 w-3.5" aria-hidden="true" />{applyingSizePresets ? "Menerapkan…" : "Terapkan ukuran"}
                  </button>
                </div>
                <div className="mt-3 max-h-48 space-y-1 overflow-auto border-t border-amber-200 pt-2">
                  {sizePreview.products.filter((product) => product.variants_to_add > 0).map((product) => (
                    <div key={product.id} className="flex items-start justify-between gap-3 text-xs text-neutral-700">
                      <span className="min-w-0">
                        <span className="block truncate">{product.name}</span>
                        <span className="mt-0.5 block text-[10px] text-neutral-500">
                          {product.variant_options.map((options) => Object.values(options).join(" / ")).join(", ")}
                          {product.more_variants ? `, +${product.more_variants} lainnya` : ""}
                        </span>
                      </span>
                      <span className="shrink-0 text-neutral-500">+{product.variants_to_add} varian</span>
                    </div>
                  ))}
                  {sizePreview.variants_to_add === 0 ? <p className="text-xs text-neutral-600">Semua kombinasi ukuran sudah tersedia. Penerapan tetap akan mengaktifkan filter ukuran toko.</p> : null}
                </div>
              </div>
            ) : null}
          </>
        )}
      </section>

      <div className="mt-5 flex flex-wrap gap-3">
        <form
          className="relative"
          onSubmit={(e) => {
            e.preventDefault();
            setFilter("q", q.trim());
          }}
        >
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search products…"
            data-testid="products-search"
            className={`${inputClass} w-64 pl-9`}
          />
        </form>
        <select value={status} onChange={(e) => setFilter("status", e.target.value)} className={`${inputClass} w-44`} data-testid="products-status-filter">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="inactive">Inactive</option>
        </select>
        <select value={inventory} onChange={(e) => setFilter("inventory", e.target.value)} className={`${inputClass} w-44`} data-testid="products-inventory-filter">
          <option value="">All inventory</option>
          <option value="in_stock">In stock</option>
          <option value="low_stock">Low stock</option>
          <option value="out_of_stock">Out of stock</option>
        </select>
      </div>

      <div className="mt-5 overflow-x-auto border border-neutral-200 bg-white">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-3 font-medium">Product</th>
              <th className="px-5 py-3 font-medium">Brand</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Variants</th>
              <th className="px-5 py-3 font-medium">Stock</th>
              <th className="px-5 py-3 text-right font-medium">Price</th>
              <th className="px-5 py-3 text-right font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={7} className="px-5 py-3"><Skeleton className="h-5 w-full" /></td></tr>
                ))
              : items.map((p) => (
                  <tr key={p.id} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`product-row-${p.slug}`}>
                    <td className="px-5 py-3">
                      <Link to={`/products/${p.id}`} className="font-medium text-[#145A46] hover:underline" data-testid={`product-edit-${p.slug}`}>
                        {p.name}
                      </Link>
                      <p className="text-xs text-neutral-400">{p.slug}</p>
                    </td>
                    <td className="px-5 py-3 text-neutral-600">{p.brand || "—"}</td>
                    <td className="px-5 py-3"><StatusPill value={p.status} /></td>
                    <td className="px-5 py-3">{p.variant_count}</td>
                    <td className="px-5 py-3">
                      <span className="mr-2 font-medium">{p.total_stock}</span>
                      <StatusPill value={p.stock_state} />
                    </td>
                    <td className="px-5 py-3 text-right font-medium">{fmtMoney(p.base_price)}</td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex flex-wrap justify-end gap-x-3 gap-y-1">
                        {["active", "inactive"].includes(p.status) ? (
                          <button
                            type="button"
                            onClick={() => toggleProductStatus(p)}
                            disabled={deletingId === p.id || updatingStatusId === p.id}
                            className={`text-xs font-medium hover:underline disabled:opacity-50 ${p.status === "active" ? "text-amber-700" : "text-[#145A46]"}`}
                            data-testid={`product-toggle-status-${p.slug}`}
                          >
                            {updatingStatusId === p.id ? "Saving…" : p.status === "active" ? "Deactivate" : "Activate"}
                          </button>
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeProduct(p)}
                          disabled={deletingId === p.id || updatingStatusId === p.id}
                          className="inline-flex items-center gap-1 text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                          data-testid={`product-delete-${p.slug}`}
                        >
                          <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                          {deletingId === p.id ? "Deleting…" : "Delete"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            {!isLoading && !items.length ? (
              <tr><td colSpan={7} className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="products-empty">No products found.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm">
        <span className="text-neutral-500" data-testid="products-total">{total} products</span>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setFilter("page", String(page - 1))}
            data-testid="products-prev"
            className="h-9 border border-neutral-300 px-4 text-xs font-medium disabled:opacity-40"
          >
            Previous
          </button>
          <span className="flex h-9 items-center px-2 text-xs text-neutral-500" data-testid="products-page-indicator">
            Page {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setFilter("page", String(page + 1))}
            data-testid="products-next"
            className="h-9 border border-neutral-300 px-4 text-xs font-medium disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
