import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import { useI18n } from "@/i18n";
import { getSellerProducts } from "@/lib/api";
import PriceDisplay from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

const inputClass =
  "h-10 border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";

export function StockBadge({ state, testId }) {
  const { t } = useI18n();
  const styles = {
    in_stock: "bg-[#145A46]/10 text-[#145A46]",
    low_stock: "bg-amber-100 text-amber-800",
    out_of_stock: "bg-red-100 text-red-700",
  };
  return (
    <span data-testid={testId} className={`inline-block px-2 py-0.5 text-[11px] font-semibold ${styles[state] || "bg-neutral-100 text-neutral-600"}`}>
      {t(`seller.stock.${state}`)}
    </span>
  );
}

export function ProductStatusBadge({ status, testId }) {
  const { t } = useI18n();
  const styles = {
    active: "bg-[#145A46] text-white",
    draft: "bg-neutral-200 text-neutral-700",
    inactive: "bg-neutral-400 text-white",
  };
  return (
    <span data-testid={testId} className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase ${styles[status] || "bg-neutral-200 text-neutral-600"}`}>
      {t(`seller.status.${status}`)}
    </span>
  );
}

export default function SellerProductsPage() {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [inventory, setInventory] = useState("");
  const [page, setPage] = useState(1);

  const query = useQuery({
    queryKey: ["seller-products", { search, status, inventory, page }],
    queryFn: () =>
      getSellerProducts({
        q: search || undefined,
        status: status || undefined,
        inventory: inventory || undefined,
        page,
        page_size: 20,
      }),
  });

  const data = query.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div data-testid="seller-products-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">{t("seller.products.title")}</h1>
        <Link
          to="/seller/products/new"
          data-testid="products-new"
          className="inline-flex h-10 items-center gap-2 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t("seller.products.new")}
        </Link>
      </div>

      <form
        className="mt-5 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSearch(q);
        }}
      >
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("seller.products.searchPlaceholder")}
            data-testid="products-search"
            className={`${inputClass} w-64 pl-9`}
          />
        </div>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className={inputClass} data-testid="products-filter-status" aria-label={t("seller.products.status")}>
          <option value="">{t("seller.products.allStatuses")}</option>
          <option value="active">{t("seller.status.active")}</option>
          <option value="draft">{t("seller.status.draft")}</option>
          <option value="inactive">{t("seller.status.inactive")}</option>
        </select>
        <select value={inventory} onChange={(e) => { setInventory(e.target.value); setPage(1); }} className={inputClass} data-testid="products-filter-inventory" aria-label={t("seller.products.inventory")}>
          <option value="">{t("seller.products.allInventory")}</option>
          <option value="in_stock">{t("seller.stock.in_stock")}</option>
          <option value="low_stock">{t("seller.stock.low_stock")}</option>
          <option value="out_of_stock">{t("seller.stock.out_of_stock")}</option>
        </select>
      </form>

      <div className="mt-4 overflow-x-auto border border-neutral-200 bg-white" data-testid="products-table-wrap">
        {query.isLoading ? (
          <div className="p-5"><Skeleton className="h-40 w-full" /></div>
        ) : (data?.items || []).length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="products-empty">
            {t("seller.products.empty")}
          </p>
        ) : (
          <table className="w-full min-w-[640px] text-sm" data-testid="products-table">
            <thead>
              <tr className="border-b border-neutral-100 text-left text-xs text-neutral-400">
                <th className="px-5 py-2.5 font-medium">{t("seller.products.product")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.products.status")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.products.price")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.products.variants")}</th>
                <th className="px-4 py-2.5 font-medium">{t("seller.products.stock")}</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {data.items.map((p) => (
                <tr key={p.id} className="border-b border-neutral-50 last:border-0 hover:bg-neutral-50" data-testid={`product-row-${p.id}`}>
                  <td className="px-5 py-3">
                    <p className="font-medium">{p.name}</p>
                    <p className="text-xs text-neutral-400">{p.slug}</p>
                  </td>
                  <td className="px-4 py-3"><ProductStatusBadge status={p.status} testId={`product-status-${p.id}`} /></td>
                  <td className="px-4 py-3"><PriceDisplay amount={p.base_price} className="text-xs" /></td>
                  <td className="px-4 py-3 tabular-nums">{p.variant_count}</td>
                  <td className="px-4 py-3">
                    <span className="mr-2 tabular-nums">{p.total_stock}</span>
                    <StockBadge state={p.stock_state} testId={`product-stock-${p.id}`} />
                  </td>
                  <td className="px-4 py-3 text-right">
                    <Link
                      to={`/seller/products/${p.id}`}
                      data-testid={`product-edit-${p.id}`}
                      className="text-xs font-semibold text-[#145A46] hover:underline"
                    >
                      {t("seller.products.edit")}
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {totalPages > 1 ? (
        <div className="mt-4 flex items-center gap-3 text-sm" data-testid="products-pagination">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="products-prev" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">
            {t("seller.products.prev")}
          </button>
          <span className="text-xs text-neutral-500">{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} data-testid="products-next" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">
            {t("seller.products.next")}
          </button>
        </div>
      ) : null}
    </div>
  );
}
