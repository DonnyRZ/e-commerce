import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { getSellerProduct, getSellerProducts, updateSellerInventory } from "@/lib/api";
import { StockBadge } from "@/pages/seller/SellerProductsPage";
import { Skeleton } from "@/components/ui/skeleton";

const inputClass =
  "h-9 w-24 border border-neutral-300 bg-white px-2 text-sm outline-none focus:border-[#145A46]";

function VariantStockRow({ variant, productId }) {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const [value, setValue] = useState(variant.stock_quantity);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    const next = parseInt(value, 10);
    if (Number.isNaN(next) || next < 0) return;
    setSaving(true);
    try {
      await updateSellerInventory(variant.id, next);
      toast.success(t("seller.inventory.updated"));
      queryClient.invalidateQueries({ queryKey: ["seller-inv-product", productId] });
      queryClient.invalidateQueries({ queryKey: ["seller-products"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      if (d?.error === "below_active_reservations") {
        toast.error(t("seller.inventory.floorError", { count: d.active_reservations }));
      } else {
        toast.error(t("seller.inventory.failed"));
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <tr className="border-b border-neutral-100 last:border-0" data-testid={`inv-row-${variant.id}`}>
      <td className="px-4 py-2.5 font-medium">{variant.sku}</td>
      <td className="px-4 py-2.5 text-xs text-neutral-500">
        {Object.entries(variant.option_values || {}).map(([k, v]) => `${k}: ${v}`).join(" · ")}
      </td>
      <td className="px-4 py-2.5">
        <input
          type="number"
          min="0"
          step="1"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          className={inputClass}
          data-testid={`inv-input-${variant.id}`}
        />
      </td>
      <td className="px-4 py-2.5 tabular-nums text-xs" data-testid={`inv-reserved-${variant.id}`}>{variant.active_reserved}</td>
      <td className="px-4 py-2.5 tabular-nums text-xs" data-testid={`inv-available-${variant.id}`}>{variant.available}</td>
      <td className="px-4 py-2.5"><StockBadge state={variant.stock_state} testId={`inv-state-${variant.id}`} /></td>
      <td className="px-4 py-2.5 text-right">
        <button
          onClick={save}
          disabled={saving || parseInt(value, 10) === variant.stock_quantity}
          data-testid={`inv-save-${variant.id}`}
          className="h-9 bg-[#145A46] px-4 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-40"
        >
          {t("seller.inventory.save")}
        </button>
      </td>
    </tr>
  );
}

function ProductInventoryRow({ product }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const detailQuery = useQuery({
    queryKey: ["seller-inv-product", product.id],
    queryFn: () => getSellerProduct(product.id),
    enabled: open,
  });

  return (
    <div className="border-b border-neutral-100 last:border-0" data-testid={`inv-product-${product.id}`}>
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left hover:bg-neutral-50"
        data-testid={`inv-expand-${product.id}`}
      >
        {open ? <ChevronDown className="h-4 w-4 text-neutral-400" /> : <ChevronRight className="h-4 w-4 text-neutral-400" />}
        <span className="flex-1 text-sm font-medium">{product.name}</span>
        <span className="text-xs tabular-nums text-neutral-500">{product.total_stock}</span>
        <StockBadge state={product.stock_state} testId={`inv-product-state-${product.id}`} />
      </button>
      {open ? (
        <div className="border-t border-neutral-100 bg-neutral-50/50">
          {detailQuery.isLoading ? (
            <div className="p-4"><Skeleton className="h-16 w-full" /></div>
          ) : (
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-neutral-400">
                  <th className="px-4 py-2 font-medium">{t("seller.editor.sku")}</th>
                  <th className="px-4 py-2 font-medium">{t("seller.editor.options")}</th>
                  <th className="px-4 py-2 font-medium">{t("seller.inventory.physical")}</th>
                  <th className="px-4 py-2 font-medium">{t("seller.inventory.reserved")}</th>
                  <th className="px-4 py-2 font-medium">{t("seller.inventory.available")}</th>
                  <th className="px-4 py-2 font-medium">{t("seller.products.status")}</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {(detailQuery.data?.variants || []).map((v) => (
                  <VariantStockRow key={v.id} variant={v} productId={product.id} />
                ))}
              </tbody>
            </table>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function SellerInventoryPage() {
  const { t } = useI18n();
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["seller-products", { inventoryPage: page }],
    queryFn: () => getSellerProducts({ page, page_size: 20 }),
  });
  const data = query.data;
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div data-testid="seller-inventory-page">
      <h1 className="text-xl font-semibold tracking-tight">{t("seller.inventory.title")}</h1>
      <p className="mt-1 text-xs text-neutral-400">{t("seller.inventory.hint")}</p>
      <div className="mt-5 border border-neutral-200 bg-white" data-testid="inventory-list">
        {query.isLoading ? (
          <div className="p-5"><Skeleton className="h-40 w-full" /></div>
        ) : (data?.items || []).length === 0 ? (
          <p className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="inventory-empty">{t("seller.products.empty")}</p>
        ) : (
          data.items.map((p) => <ProductInventoryRow key={p.id} product={p} />)
        )}
      </div>
      {totalPages > 1 ? (
        <div className="mt-4 flex items-center gap-3 text-sm">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="inventory-prev" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">{t("seller.products.prev")}</button>
          <span className="text-xs text-neutral-500">{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} data-testid="inventory-next" className="h-9 border border-neutral-300 px-4 disabled:opacity-40">{t("seller.products.next")}</button>
        </div>
      ) : null}
    </div>
  );
}
