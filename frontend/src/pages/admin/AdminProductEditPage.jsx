import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight, ImagePlus, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import {
  createAdminProduct,
  deleteAdminProduct,
  deleteAdminVariant,
  getAdminCategories,
  getAdminProduct,
  saveAdminProductEditor,
  uploadCmsMedia,
} from "@/lib/api";
import { mediaUrl, pickLocalized } from "@/lib/localize";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";
import { adminDeleteError, inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];
const EMPTY_VARIANT = { sku: "", size: "", preservedOptions: {}, stock: 0, price_override: "", sale_price_override: "", media_id: null, image_url: "", is_active: true };

const sizeFromOptions = (obj) =>
  typeof obj?.size === "string" || typeof obj?.size === "number" ? String(obj.size) : "";

// The editor now exposes only the size field. Keep any existing option keys
// (for example color, volume, or format) hidden and intact when an old product
// is edited, so simplifying the form does not silently rewrite catalog data.
const preservedOptionsFrom = (obj) =>
  Object.fromEntries(Object.entries(obj || {}).filter(([key]) => key !== "size"));

const optionsFromSize = (size, preservedOptions = {}) => {
  const value = String(size || "").trim();
  return value ? { ...preservedOptions, size: value } : { ...preservedOptions };
};

const MAX_PRODUCT_IMAGES = 8;

const OPTIONAL_MATERIAL_FIELD = ["material", "Material (optional)"];

const ATTRIBUTE_FIELDS = {
  apparel: [OPTIONAL_MATERIAL_FIELD],
  hijab: [OPTIONAL_MATERIAL_FIELD],
  batik: [OPTIONAL_MATERIAL_FIELD],
  skincare: [
    ["skin_type", "Skin type"],
    ["ingredients", "Ingredients"],
    ["benefits", "Benefits"],
    ["directions", "How to use"],
  ],
  parfum: [
    ["fragrance_family", "Fragrance family"],
    ["notes", "Notes"],
    ["concentration", "Concentration"],
    ["usage", "How to wear"],
  ],
};

// Product family is an internal compatibility field. The operator chooses a
// leaf category; the editor derives the family from that category instead of
// exposing a second, confusing taxonomy selector.
const PRODUCT_TYPE_BY_DEPARTMENT = {
  batik: "batik",
  parfum: "parfum",
  skincare: "skincare",
  "tropical-halal-skincare": "skincare",
  hijab: "hijab",
};

const productTypeForCategory = (category, fallback = "apparel") =>
  PRODUCT_TYPE_BY_DEPARTMENT[category?.department] || fallback;

const normalizeMedia = (items) =>
  (Array.isArray(items) ? items : [])
    .map((item, index) => {
      if (typeof item === "string") return { url: item, sort_order: index };
      return item && typeof item === "object" && (item.url || item.media_id)
        ? { ...item, sort_order: item.sort_order ?? index }
        : null;
    })
    .filter(Boolean)
    .slice(0, MAX_PRODUCT_IMAGES);

const uploadErrorMessage = (err) => {
  const detail = err?.response?.data?.detail;
  const code = typeof detail === "object" ? detail?.error : detail;
  if (code === "file_too_large" || err?.response?.status === 413) return "Image too large (maximum 15 MB).";
  if (["unsupported_media_type", "content_mismatch", "invalid_image"].includes(code)) {
    return "Only valid JPEG, PNG, or WebP images are supported.";
  }
  return "Image upload failed.";
};

const generatedSku = (name) => {
  const stem = String(name || "product")
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 38) || "PRODUCT";
  return `${stem}-${Date.now().toString(36).toUpperCase()}`.slice(0, 80);
};

const validationDetails = (detail) => {
  if (!Array.isArray(detail)) return "";
  return detail
    .map((item) => {
      const location = Array.isArray(item?.loc)
        ? item.loc.filter((part) => part !== "body").join(".")
        : "";
      const message = item?.msg || "Invalid value";
      return location ? `${location}: ${message}` : message;
    })
    .filter(Boolean)
    .join("; ");
};

const productSaveErrorMessage = (err) => {
  const detail = err?.response?.data?.detail;
  const pydanticMessage = validationDetails(detail);
  if (pydanticMessage) return `Please fix: ${pydanticMessage}.`;

  const code = typeof detail === "string" ? detail : detail?.error;
  const messages = {
    translation_en_required: "Enter the English product name before saving.",
    translation_name_required: `Enter a product name for ${detail?.locale || "the selected language"}.`,
    invalid_translation: "One of the product name or description fields is invalid.",
    invalid_locale: "One of the translation languages is not supported.",
    unsafe_text: "Product text cannot contain HTML or angle brackets.",
    invalid_category: "Select an active leaf category before saving.",
    category_not_leaf: "Select the most specific category; products cannot use a parent category.",
    invalid_product_type: "The selected category has an invalid product configuration.",
    invalid_status: "Select Draft, Active, or Inactive as the product status.",
    invalid_sku: "SKU must be at least 2 characters and cannot contain spaces or control characters.",
    sku_exists: "That SKU is already used by another variant. Use a different SKU.",
    sku_duplicate_in_payload: "Two variants in this product use the same SKU.",
    invalid_option_values: "Variant size must be a simple value such as S, M, or L.",
    invalid_variant: "One of the selected variants is no longer valid. Refresh and try again.",
    compare_price_below_base: "Compare-at price must be equal to or higher than the base price.",
    sale_price_not_below_regular: "Sale price must be lower than the regular price.",
    active_product_requires_variant: "An active product needs at least one active variant.",
    invalid_media: "One of the selected images is no longer available. Remove it and upload it again.",
    invalid_media_url: "One of the selected image links is invalid.",
    too_many_media: "A product can have up to 8 images.",
  };

  if (code === "below_active_reservations") {
    return `Stock cannot go below ${detail.active_reservations} active reservations.`;
  }
  if (code === "product_type_category_mismatch") {
    return "Batik and Parfum products must use a matching active category.";
  }
  if (code && messages[code]) return messages[code];
  if (code) return `Save failed (${code}). Please review the product fields.`;
  if (err?.response?.status === 401) return "Your admin session expired. Sign in again and retry.";
  if (err?.response?.status === 403) return "You do not have permission to save products.";
  return "Save failed. Please review the product fields and try again.";
};

export default function AdminProductEditPage() {
  const { productId } = useParams();
  const isNew = !productId;
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [form, setForm] = useState({
    category_id: "", product_type: "general", brand: "",
    base_price: "", compare_at_price: "", status: "draft", media: [],
  });
  const [attributes, setAttributes] = useState({});
  const [tr, setTr] = useState({ en: { name: "", short_description: "", description: "" } });
  const [activeLocale, setActiveLocale] = useState("en");
  const [variants, setVariants] = useState([{ ...EMPTY_VARIANT }]);
  const [saving, setSaving] = useState(false);
  const [imageUploading, setImageUploading] = useState(false);
  const [replacingImageIndex, setReplacingImageIndex] = useState(null);
  const [deletingVariantId, setDeletingVariantId] = useState(null);
  const [deletingProduct, setDeletingProduct] = useState(false);

  const categoriesQuery = useQuery({ queryKey: ["admin-categories"], queryFn: getAdminCategories });
  const productQuery = useQuery({
    queryKey: ["admin-product", productId],
    queryFn: () => getAdminProduct(productId),
    enabled: !isNew,
  });

  useEffect(() => {
    const p = productQuery.data;
    if (!p) return;
    setForm({
      category_id: p.category_id, product_type: p.product_type, brand: p.brand || "",
      base_price: String(p.base_price),
      compare_at_price: p.compare_at_price != null ? String(p.compare_at_price) : "",
      status: p.status, media: normalizeMedia(p.media),
    });
    setAttributes(p.attributes || {});
    setTr(p.translations || { en: { name: "" } });
    setVariants(
      (p.variants || []).map((v) => ({
        id: v.id, sku: v.sku, size: sizeFromOptions(v.option_values), preservedOptions: preservedOptionsFrom(v.option_values),
        stock: v.stock_quantity, active_reserved: v.active_reserved,
        price_override: v.price_override != null ? String(v.price_override) : "",
        sale_price_override: v.sale_price_override != null ? String(v.sale_price_override) : "",
        media_id: v.media_id || null,
        image_url: v.image_url || "",
        is_active: v.is_active,
      }))
    );
  }, [productQuery.data]);

  const setF = (key) => (e) => setForm((current) => ({ ...current, [key]: e.target.value }));
  const setAttribute = (key, value) => setAttributes((current) => ({ ...current, [key]: value }));
  const setT = (key) => (e) =>
    setTr((current) => ({ ...current, [activeLocale]: { ...(current[activeLocale] || {}), [key]: e.target.value } }));
  const setV = (idx, key, value) =>
    setVariants(variants.map((v, i) => (i === idx ? { ...v, [key]: value } : v)));

  const uploadProductImages = async (e) => {
    const files = Array.from(e.target.files || []);
    e.target.value = "";
    if (!files.length) return;

    const availableSlots = MAX_PRODUCT_IMAGES - form.media.length;
    if (availableSlots <= 0) {
      toast.error(`A product can have up to ${MAX_PRODUCT_IMAGES} images.`);
      return;
    }
    const filesToUpload = files.slice(0, availableSlots);
    setImageUploading(true);
    const uploaded = [];
    let firstError = null;
    try {
      for (const file of filesToUpload) {
        try {
          const asset = await uploadCmsMedia(file);
          uploaded.push({
            url: mediaUrl(asset.url),
            media_id: asset.id,
            original_filename: asset.original_filename,
          });
        } catch (err) {
          firstError = firstError || err;
        }
      }
      if (uploaded.length) {
        setForm((current) => ({ ...current, media: [...current.media, ...uploaded] }));
        queryClient.invalidateQueries({ queryKey: ["cms-media"] });
        toast.success(`${uploaded.length} product image${uploaded.length > 1 ? "s" : ""} uploaded`);
      }
      if (firstError) toast.error(uploadErrorMessage(firstError));
      if (files.length > filesToUpload.length) {
        toast.error(`Only ${availableSlots} image${availableSlots > 1 ? "s" : ""} could be added.`);
      }
    } finally {
      setImageUploading(false);
    }
  };

  const replaceProductImage = async (index, e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || imageUploading || replacingImageIndex !== null) return;

    setReplacingImageIndex(index);
    try {
      const asset = await uploadCmsMedia(file);
      setForm((current) => {
        const media = [...current.media];
        media[index] = {
          ...media[index],
          url: mediaUrl(asset.url),
          media_id: asset.id,
          original_filename: asset.original_filename,
          sort_order: index,
        };
        return { ...current, media };
      });
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
      toast.success(`Image ${index + 1} replaced. Click Save to apply.`);
    } catch (err) {
      toast.error(uploadErrorMessage(err));
    } finally {
      setReplacingImageIndex(null);
    }
  };

  const removeProductImage = (index) => {
    setForm((current) => ({
      ...current,
      media: current.media.filter((_, itemIndex) => itemIndex !== index),
    }));
  };

  const removeVariant = async (index, variant) => {
    if (!variant.id) {
      setVariants((current) => current.filter((_, itemIndex) => itemIndex !== index));
      return;
    }
    if (deletingVariantId || saving || deletingProduct) return;
    if (!window.confirm(`Delete variant "${variant.sku}" permanently?`)) return;

    setDeletingVariantId(variant.id);
    try {
      await deleteAdminVariant(variant.id);
      setVariants((current) => current.filter((item) => item.id !== variant.id));
      // Keep any unsaved local variant rows intact. The product query is
      // marked stale for the next navigation/refresh without replacing the
      // editor state while the operator is still working.
      queryClient.invalidateQueries({ queryKey: ["admin-product", productId], refetchType: "none" });
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      toast.success("Variant deleted");
    } catch (err) {
      toast.error(adminDeleteError(err, "Variant"));
    } finally {
      setDeletingVariantId(null);
    }
  };

  const removeProduct = async () => {
    if (isNew || deletingProduct || saving || deletingVariantId) return;
    const productName = tr.en?.name || productId;
    if (!window.confirm(`Delete product "${productName}" permanently?`)) return;

    setDeletingProduct(true);
    try {
      await deleteAdminProduct(productId);
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
      toast.success("Product deleted");
      navigate("/products", { replace: true });
    } catch (err) {
      toast.error(adminDeleteError(err, "Produk"));
    } finally {
      setDeletingProduct(false);
    }
  };

  const moveProductImage = (index, direction) => {
    setForm((current) => {
      const next = [...current.media];
      const target = index + direction;
      if (target < 0 || target >= next.length) return current;
      [next[index], next[target]] = [next[target], next[index]];
      return { ...current, media: next };
    });
  };

  const rawCats = categoriesQuery.data;
  const categoryNodes = Array.isArray(rawCats) ? rawCats : rawCats?.items || [];
  const catItems = categoryNodes.filter(
    (c) => c.kind === "category" && c.is_leaf !== false && (c.is_active || c.id === form.category_id)
  );
  const categoryById = new Map(categoryNodes.map((node) => [node.id, node]));
  const categoryBreadcrumb = (category) => {
    const chain = [];
    const seen = new Set();
    let current = category;
    while (current && !seen.has(current.id)) {
      seen.add(current.id);
      chain.unshift(current);
      current = categoryById.get(current.parent_id);
    }
    return chain
      .map((node) => pickLocalized(node.translations, "en", "name") || node.slug)
      .join(" / ");
  };

  const setCategory = (e) => {
    const categoryId = e.target.value;
    const category = categoryById.get(categoryId);
    setForm((current) => ({
      ...current,
      category_id: categoryId,
      product_type: productTypeForCategory(category, isNew ? "apparel" : current.product_type),
    }));
  };

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;

    const englishName = tr.en?.name?.trim() || "";
    if (!englishName) {
      setActiveLocale("en");
      toast.error("Enter the English product name before saving.");
      return;
    }
    const basePrice = Number(form.base_price);
    const compareAtPrice = form.compare_at_price === "" ? null : Number(form.compare_at_price);
    if (!Number.isInteger(basePrice) || basePrice < 0) {
      toast.error("Enter a valid base price.");
      return;
    }
    if (compareAtPrice !== null && (!Number.isInteger(compareAtPrice) || compareAtPrice < 0)) {
      toast.error("Enter a valid compare-at price.");
      return;
    }
    // A SKU is operational metadata, not something that should block an
    // otherwise complete product draft. Generate one for the first variant
    // when the operator leaves it blank; the backend still validates the
    // generated value and uniqueness.
    const enteredVariants = variants.filter(
      (v) => v.id || v.sku.trim() || v.size.trim() || Number(v.stock || 0) > 0
    );
    const candidateVariants = enteredVariants.length
      ? enteredVariants
      : [variants[0] || { ...EMPTY_VARIANT }];
    const preparedVariants = candidateVariants.map((variant, index) => ({
      ...variant,
      sku: variant.sku.trim() || (index === 0 ? generatedSku(englishName) : ""),
    })).filter((variant) => variant.id || variant.sku);
    if (!preparedVariants.length) {
      toast.error("Add at least one variant with a SKU.");
      return;
    }
    for (const variant of preparedVariants) {
      const numericValues = [
        variant.stock === "" ? 0 : Number(variant.stock),
        variant.price_override === "" ? null : Number(variant.price_override),
        variant.sale_price_override === "" ? null : Number(variant.sale_price_override),
      ];
      if (
        numericValues.some(
          (value) => value !== null && (!Number.isInteger(value) || value < 0)
        )
      ) {
        toast.error("Enter whole, non-negative values for stock and prices.");
        return;
      }
    }
    setSaving(true);
    try {
      const translations = Object.fromEntries(
        Object.entries(tr)
          .filter(([, v]) => v && v.name && v.name.trim())
          .map(([locale, value]) => [locale, {
            ...value,
            name: value.name.trim(),
          }])
      );
      const media = form.media.map((item, index) => ({ ...item, sort_order: index }));
      const primaryMediaId = media[0]?.media_id || null;
      const primaryImageUrl = media[0]?.url || null;
      const previousPrimaryMediaId = productQuery.data?.media?.[0]?.media_id || null;
      const previousPrimaryImageUrl = productQuery.data?.media?.[0]?.url || null;
      const base = {
        category_id: form.category_id,
        product_type: form.product_type,
        brand: form.brand,
        base_price: basePrice,
        compare_at_price: compareAtPrice,
        status: form.status,
        attributes,
        media,
        translations,
      };
      const editorVariants = preparedVariants
        .map((v) => {
          const stockQuantity = v.stock === "" ? 0 : Number(v.stock);
          const priceOverride = v.price_override === "" ? null : Number(v.price_override);
          const salePriceOverride = v.sale_price_override === "" ? null : Number(v.sale_price_override);
          const usesPreviousPrimary =
            (Boolean(v.media_id) && v.media_id === previousPrimaryMediaId) ||
            (!v.media_id && v.image_url === previousPrimaryImageUrl);
          const variantMediaId = usesPreviousPrimary ? primaryMediaId : (v.media_id || null);
          return {
            ...(v.id ? { id: v.id } : {}),
            sku: v.sku.trim(),
            option_values: optionsFromSize(v.size, v.preservedOptions),
            stock_quantity: stockQuantity,
            price_override: priceOverride,
            sale_price_override: salePriceOverride,
            media_id: variantMediaId,
            image_url: variantMediaId ? null : (usesPreviousPrimary ? primaryImageUrl : (v.image_url || null)),
            is_active: Boolean(v.is_active),
          };
        });
      if (isNew) {
        const created = await createAdminProduct({
          ...base,
          variants: editorVariants,
        });
        toast.success("Product created");
        queryClient.invalidateQueries({ queryKey: ["admin-products"] });
        navigate(`/products/${created.id}`, { replace: true });
        return;
      }
      await saveAdminProductEditor(productId, { ...base, variants: editorVariants });
      toast.success("Product saved");
      queryClient.invalidateQueries({ queryKey: ["admin-product", productId] });
      queryClient.invalidateQueries({ queryKey: ["admin-products"] });
      queryClient.invalidateQueries({ queryKey: ["products"] });
    } catch (err) {
      toast.error(productSaveErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  if (!isNew && productQuery.isLoading) {
    return <div data-testid="admin-editor-loading"><Skeleton className="h-8 w-64" /><Skeleton className="mt-6 h-96 w-full" /></div>;
  }

  const tab = tr[activeLocale] || {};

  return (
    <div data-testid="admin-product-editor">
      <Link to="/products" className="inline-flex items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-900" data-testid="editor-back">
        <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
        Back to products
      </Link>
      <h1 className="mt-2 text-xl font-semibold tracking-tight">
        {isNew ? "New product" : `Edit product`}
      </h1>

      <form onSubmit={save} className="mt-6 space-y-6">
        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-basics">
          <h2 className="text-sm font-semibold">Basics</h2>
          <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Category</label>
              <select value={form.category_id} onChange={setCategory} required className={inputClass} data-testid="editor-category">
                <option value="" disabled>—</option>
                {catItems.map((c) => (
                  <option key={c.id} value={c.id}>
                    {categoryBreadcrumb(c)}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-[11px] text-neutral-400">Product details follow the selected category automatically.</p>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Brand</label>
              <input value={form.brand} onChange={setF("brand")} className={inputClass} data-testid="editor-brand" maxLength={120} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Base price (UZS)</label>
              <input type="number" min="0" step="1" required value={form.base_price} onChange={setF("base_price")} className={inputClass} data-testid="editor-base-price" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Compare-at price (UZS)</label>
              <input type="number" min="0" step="1" value={form.compare_at_price} onChange={setF("compare_at_price")} className={inputClass} data-testid="editor-compare-at" />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Status</label>
              <select value={form.status} onChange={setF("status")} className={inputClass} data-testid="editor-status">
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="inactive">Inactive</option>
              </select>
            </div>
          </div>
        </section>

        {(ATTRIBUTE_FIELDS[form.product_type] || []).length ? (
          <section className="border border-neutral-200 bg-white p-5" data-testid="editor-attributes">
            <h2 className="text-sm font-semibold">{form.product_type === "parfum" ? "Fragrance details" : "Product details"}</h2>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              {(ATTRIBUTE_FIELDS[form.product_type] || []).map(([key, label]) => (
                <div key={key}>
                  <label className="mb-1 block text-xs font-medium text-neutral-500">{label}</label>
                  <textarea
                    value={attributes[key] || ""}
                    onChange={(e) => setAttribute(key, e.target.value)}
                    rows={key === "care" || key === "ingredients" || key === "benefits" || key === "directions" || key === "notes" || key === "usage" ? 3 : 2}
                    className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]"
                    data-testid={`editor-attribute-${key}`}
                  />
                </div>
              ))}
              {form.product_type === "parfum" ? (
                <label className="flex items-center gap-2 text-sm sm:col-span-2" data-testid="editor-alcohol-free">
                  <input type="checkbox" checked={Boolean(attributes.alcohol_free)} onChange={(e) => setAttribute("alcohol_free", e.target.checked)} className="accent-[#145A46]" />
                  Alcohol-free formula (only if confirmed in the master data)
                </label>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-media">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Product images</h2>
              <p className="mt-1 text-xs text-neutral-500">Upload directly from your device. The first image is the primary image.</p>
            </div>
            <span className="text-xs text-neutral-400" data-testid="editor-image-count">
              {form.media.length}/{MAX_PRODUCT_IMAGES}
            </span>
          </div>

          {form.media.length ? (
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-6" data-testid="editor-image-grid">
              {form.media.map((item, index) => (
                <div key={`${item.media_id || item.url}-${index}`} className="group relative overflow-hidden border border-neutral-200 bg-neutral-50" data-testid={`editor-image-${index}`}>
                  <ImageWithFallback
                    src={mediaUrl(item.url)}
                    alt={item.original_filename || `${tab.name || "Product"} image ${index + 1}`}
                    className="aspect-square w-full object-cover"
                    data-testid={`editor-image-preview-${index}`}
                  />
                  <div className="absolute left-2 top-2 bg-white/95 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-[#145A46]">
                    {index === 0 ? "Primary" : index + 1}
                  </div>
                  <div className="absolute inset-x-0 bottom-0 flex items-center justify-between gap-1 bg-black/70 px-1.5 py-1 opacity-100 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                    <label
                      htmlFor={`editor-image-replace-input-${index}`}
                      className={`inline-flex h-7 flex-1 cursor-pointer items-center justify-center gap-1 rounded-sm px-1 text-[10px] font-semibold text-white hover:bg-white/15 ${replacingImageIndex === index ? "pointer-events-none opacity-60" : ""}`}
                      title="Replace image"
                      data-testid={`editor-image-replace-${index}`}
                    >
                      <RefreshCw className={`h-3.5 w-3.5 ${replacingImageIndex === index ? "animate-spin" : ""}`} aria-hidden="true" />
                      {replacingImageIndex === index ? "Uploading…" : "Replace"}
                      <input
                        id={`editor-image-replace-input-${index}`}
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        className="hidden"
                        onChange={(e) => replaceProductImage(index, e)}
                        disabled={imageUploading || replacingImageIndex !== null}
                        data-testid={`editor-image-replace-input-${index}`}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => moveProductImage(index, -1)}
                      disabled={index === 0}
                      aria-label="Move image left"
                      className="inline-flex h-7 w-7 items-center justify-center text-white disabled:opacity-30"
                      data-testid={`editor-image-move-left-${index}`}
                    >
                      <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => removeProductImage(index)}
                      aria-label="Remove image"
                      className="inline-flex h-7 w-7 items-center justify-center text-white hover:text-red-300"
                      data-testid={`editor-image-remove-${index}`}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => moveProductImage(index, 1)}
                      disabled={index === form.media.length - 1}
                      aria-label="Move image right"
                      className="inline-flex h-7 w-7 items-center justify-center text-white disabled:opacity-30"
                      data-testid={`editor-image-move-right-${index}`}
                    >
                      <ChevronRight className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 flex h-32 items-center justify-center border border-dashed border-neutral-300 bg-neutral-50 text-xs text-neutral-400" data-testid="editor-image-empty">
              No images selected yet.
            </div>
          )}

          <div className="mt-4 flex flex-wrap items-end gap-3">
            <label
              className={`inline-flex h-10 cursor-pointer items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90 ${imageUploading ? "opacity-50" : ""}`}
              data-testid="editor-upload-image"
            >
              <ImagePlus className="h-4 w-4" aria-hidden="true" />
              {imageUploading ? "Uploading…" : "Upload image"}
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                multiple
                className="hidden"
                onChange={uploadProductImages}
                disabled={imageUploading || form.media.length >= MAX_PRODUCT_IMAGES}
                data-testid="editor-image-input"
              />
            </label>
          </div>
          <p className="mt-2 text-[11px] text-neutral-400">JPEG, PNG, or WebP up to 15 MB each. Images are stored on the VPS.</p>
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-translations">
          <h2 className="text-sm font-semibold">Translations</h2>
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
                Name ({activeLocale}{activeLocale === "en" ? " — required" : ""})
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
              <label className="mb-1 block text-xs font-medium text-neutral-500">Short description</label>
              <input value={tab.short_description || ""} onChange={setT("short_description")} className={inputClass} data-testid={`editor-short-${activeLocale}`} maxLength={500} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">Description</label>
              <textarea value={tab.description || ""} onChange={setT("description")} rows={4} className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]" data-testid={`editor-desc-${activeLocale}`} />
            </div>
          </div>
        </section>

        <section className="border border-neutral-200 bg-white p-5" data-testid="editor-variants">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold">Variants & inventory</h2>
            <button
              type="button"
              onClick={() => setVariants([...variants, { ...EMPTY_VARIANT }])}
              data-testid="editor-add-variant"
              className="inline-flex h-9 items-center gap-1.5 border border-neutral-300 px-3 text-xs font-semibold hover:border-[#145A46] hover:text-[#145A46]"
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" />
              Add variant
            </button>
          </div>
          <p className="mt-1 text-[11px] text-neutral-400">Enter the size for this variant, for example S, M, or L.</p>
          <div className="mt-3 space-y-3">
            {variants.map((v, idx) => (
              <div key={idx} className="grid items-end gap-3 border border-neutral-100 p-3 sm:grid-cols-2 xl:grid-cols-[1fr_1.4fr_0.6fr_0.7fr_0.7fr_auto_auto]" data-testid={`editor-variant-${idx}`}>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">SKU <span className="font-normal text-neutral-400">(optional)</span></label>
                  <input value={v.sku} onChange={(e) => setV(idx, "sku", e.target.value)} className={inputClass} data-testid={`variant-sku-${idx}`} maxLength={80} placeholder="Generated if blank" />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">Size</label>
                  <input value={v.size} onChange={(e) => setV(idx, "size", e.target.value)} className={inputClass} data-testid={`variant-size-${idx}`} placeholder="e.g. S, M, L" />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">
                    Stock{v.active_reserved ? ` (reserved ${v.active_reserved})` : ""}
                  </label>
                  <input type="number" min="0" step="1" value={v.stock} onChange={(e) => setV(idx, "stock", e.target.value)} className={inputClass} data-testid={`variant-stock-${idx}`} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">Price override</label>
                  <input type="number" min="0" step="1" value={v.price_override} onChange={(e) => setV(idx, "price_override", e.target.value)} className={inputClass} data-testid={`variant-price-${idx}`} />
                </div>
                <div>
                  <label className="mb-1 block text-[11px] font-medium text-neutral-500">Sale override</label>
                  <input type="number" min="0" step="1" value={v.sale_price_override} onChange={(e) => setV(idx, "sale_price_override", e.target.value)} className={inputClass} data-testid={`variant-sale-${idx}`} />
                </div>
                <label className="flex h-10 items-center gap-2 text-xs" data-testid={`variant-active-label-${idx}`}>
                  <input type="checkbox" checked={Boolean(v.is_active)} onChange={(e) => setV(idx, "is_active", e.target.checked)} className="accent-[#145A46]" data-testid={`variant-active-${idx}`} />
                  Active
                </label>
                <button
                  type="button"
                  onClick={() => removeVariant(idx, v)}
                  disabled={variants.length <= 1 || Boolean(deletingVariantId) || saving || deletingProduct}
                  title={variants.length <= 1 ? "A product must keep at least one variant." : "Delete variant"}
                  className="flex h-10 items-center text-neutral-400 hover:text-red-600 disabled:cursor-not-allowed disabled:opacity-30"
                  aria-label={`Delete variant ${v.sku || idx + 1}`}
                  data-testid={`variant-remove-${idx}`}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            ))}
          </div>
        </section>

        {!isNew ? (
          <section className="border border-red-200 bg-red-50/40 p-5" data-testid="editor-danger-zone">
            <h2 className="text-sm font-semibold text-red-900">Danger zone</h2>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-red-800/80">
              Permanent deletion is only allowed for an inactive or draft product with no order, cart, wishlist, or stock-reservation references.
            </p>
            {form.status === "active" ? (
              <p className="mt-2 text-xs font-medium text-amber-800">Set the product to Inactive and save it before deleting.</p>
            ) : null}
            <button
              type="button"
              onClick={removeProduct}
              disabled={deletingProduct || saving || Boolean(deletingVariantId)}
              className="mt-4 inline-flex h-10 items-center gap-2 border border-red-300 px-4 text-sm font-semibold text-red-800 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50"
              data-testid="editor-delete-product"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {deletingProduct ? "Deleting…" : "Delete permanently"}
            </button>
          </section>
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={saving}
            data-testid="editor-save"
            className="h-11 bg-[#145A46] px-8 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save product"}
          </button>
        </div>
      </form>
    </div>
  );
}
