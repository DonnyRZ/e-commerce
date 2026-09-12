import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";

const root = path.resolve(".");
const manifestPath = path.join(root, "artifacts", "imagegen", "manifest.json");
const optimizedDir = path.join(root, "artifacts", "imagegen", "optimized");
const resultPath = path.join(root, "artifacts", "imagegen", "import-result.json");
const reportPath = path.join(root, "artifacts", "imagegen", "import-report.json");
const apiBase = (process.env.MARKETPLACE_API_URL || "https://shanicantik.com/api/v1").replace(/\/$/, "");
const adminEmail = process.env.MARKETPLACE_ADMIN_EMAIL;
const adminPassword = process.env.MARKETPLACE_ADMIN_PASSWORD;

if (!adminEmail || !adminPassword) {
  throw new Error("Set MARKETPLACE_ADMIN_EMAIL and MARKETPLACE_ADMIN_PASSWORD in the process environment.");
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
if (manifest.count !== 104 || manifest.entries.length !== 104) {
  throw new Error(`Manifest must contain 104 entries; found ${manifest.entries.length}.`);
}

const cookies = new Map();
const cookieHeader = () => [...cookies.entries()].map(([key, value]) => `${key}=${value}`).join("; ");
const csrfToken = () => cookies.get("csrf_token") || "";

function captureCookies(response) {
  const values = typeof response.headers.getSetCookie === "function"
    ? response.headers.getSetCookie()
    : (response.headers.get("set-cookie") ? [response.headers.get("set-cookie")] : []);
  for (const value of values) {
    const pair = value.split(";", 1)[0];
    const separator = pair.indexOf("=");
    if (separator > 0) cookies.set(pair.slice(0, separator), pair.slice(separator + 1));
  }
}

async function request(endpoint, options = {}) {
  const method = options.method || "GET";
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  const requestOptions = { ...options, method, headers };
  if (cookies.size) headers.Cookie = cookieHeader();
  if (method !== "GET" && method !== "HEAD" && csrfToken()) headers["X-CSRF-Token"] = csrfToken();
  if (options.json !== undefined) {
    headers["Content-Type"] = "application/json";
    requestOptions.body = JSON.stringify(options.json);
    delete requestOptions.json;
  }
  const response = await fetch(`${apiBase}${endpoint}`, requestOptions);
  captureCookies(response);
  const raw = await response.text();
  let body = raw;
  try { body = raw ? JSON.parse(raw) : null; } catch { /* keep text */ }
  if (!response.ok) {
    throw new Error(`${method} ${endpoint} -> ${response.status}: ${typeof body === "string" ? body : JSON.stringify(body)}`);
  }
  return body;
}

async function upload(filePath) {
  const data = fs.readFileSync(filePath);
  const form = new FormData();
  form.append("file", new Blob([data], { type: "image/jpeg" }), path.basename(filePath));
  return request("/admin/cms/media", { method: "POST", body: form });
}

async function patch(endpoint, json) {
  return request(endpoint, { method: "PATCH", json });
}

function loadResult() {
  if (!fs.existsSync(resultPath)) return { version: 1, entries: {} };
  return JSON.parse(fs.readFileSync(resultPath, "utf8"));
}

function saveResult(result) {
  fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");
}

async function listAll(endpoint, pageSize = 100) {
  const all = [];
  let page = 1;
  let total = Infinity;
  while (all.length < total) {
    const data = await request(`${endpoint}?page=${page}&page_size=${pageSize}`);
    const items = data.items || [];
    all.push(...items);
    total = Number(data.total ?? all.length);
    if (!items.length) break;
    page += 1;
  }
  return all;
}

function withoutImageUrl(payload) {
  const value = { ...(payload || {}) };
  delete value.image_url;
  return value;
}

function assertNoRemoteImage(value, label) {
  const serialized = JSON.stringify(value || {});
  const origin = new URL(apiBase).origin;
  const urls = serialized.match(/https?:\/\/[^"'\\s]+/gi) || [];
  if (urls.some((url) => !url.startsWith(origin) && !url.includes("/api/v1/cms/media/file/"))) {
    throw new Error(`Remote image URL remains in ${label}`);
  }
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  await request("/auth/login", { method: "POST", json: { email: adminEmail, password: adminPassword } });
  if (!csrfToken()) throw new Error("Login succeeded but csrf_token cookie was not returned.");

  const result = loadResult();
  const products = await listAll("/admin/products");
  const targetProductSlugs = new Set(manifest.entries.filter((entry) => entry.entity_type === "product").map((entry) => entry.entity_slug));
  const targetProducts = products.filter((product) => targetProductSlugs.has(product.slug));
  if (targetProducts.length !== targetProductSlugs.size) {
    throw new Error(`Missing target products: expected ${targetProductSlugs.size}, found ${targetProducts.length}`);
  }
  const productDetails = new Map();
  for (const product of products) productDetails.set(product.slug, await request(`/admin/products/${product.id}`));
  const categories = await request("/admin/categories");
  const categoryBySlug = new Map((categories.items || categories).map((item) => [item.slug, item]));
  const content = await listAll("/admin/cms/content");
  const contentBySlug = new Map(content.map((item) => [item.slug, item]));

  const assets = new Map();
  for (let index = 0; index < manifest.entries.length; index += 1) {
    const entry = manifest.entries[index];
    const filePath = path.join(optimizedDir, entry.filename);
    if (!fs.existsSync(filePath)) throw new Error(`Missing optimized asset: ${filePath}`);
    let record = result.entries[entry.asset_key];
    if (!record?.media_id) {
      const asset = await upload(filePath);
      record = {
        media_id: asset.id,
        url: asset.url,
        checksum: asset.checksum || crypto.createHash("sha256").update(fs.readFileSync(filePath)).digest("hex"),
        filename: entry.filename,
      };
      result.entries[entry.asset_key] = record;
      saveResult(result);
    }
    assets.set(entry.asset_key, { ...entry, ...record });
    const translations = Object.fromEntries(
      Object.entries(entry.locale_alt).map(([locale, altText]) => [locale, { alt_text: altText, caption: "" }])
    );
    await patch(`/admin/cms/media/${record.media_id}`, { translations });
    if ((index + 1) % 10 === 0 || index === manifest.entries.length - 1) {
      console.log(`uploaded and described ${index + 1}/${manifest.entries.length}`);
    }
  }

  for (const product of targetProducts) {
    const entries = manifest.entries
      .filter((entry) => entry.entity_type === "product" && entry.entity_slug === product.slug)
      .sort((a, b) => a.sort_order - b.sort_order)
      .map((entry) => assets.get(entry.asset_key));
    if (entries.length !== 4) throw new Error(`Expected 4 gallery assets for ${product.slug}`);
    await patch(`/admin/products/${product.id}`, {
      media: entries.map((entry, index) => ({ media_id: entry.media_id, url: entry.url, sort_order: index })),
    });
  }

  const variantEntries = manifest.entries.filter((entry) => entry.entity_type === "variant");
  for (const entry of variantEntries) {
    const asset = assets.get(entry.asset_key);
    const matches = [];
    for (const product of productDetails.values()) {
      for (const variant of product.variants || []) {
        if (variant.sku === entry.entity_sku_prefix || variant.sku.startsWith(`${entry.entity_sku_prefix}-`)) {
          matches.push(variant);
        }
      }
    }
    if (!matches.length) throw new Error(`No variant SKU matched ${entry.entity_sku_prefix}`);
    for (const variant of matches) await patch(`/admin/variants/${variant.id}`, { media_id: asset.media_id });
  }

  for (const entry of manifest.entries.filter((item) => ["category", "department"].includes(item.entity_type))) {
    const category = categoryBySlug.get(entry.entity_slug);
    if (!category) throw new Error(`Category/department not found: ${entry.entity_slug}`);
    const asset = assets.get(entry.asset_key);
    await patch(`/admin/categories/${category.id}`, { media_id: asset.media_id });
  }

  for (const entry of manifest.entries.filter((item) => item.entity_type === "cms")) {
    const cmsEntry = contentBySlug.get(entry.entity_slug);
    if (!cmsEntry) throw new Error(`CMS entry not found: ${entry.entity_slug}`);
    const asset = assets.get(entry.asset_key);
    await patch(`/admin/cms/content/${cmsEntry.id}`, {
      media_id: asset.media_id,
      payload: withoutImageUrl(cmsEntry.payload),
    });
  }

  const verifiedProducts = [];
  for (const product of targetProducts) {
    const detail = await request(`/admin/products/${product.id}`);
    if ((detail.media || []).length !== 4 || detail.media.some((item) => !item.media_id)) {
      throw new Error(`Product gallery verification failed: ${product.slug}`);
    }
    if ((detail.variants || []).some((variant) => variant.image_url && /https?:\/\//.test(variant.image_url) && !variant.image_url.includes("/api/"))) {
      throw new Error(`Remote variant image remains: ${product.slug}`);
    }
    verifiedProducts.push(product.slug);
    assertNoRemoteImage(detail.media, `product ${product.slug}`);
  }
  const verifiedCategories = await request("/admin/categories");
  const targetTaxonomySlugs = new Set(manifest.entries.filter((entry) => ["category", "department"].includes(entry.entity_type)).map((entry) => entry.entity_slug));
  const taxonomyWithoutMedia = (verifiedCategories.items || verifiedCategories).filter((item) => targetTaxonomySlugs.has(item.slug) && !item.media_id);
  if (taxonomyWithoutMedia.length) throw new Error(`Taxonomy assets missing: ${taxonomyWithoutMedia.map((item) => item.slug).join(", ")}`);
  const verifiedContent = await listAll("/admin/cms/content");
  const cmsWithoutMedia = verifiedContent.filter((item) => ["home-hero", "modest-styling-guide", "hijab-styling-guide", "tropical-halal-skincare-routine", "new-season-muslimah-edit"].includes(item.slug) && !item.media_id);
  if (cmsWithoutMedia.length) throw new Error(`CMS assets missing: ${cmsWithoutMedia.map((item) => item.slug).join(", ")}`);
  const publicBundle = await request("/cms/public/bundle");
  if (!publicBundle.hero?.image_url) throw new Error("Public CMS hero has no image URL");

  const media = await listAll("/admin/cms/media");
  const unused = media.filter((item) => item.usage_count === 0).map((item) => item.original_filename);
  if (media.length < 104) throw new Error(`Media library verification found only ${media.length} assets`);
  if (unused.length) throw new Error(`Imported assets are unused: ${unused.join(", ")}`);
  const report = {
    generated_at: new Date().toISOString(),
    manifest_count: manifest.entries.length,
    media_count: media.length,
    verified_products: verifiedProducts.length,
    verified_taxonomy: targetTaxonomySlugs.size,
    verified_cms_assets: 5,
    unused_assets: unused,
    api_base: apiBase,
  };
  fs.writeFileSync(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log(JSON.stringify(report, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exitCode = 1;
});
