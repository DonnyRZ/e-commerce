import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { deleteAdminProduct, getAdminProducts } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, adminDeleteError, fmtMoney, inputClass } from "./adminUtils";

export default function AdminProductsPage() {
  const [params, setParams] = useSearchParams();
  const [q, setQ] = useState(params.get("q") || "");
  const [deletingId, setDeletingId] = useState(null);
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
    if (deletingId || !window.confirm(`Delete product "${product.name}" permanently?`)) return;
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
                      <button
                        type="button"
                        onClick={() => removeProduct(p)}
                        disabled={deletingId === p.id}
                        className="inline-flex items-center gap-1 text-xs font-medium text-red-700 hover:underline disabled:opacity-50"
                        data-testid={`product-delete-${p.slug}`}
                      >
                        <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                        {deletingId === p.id ? "Deleting…" : "Delete"}
                      </button>
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
