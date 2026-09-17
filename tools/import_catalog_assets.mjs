import fs from "node:fs";
import path from "node:path";

const root = path.resolve(".");
const manifestPath = path.join(root, "artifacts", "imagegen", "catalog-media-manifest.json");
const optimizedDir = path.join(root, "artifacts", "imagegen", "catalog-optimized");
const resultPath = path.join(root, "artifacts", "imagegen", "catalog-import-result.json");
const apiBase = (process.env.MARKETPLACE_API_URL || "https://shanicantik.com/api/v1").replace(/\/$/, "");
const adminEmail = process.env.MARKETPLACE_ADMIN_EMAIL;
const adminPassword = process.env.MARKETPLACE_ADMIN_PASSWORD;

if (!adminEmail || !adminPassword) {
  throw new Error("Set MARKETPLACE_ADMIN_EMAIL and MARKETPLACE_ADMIN_PASSWORD in the process environment.");
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const entries = manifest.assets || [];
if (!entries.length) throw new Error("Catalog asset manifest is empty.");

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

function saveManifest(assetRecords) {
  const next = {
    ...manifest,
    status: "imported_and_mapped",
    assets: entries.map((entry) => ({ ...entry, ...(assetRecords[entry.asset_key] || {}) })),
  };
  fs.writeFileSync(manifestPath, `${JSON.stringify(next, null, 2)}\n`, "utf8");
}

async function main() {
  await request("/auth/login", { method: "POST", json: { email: adminEmail, password: adminPassword } });
  if (!csrfToken()) throw new Error("Login succeeded but csrf_token cookie was not returned.");

  const categoriesPayload = await request("/admin/categories");
  const categories = categoriesPayload.items || categoriesPayload;
  const categoryBySlug = new Map(categories.map((item) => [item.slug, item]));
  const result = loadResult();
  const records = {};

  for (const entry of entries) {
    const sourcePath = path.resolve(root, entry.file);
    const optimizedPath = path.join(optimizedDir, `${path.basename(sourcePath, path.extname(sourcePath))}.jpg`);
    if (!fs.existsSync(optimizedPath)) throw new Error(`Missing optimized asset: ${optimizedPath}`);

    let record = result.entries[entry.asset_key];
    if (!record?.media_id) {
      const asset = await upload(optimizedPath);
      record = {
        media_id: asset.id,
        url: asset.url,
        checksum: asset.checksum,
        filename: path.basename(optimizedPath),
      };
      result.entries[entry.asset_key] = record;
      saveResult(result);
    }

    const translations = Object.fromEntries(
      Object.entries(entry.alt || {}).map(([locale, altText]) => [locale, { alt_text: altText, caption: "" }])
    );
    await patch(`/admin/cms/media/${record.media_id}`, { translations });

    const category = categoryBySlug.get(entry.entity_slug);
    if (!category) throw new Error(`Category/department not found: ${entry.entity_slug}`);
    await patch(`/admin/categories/${category.id}`, { media_id: record.media_id });

    records[entry.asset_key] = { media_id: record.media_id, url: record.url };
    saveManifest(records);
    console.log(`mapped ${entry.entity_type}:${entry.entity_slug}`);
  }

  const verifiedPayload = await request("/admin/categories");
  const verified = verifiedPayload.items || verifiedPayload;
  const missing = entries
    .map((entry) => entry.entity_slug)
    .filter((slug) => !verified.find((item) => item.slug === slug && item.media_id));
  if (missing.length) throw new Error(`Catalog media mapping failed: ${missing.join(", ")}`);

  console.log(JSON.stringify({ imported: entries.length, mapped: entries.length, api_base: apiBase }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exitCode = 1;
});
