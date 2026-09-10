import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import {
  createSellerProduct,
  createSellerVariant,
  getCatalogCategories,
  getSellerProduct,
  updateSellerInventory,
  updateSellerProduct,
  updateSellerVariant,
} from "@/lib/api";
import { pickLocalized } from "@/lib/localize";
import { Skeleton } from "@/components/ui/skeleton";

const inputClass =
  "h-10 w-full border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";
const LOCALES = ["en", "id", "uz", "ru"];
const EMPTY_VARIANT = { sku: "", optionsText: "", stock: 0, price_override: "", sale_price_override: "", is_active: true };

function parseOptions(text) {
  const out = {};
  for (const pair of text.split(",")) {
    const [k, ...rest] = pair.split("=");
    const key = k.trim();
    const value = rest.join("=").trim();
    if (key && value) out[key] = value;
  }
  return out;
}

function optionsToText(obj) {
  return Object.entries(obj || {}).map(([k, v]) => `${k}=${v}`).join(", ");
}

export default function SellerProductEditPage() {
  const { t, locale } = useI18n();
  const { productId } = useParams();
  const isNew = !productId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    category_id: "", product_type: "general", brand: "",
    base_price: "", compare_at_price: "", status: "draft", image_url: "",
  });
  const [tr, setTr] = useState({ en: { name: "", short_description: "", description: "" } });
  const [activeLocale, setActiveLocale] = useState("en");
  const [variants, setVariants] = useState([{ ...EMPTY_VARIANT }]);
  const [saving, setSaving] = useState(false);

  const categoriesQuery = useQuery({ queryKey: ["catalog-categories"], queryFn: getCatalogCategories });
  const productQuery = useQuery({
    queryKey: ["seller-product", productId],
    queryFn: () => getSellerProduct(productId),
    enabled: !isNew,
  });

  useEffect(() => {
    const p = productQuery.data;
    if (!p) return;
    setForm({
      category_id: p.category_id, product_type: p.product_type, brand: p.brand,
      base_price: String(p.base_price),
      compare_at_price: p.compare_at_price != null ? String(p.compare_at_price) : "",
      status: p.status, image_url: p.media?.[0]?.url || "",
    });
    setTr(p.translations || { en: { name: "" } });
    setVariants(
      p.variants.map((v) => ({
        id: v.id, sku: v.sku, optionsText: optionsToText(v.option_values),
        stock: v.stock_quantity,
        price_override: v.price_override != null ? String(v.price_override) : "",
        sale_price_override: v.sale_price_override != null ? String(v.sale_price_override) : "",
        is_active: v.is_active,
      }))
    );
  }, [productQuery.data]);

  const setF = (key) => (e) => setForm({ ...form, [key]: e.target.value });
  const setT = (key) => (e) =>
    setTr({ ...tr, [activeLocale]: { ...(tr[activeLocale] || {}), [key]: e.target.value } });
  const setV = (idx, key, value) =>
    setVariants(variants.map((v, i) => (i === idx ? { ...v, [key]: value } : v)));

  const categories = categoriesQuery.data || [];
  const catItems = Array.isArray(categories) ? categories : categories.items || [];

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      const translations = Object.fromEntries(
        Object.entries(tr).filter(([, v]) => v && v.name && v.name.trim())
      );
      const base = {
        category_id: form.category_id,
        product_type: form.product_type,
        brand: form.brand,
        base_price: parseInt(form.base_price, 10),
        compare_at_price: form.compare_at_price === "" ? null : parseInt(form.compare_at_price, 10),
        status: form.status,
        media: form.image_url ? [{ url: form.image_url }] : [],
        translations,
      };
      if (isNew) {
        const created = await createSellerProduct({
          ...base,
          variants: variants.map((v) => ({
            sku: v.sku.trim(),
            option_values: parseOptions(v.optionsText),
            stock_quantity: parseInt(v.stock, 10) || 0,
            price_override: v.price_override === "" ? null : parseInt(v.price_override, 10),
            sale_price_override: v.sale_price_override === "" ? null : parseInt(v.sale_price_override, 10),
            image_url: form.image_url || null,
            is_active: Boolean(v.is_active),
          })),
        });
        toast.success(t("seller.editor.saved"));
        queryClient.invalidateQueries({ queryKey: ["seller-products"] });
        navigate(`/seller/products/${created.id}`, { replace: true });
        return;
      }
      // edit: product fields + translations
      await updateSellerProduct(productId, base);
      // variants: update existing, create new
      for (const v of variants) {
        const body = {
          option_values: parseOptions(v.optionsText),
          price_override: v.price_override === "" ? null : parseInt(v.price_override, 10),
          sale_price_override: v.sale_price_override === "" ? null : parseInt(v.sale_price_override, 10),
          is_active: Boolean(v.is_active),
        };
        if (v.id) {
          await updateSellerVariant(v.id, { ...body, sku: v.sku.trim() });
          const current = productQuery.data.variants.find((x) => x.id === v.id);
          const nextStock = parseInt(v.stock, 10) || 0;
          if (current && current.stock_quantity !== nextStock) {
            await updateSellerInventory(v.id, nextStock);
          }
        } else if (v.sku.trim()) {
          await createSellerVariant(productId, {
            ...body, sku: v.sku.trim(),
            stock_quantity: parseInt(v.stock, 10) || 0,
            image_url: form.image_url || null,
          });
        }
      }
      toast.success(t("seller.editor.saved"));
      queryClient.invalidateQueries({ queryKey: ["seller-product", productId] });
      queryClient.invalidateQueries({ queryKey: ["seller-products"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "string" ? d : d?.error;
      if (code === "sku_exists" || code === "sku_duplicate_in_payload") {
        toast.error(t("seller.editor.skuExists"));
      } else if (code === "below_active_reservations") {
        toast.error(t("seller.editor.reservationFloor", { count: d.active_reservations }));
      } else {
        toast.error(t("seller.editor.failed"));
      }
    } finally {
      setSaving(false);
    }
  };

  const archive = async () => {
    try {
      await updateSellerProduct(productId, { status: "inactive" });
      toast.success(t("seller.editor.archived"));
      queryClient.invalidateQueries({ queryKey: ["seller-product", productId] });
      queryClient.invalidateQueries({ queryKey: ["seller-products"] });
    } catch {
      toast.error(t("seller.editor.failed"));
    }
  };

  if (!isNew && productQuery.isLoading) {
    return <div data-testid="editor-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  }

  const tab = tr[activeLocale] || {};

  return (
    <div data-testid="seller-product-editor">
      <Link to="/seller/products" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900" data-testid="editor-back">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        {t("seller.editor.backToProducts")}
      </Link>
      <h1 className="mt-2 text-xl font-semibold tracking-tight">
        {isNew ? t("seller.editor.createTitle") : t("seller.editor.editTitle")}
      </h1>

      <form onSubmit={save} className="mt-6 space-y-6">
        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-basics">
          <h2 className="text-sm font-semibold">{t("seller.editor.basics")}</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.category")}</label>
              <select value={form.category_id} onChange={setF("category_id")} required className={inputClass} data-testid="editor-category">
                <option value="" disabled>—</option>
                {catItems.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name || (c.translations ? pickLocalized(c.translations, locale) : null) || c.slug}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.type")}</label>
              <select value={form.product_type} onChange={setF("product_type")} className={inputClass} data-testid="editor-type">
                <option value="general">general</option>
                <option value="apparel">apparel</option>
                <option value="hijab">hijab</option>
                <option value="skincare">skincare</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.brand")}</label>
              <input value={form.brand} onChange={setF("brand")} className={inputClass} data-testid="editor-brand" maxLength={120} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.basePrice")} (UZS)</label>
              <input type="number" min="0" step="1" required value={form.base_price} onChange={setF("base_price")} className={inputClass} data-testid="editor-base-price" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.compareAt")} (UZS)</label>
              <input type="number" min="0" step="1" value={form.compare_at_price} onChange={setF("compare_at_price")} className={inputClass} data-testid="editor-compare-at" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.status")}</label>
              <select value={form.status} onChange={setF("status")} className={inputClass} data-testid="editor-status">
                <option value="draft">{t("seller.status.draft")}</option>
                <option value="active">{t("seller.status.active")}</option>
                <option value="inactive">{t("seller.status.inactive")}</option>
              </select>
            </div>
            <div className="sm:col-span-2 xl:col-span-3">
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.imageUrl")}</label>
              <input type="url" value={form.image_url} onChange={setF("image_url")} className={inputClass} data-testid="editor-image-url" placeholder="https://…" />
              <p className="mt-1 text-[11px] text-neutral-400">{t("seller.editor.mediaHint")}</p>
            </div>
          </div>
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-translations">
          <h2 className="text-sm font-semibold">{t("seller.editor.translations")}</h2>
          <div className="mt-3 flex gap-1" role="tablist">
            {LOCALES.map((loc) => (
              <button
                key={loc}
                type="button"
                role="tab"
                aria-selected={activeLocale === loc}
                data-testid={`editor-locale-${loc}`}
                onClick={() => setActiveLocale(loc)}
                className={`h-9 px-4 text-xs font-semibold uppercase tracking-wide ${
                  activeLocale === loc ? "bg-[#145A46] text-white" : "bg-neutral-100 text-neutral-600 hover:bg-neutral-200"
                }`}
              >
                {loc}
                {tr[loc]?.name ? " •" : ""}
              </button>
            ))}
          </div>
          <div className="mt-4 grid gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">
                {t("seller.editor.name")} ({activeLocale}{activeLocale === "en" ? " — required" : ""})
              </label>
              <input
                value={tab.name || ""}
                onChange={setT("name")}
                required={activeLocale === "en"}
                className={inputClass}
                data-testid={`editor-name-${activeLocale}`}
                maxLength={255}
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.shortDesc")}</label>
              <input value={tab.short_description || ""} onChange={setT("short_description")} className={inputClass} data-testid={`editor-short-${activeLocale}`} maxLength={500} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.editor.description")}</label>
              <textarea value={tab.description || ""} onChange={setT("description")} rows={4} className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]" data-testid={`editor-desc-${activeLocale}`} />
            </div>
          </div>
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-variants">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">{t("seller.editor.variants")}</h2>
            <button
              type="button"
              onClick={() => setVariants([...variants, { ...EMPTY_VARIANT }])}
              data-testid="editor-add-variant"
              className="inline-flex h-9 items-center gap-1.5 border border-neutral-300 px-3 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              {t("seller.editor.addVariant")}
            </button>
          </div>
          <p className="mt-1 text-[11px] text-neutral-400">{t("seller.editor.optionsHint")}</p>
          <div className="mt-3 space-y-3">
            {variants.map((v, idx) => (
              <div key={idx} className="grid items-end gap-3 border border-neutral-100 p-3 sm:grid-cols-2 xl:grid-cols-[1fr_1.4fr_0.6fr_0.7fr_0.7fr_auto_auto]" data-testid={`editor-variant-${idx}`}>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">{t("seller.editor.sku")}</label>
                  <input value={v.sku} onChange={(e) => setV(idx, "sku", e.target.value)} required className={inputClass} data-testid={`variant-sku-${idx}`} maxLength={80} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">{t("seller.editor.options")}</label>
                  <input value={v.optionsText} onChange={(e) => setV(idx, "optionsText", e.target.value)} className={inputClass} data-testid={`variant-options-${idx}`} placeholder="color=Black, size=M" />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">{t("seller.editor.stock")}</label>
                  <input type="number" min="0" step="1" value={v.stock} onChange={(e) => setV(idx, "stock", e.target.value)} className={inputClass} data-testid={`variant-stock-${idx}`} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">{t("seller.editor.priceOverride")}</label>
                  <input type="number" min="0" step="1" value={v.price_override} onChange={(e) => setV(idx, "price_override", e.target.value)} className={inputClass} data-testid={`variant-price-${idx}`} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">{t("seller.editor.saleOverride")}</label>
                  <input type="number" min="0" step="1" value={v.sale_price_override} onChange={(e) => setV(idx, "sale_price_override", e.target.value)} className={inputClass} data-testid={`variant-sale-${idx}`} />
                </div>
                <label className="flex h-10 items-center gap-2 text-xs" data-testid={`variant-active-label-${idx}`}>
                  <input type="checkbox" checked={Boolean(v.is_active)} onChange={(e) => setV(idx, "is_active", e.target.checked)} className="accent-[#145A46]" data-testid={`variant-active-${idx}`} />
                  {t("seller.editor.active")}
                </label>
                {variants.length > 1 && !v.id ? (
                  <button type="button" onClick={() => setVariants(variants.filter((_, i) => i !== idx))} className="flex h-10 items-center text-neutral-400 hover:text-red-600" aria-label="remove" data-testid={`variant-remove-${idx}`}>
                    <Trash2 className="h-4 w-4" />
                  </button>
                ) : <span className="w-4" />}
              </div>
            ))}
          </div>
        </section>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            data-testid="editor-save"
            className="h-11 bg-[#145A46] px-8 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving ? t("seller.editor.saving") : t("seller.editor.save")}
          </button>
          {!isNew && form.status !== "inactive" ? (
            <button type="button" onClick={archive} data-testid="editor-archive" className="h-11 border border-neutral-300 px-6 text-sm font-medium text-neutral-600 hover:border-red-600 hover:text-red-600">
              {t("seller.editor.archive")}
            </button>
          ) : null}
        </div>
      </form>
    </div>
  );
}
