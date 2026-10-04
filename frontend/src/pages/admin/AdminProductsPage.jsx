import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { announceProductUpdate } from "@/lib/productUpdateEvents";
import {
  deleteAdminProduct,
  getAdminProducts,
  updateAdminProduct,
} from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, adminDeleteError, fmtMoney, inputClass } from "./adminUtils";

export default function AdminProductsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [deletingId, setDeletingId] = useState(null);
  const [updatingStatusId, setUpdatingStatusId] = useState(null);
  const queryClient = useQueryClient();
  const page = parseInt(params.get("page") || "1", 10);
  const status = params.get("status") || "";
  const inventory = params.get("inventory") || "";

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
  const removeProduct = async (product) => {
    if (deletingId || updatingStatusId || !window.confirm(`Delete product "${product.name}" permanently?`)) return;
    setDeletingId(product.id);
    try {
      await deleteAdminProduct(product.id, product.revision);
      toast.success("Product deleted");
      announceProductUpdate(product.id, product.revision);
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail?.error === "product_changed") {
        toast.warning("The product changed in another session. The list was refreshed; review the latest product before deleting it.");
        queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      } else {
        toast.error(adminDeleteError(err, "Produk"));
      }
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
      const updated = await updateAdminProduct(product.id, {
        status: nextStatus,
        expected_revision: product.revision,
      });
      toast.success(nextStatus === "inactive" ? "Product deactivated" : "Product activated");
      announceProductUpdate(product.id, updated.revision);
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const code = typeof detail === "string" ? detail : detail?.error;
      if (code === "product_changed") {
        toast.warning("The product changed in another session. Its status was not changed; the list is refreshing.");
        queryClient.invalidateQueries({ queryKey: ["admin-products"] });
        return;
      }
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

      <div className="mt-5 grid grid-cols-2 gap-3 sm:flex sm:flex-wrap">
        <form
          className="relative col-span-2 w-full sm:col-span-1 sm:w-64"
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
            className={`${inputClass} w-full pl-9`}
          />
        </form>
        <select value={status} onChange={(e) => setFilter("status", e.target.value)} className={`${inputClass} w-full sm:w-44`} aria-label="Filter product status" data-testid="products-status-filter">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="draft">Draft</option>
          <option value="inactive">Inactive</option>
        </select>
        <select value={inventory} onChange={(e) => setFilter("inventory", e.target.value)} className={`${inputClass} w-full sm:w-44`} aria-label="Filter product inventory" data-testid="products-inventory-filter">
          <option value="">All inventory</option>
          <option value="in_stock">In stock</option>
          <option value="low_stock">Low stock</option>
          <option value="out_of_stock">Out of stock</option>
        </select>
      </div>

      <div className="mt-5 space-y-3 md:hidden" data-testid="products-mobile-list">
        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-40 w-full rounded-lg" />)
          : items.map((p) => (
              <article key={p.id} className="rounded-lg border border-neutral-200 bg-white p-4" data-testid={`product-mobile-card-${p.slug}`}>
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <Link to={`/products/${p.id}`} className="break-words font-semibold text-[#145A46] hover:underline" data-testid={`product-edit-mobile-${p.slug}`}>{p.name}</Link>
                    <p className="mt-1 break-all text-xs text-neutral-400">{p.slug}</p>
                    <p className="mt-1 text-xs text-neutral-600">{p.brand || "—"}</p>
                  </div>
                  <span className="shrink-0 text-right text-sm font-semibold text-neutral-900">{fmtMoney(p.base_price)}</span>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-neutral-100 pt-3 text-xs">
                  <StatusPill value={p.status} />
                  <span className="text-neutral-500">{p.variant_count} varian</span>
                  <span className="text-neutral-500">Stok {p.total_stock}</span>
                  <StatusPill value={p.stock_state} />
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  { ["active", "inactive"].includes(p.status) ? (
                    <button type="button" onClick={() => toggleProductStatus(p)} disabled={deletingId === p.id || updatingStatusId === p.id} className={`inline-flex min-h-11 items-center px-3 text-xs font-semibold hover:bg-neutral-50 disabled:opacity-50 ${p.status === "active" ? "border border-amber-200 text-amber-800" : "border border-[#145A46]/30 text-[#145A46]"}`} data-testid={`product-toggle-status-mobile-${p.slug}`}>
                      {updatingStatusId === p.id ? "Saving…" : p.status === "active" ? "Deactivate" : "Activate"}
                    </button>
                  ) : null}
                  <button type="button" onClick={() => removeProduct(p)} disabled={deletingId === p.id || updatingStatusId === p.id} className="inline-flex min-h-11 items-center gap-1.5 border border-red-200 px-3 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-50" data-testid={`product-delete-mobile-${p.slug}`}>
                    <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />{deletingId === p.id ? "Deleting…" : "Delete"}
                  </button>
                </div>
              </article>
            ))}
        {!isLoading && !items.length ? <div className="rounded-lg border border-neutral-200 bg-white px-4 py-10 text-center text-sm text-neutral-400" data-testid="products-mobile-empty">No products found.</div> : null}
      </div>

      <div className="mt-5 hidden overflow-x-auto border border-neutral-200 bg-white md:block">
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

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-neutral-500" data-testid="products-total">{total} products</span>
        <div className="flex gap-2">
          <button
            disabled={page <= 1}
            onClick={() => setFilter("page", String(page - 1))}
            data-testid="products-prev"
            className="min-h-11 whitespace-nowrap border border-neutral-300 px-3 text-[11px] font-medium disabled:opacity-40 sm:px-4 sm:text-xs"
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
            className="min-h-11 whitespace-nowrap border border-neutral-300 px-3 text-[11px] font-medium disabled:opacity-40 sm:px-4 sm:text-xs"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
