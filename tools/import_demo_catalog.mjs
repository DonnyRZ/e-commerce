import fs from "node:fs";
import path from "node:path";

const root = path.resolve(".");
const apiBase = (process.env.MARKETPLACE_API_URL || "https://shanicantik.com/api/v1").replace(/\/$/, "");
const adminEmail = process.env.MARKETPLACE_ADMIN_EMAIL;
const adminPassword = process.env.MARKETPLACE_ADMIN_PASSWORD;
const resultPath = path.join(root, "artifacts", "imagegen", "demo-catalog-import-result.json");

if (!adminEmail || !adminPassword) {
  throw new Error("Set MARKETPLACE_ADMIN_EMAIL and MARKETPLACE_ADMIN_PASSWORD in the process environment.");
}

const assets = [
  {
    slug: "demo-gamis-batik-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-gamis-batik-emerald-puspa.jpg", "Gamis Batik Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-gamis-batik-emerald-puspa-detail.jpg", "Gamis Batik Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Gamis batik wanita Muslimah warna emerald dengan motif botani emas",
      en: "Emerald women's batik gamis with a warm-gold botanical motif",
      uz: "Zumrad rangli oltin botanika naqshli ayollar batikli gamisi",
      ru: "Женский изумрудный батиковый гамис с золотым растительным узором",
    },
  },
  {
    slug: "demo-tunik-batik-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-tunik-batik-emerald-puspa.jpg", "Tunik Batik Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-tunik-batik-emerald-puspa-detail.jpg", "Tunik Batik Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Tunik batik wanita Muslimah warna emerald dengan motif botani emas",
      en: "Emerald women's batik tunic with a warm-gold botanical motif",
      uz: "Zumrad rangli oltin botanika naqshli ayollar batikli tunikasi",
      ru: "Женская изумрудная батиковая туника с золотым растительным узором",
    },
  },
  {
    slug: "demo-outer-batik-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-outer-batik-emerald-puspa.jpg", "Outer Batik Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-outer-batik-emerald-puspa-detail.jpg", "Outer Batik Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Outer batik wanita Muslimah warna emerald dengan lapisan dalam ivory",
      en: "Emerald women's batik outer with an ivory inner layer",
      uz: "Ivory ichki qatlamli zumrad rangli ayollar batikli outeri",
      ru: "Женский изумрудный батиковый кардиган со светлым внутренним слоем",
    },
  },
  {
    slug: "demo-setelan-batik-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-setelan-batik-emerald-puspa.jpg", "Setelan Batik Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-setelan-batik-emerald-puspa-detail.jpg", "Setelan Batik Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Setelan batik wanita Muslimah warna emerald dengan atasan tunik dan celana lebar",
      en: "Emerald women's batik set with a tunic top and wide-leg trousers",
      uz: "Tunika va keng shimli zumrad rangli ayollar batikli komplekti",
      ru: "Женский изумрудный батиковый комплект с туникой и широкими брюками",
    },
  },
  {
    slug: "demo-rok-batik-panjang-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-rok-batik-panjang-emerald-puspa.jpg", "Rok Batik Panjang Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-rok-batik-panjang-emerald-puspa-detail.jpg", "Rok Batik Panjang Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Rok batik panjang wanita Muslimah warna emerald dengan motif botani emas",
      en: "Emerald women's long batik skirt with a warm-gold botanical motif",
      uz: "Zumrad rangli oltin botanika naqshli ayollar uzun batik yubkasi",
      ru: "Женская длинная изумрудная батиковая юбка с золотым растительным узором",
    },
  },
  {
    slug: "demo-hijab-pashmina-batik-emerald-puspa",
    files: [
      ["frontend/public/assets/catalog/demo/batik/demo-hijab-pashmina-batik-emerald-puspa.jpg", "Hijab Pashmina Batik Emerald Puspa preview"],
      ["frontend/public/assets/catalog/demo/batik/demo-hijab-pashmina-batik-emerald-puspa-detail.jpg", "Hijab Pashmina Batik Emerald Puspa detail preview"],
    ],
    alt: {
      id: "Hijab pashmina batik warna emerald dengan motif botani emas",
      en: "Emerald batik pashmina hijab with a warm-gold botanical motif",
      uz: "Oltin botanika naqshli zumrad rangli batik pashmina hijob",
      ru: "Изумрудная батиковая пашмина с золотым растительным узором",
    },
  },
  {
    slug: "demo-musk-thaharah",
    files: [
      ["frontend/public/assets/catalog/demo/parfum/demo-musk-thaharah.jpg", "Musk Thaharah preview"],
      ["frontend/public/assets/catalog/demo/parfum/demo-musk-thaharah-detail.jpg", "Musk Thaharah detail preview"],
    ],
    alt: {
      id: "Botol parfum musk thaharah tanpa label di atas plinth emas",
      en: "Unbranded musk thaharah perfume bottle on a warm-gold plinth",
      uz: "Oltin plintusdagi yorliqsiz musk thaharah atir shishasi",
      ru: "Нелабелированный флакон мускусного парфюма Тахара на золотом постаменте",
    },
  },
  {
    slug: "demo-soft-floral-powdery",
    files: [
      ["frontend/public/assets/catalog/demo/parfum/demo-soft-floral-powdery.jpg", "Soft Floral Powdery preview"],
      ["frontend/public/assets/catalog/demo/parfum/demo-soft-floral-powdery-detail.jpg", "Soft Floral Powdery detail preview"],
    ],
    alt: {
      id: "Botol parfum soft floral powdery tanpa label dengan bunga mawar",
      en: "Unbranded soft floral powdery perfume bottle with blush roses",
      uz: "Pushti atirgullar yonidagi yorliqsiz yumshoq floral pudrali atir",
      ru: "Нелабелированный мягкий цветочный пудровый парфюм с розами",
    },
  },
  {
    slug: "demo-gourmand-rich-oriental",
    files: [
      ["frontend/public/assets/catalog/demo/parfum/demo-gourmand-rich-oriental.jpg", "Gourmand Rich Oriental preview"],
      ["frontend/public/assets/catalog/demo/parfum/demo-gourmand-rich-oriental-detail.jpg", "Gourmand Rich Oriental detail preview"],
    ],
    alt: {
      id: "Botol parfum gourmand oriental tanpa label dengan vanila dan cokelat",
      en: "Unbranded rich oriental gourmand perfume bottle with vanilla and chocolate",
      uz: "Vanil va shokoladli yorliqsiz boy sharqona gourmand atir",
      ru: "Нелабелированный насыщенный восточный гурманский парфюм с ванилью и шоколадом",
    },
  },
  {
    slug: "demo-alcohol-free-spray",
    files: [
      ["frontend/public/assets/catalog/demo/parfum/demo-alcohol-free-spray.jpg", "Alcohol-Free Spray preview"],
      ["frontend/public/assets/catalog/demo/parfum/demo-alcohol-free-spray-detail.jpg", "Alcohol-Free Spray detail preview"],
    ],
    alt: {
      id: "Botol parfum semprot bebas alkohol tanpa label dengan bunga putih",
      en: "Unbranded alcohol-free spray perfume bottle with white blossoms",
      uz: "Oq gullar yonidagi yorliqsiz spirtsiz purkaladigan atir",
      ru: "Нелабелированный спрей-парфюм без спирта с белыми цветами",
    },
  },
];

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

async function listProducts() {
  const payload = await request("/admin/products?page=1&page_size=100");
  return payload.items || payload;
}

async function main() {
  await request("/auth/login", { method: "POST", json: { email: adminEmail, password: adminPassword } });
  if (!csrfToken()) throw new Error("Login succeeded but csrf_token cookie was not returned.");

  const products = await listProducts();
  const bySlug = new Map(products.map((product) => [product.slug, product]));
  const result = { version: 1, imported_at: new Date().toISOString(), products: {} };

  for (const spec of assets) {
    const product = bySlug.get(spec.slug);
    if (!product) throw new Error(`Demo product not found: ${spec.slug}`);
    const media = [];
    for (let index = 0; index < spec.files.length; index += 1) {
      const [relativePath, filename] = spec.files[index];
      const filePath = path.join(root, relativePath);
      if (!fs.existsSync(filePath)) throw new Error(`Missing asset: ${filePath}`);
      const uploaded = await upload(filePath);
      await request(`/admin/cms/media/${uploaded.id}`, {
        method: "PATCH",
        json: {
          translations: Object.fromEntries(
            Object.entries(spec.alt).map(([locale, altText]) => [locale, {
              alt_text: altText,
              caption: filename,
            }]),
          ),
        },
      });
      media.push({ media_id: uploaded.id, url: uploaded.url, sort_order: index });
    }
    await request(`/admin/products/${product.id}`, { method: "PATCH", json: { media } });
    result.products[spec.slug] = { id: product.id, media: media.map(({ media_id, url }) => ({ media_id, url })) };
    console.log(`mapped ${spec.slug} (${media.length} images)`);
  }

  fs.mkdirSync(path.dirname(resultPath), { recursive: true });
  fs.writeFileSync(resultPath, `${JSON.stringify(result, null, 2)}\n`, "utf8");

  for (const spec of assets) {
    const product = bySlug.get(spec.slug);
    const detail = await request(`/admin/products/${product.id}`);
    if (detail.is_demo !== true) throw new Error(`Demo flag missing: ${spec.slug}`);
    if ((detail.media || []).length !== 2 || detail.media.some((item) => !item.media_id)) {
      throw new Error(`Gallery mapping failed: ${spec.slug}`);
    }
  }
  console.log(JSON.stringify({ api_base: apiBase, products: assets.length, media: assets.length * 2 }, null, 2));
}

main().catch((error) => {
  console.error(error.stack || error.message || error);
  process.exitCode = 1;
});
