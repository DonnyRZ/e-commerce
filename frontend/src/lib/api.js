import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
});

const getCookie = (name) => {
  const row = document.cookie.split("; ").find((r) => r.startsWith(`${name}=`));
  return row ? decodeURIComponent(row.split("=").slice(1).join("=")) : null;
};

api.interceptors.request.use((config) => {
  if (["post", "put", "patch", "delete"].includes(config.method)) {
    const csrf = getCookie("csrf_token");
    if (csrf) config.headers["X-CSRF-Token"] = csrf;
  }
  return config;
});

const clean = (params = {}) =>
  Object.fromEntries(
    Object.entries(params).filter(
      ([, v]) => v !== undefined && v !== null && v !== ""
    )
  );

export const getHealth = () => api.get("/v1/health").then((r) => r.data);

export const getDepartments = () =>
  api.get("/v1/catalog/departments").then((r) => r.data);

export const getCategories = (params = {}) =>
  api.get("/v1/catalog/categories", { params: clean(params) }).then((r) => r.data);

export const getCategory = (slug) =>
  api.get(`/v1/catalog/categories/${slug}`).then((r) => r.data);

export const getProducts = (params = {}) =>
  api.get("/v1/catalog/products", { params: clean(params) }).then((r) => r.data);

export const getProduct = (slug) =>
  api.get(`/v1/catalog/products/${slug}`).then((r) => r.data);

export const getFilters = (params = {}) =>
  api.get("/v1/catalog/filters", { params: clean(params) }).then((r) => r.data);

export const authLogin = (email, password) =>
  api.post("/v1/auth/login", { email, password }).then((r) => r.data);

export const authRegister = (data) =>
  api.post("/v1/auth/register", data).then((r) => r.data);

export const authLogout = () => api.post("/v1/auth/logout").then((r) => r.data);

export const authMe = () => api.get("/v1/auth/me").then((r) => r.data);

export const updateProfile = (data) =>
  api.patch("/v1/auth/me", data).then((r) => r.data);

export const forgotPassword = (email) =>
  api.post("/v1/auth/forgot-password", { email }).then((r) => r.data);

export const resetPassword = (token, password) =>
  api.post("/v1/auth/reset-password", { token, password }).then((r) => r.data);

export const getAddresses = () =>
  api.get("/v1/account/addresses").then((r) => r.data);

export const createAddress = (data) =>
  api.post("/v1/account/addresses", data).then((r) => r.data);

export const updateAddress = (id, data) =>
  api.patch(`/v1/account/addresses/${id}`, data).then((r) => r.data);

export const deleteAddress = (id) =>
  api.delete(`/v1/account/addresses/${id}`).then((r) => r.data);

export const getCart = () => api.get("/v1/cart").then((r) => r.data);

export const addCartItem = (data) =>
  api.post("/v1/cart/items", data).then((r) => r.data);

export const updateCartItem = (id, quantity) =>
  api.patch(`/v1/cart/items/${id}`, { quantity }).then((r) => r.data);

export const removeCartItem = (id) =>
  api.delete(`/v1/cart/items/${id}`).then((r) => r.data);

export const clearCart = () => api.delete("/v1/cart").then((r) => r.data);

export const mergeCart = () => api.post("/v1/cart/merge").then((r) => r.data);

export const getWishlist = () => api.get("/v1/wishlist").then((r) => r.data);

export const addWishlistItem = (productId) =>
  api.post("/v1/wishlist/items", { product_id: productId }).then((r) => r.data);

export const removeWishlistItem = (productId) =>
  api.delete(`/v1/wishlist/items/${productId}`).then((r) => r.data);

export const getCheckoutOptions = () =>
  api.get("/v1/checkout/options").then((r) => r.data);

export const getCheckoutQuote = (shippingMethod) =>
  api.post("/v1/checkout/quote", { shipping_method: shippingMethod }).then((r) => r.data);

export const placeOrder = (data) =>
  api.post("/v1/checkout/orders", data).then((r) => r.data);

export const mockPay = (data) =>
  api.post("/v1/payments/mock/pay", data).then((r) => r.data);

export const trackOrder = (orderNumber, token) =>
  api.get("/v1/orders/track", { params: { order_number: orderNumber, token } }).then((r) => r.data);

export const getMyOrders = () =>
  api.get("/v1/account/orders").then((r) => r.data);

export const getMyOrder = (orderNumber) =>
  api.get(`/v1/account/orders/${orderNumber}`).then((r) => r.data);

// ---------------- Seller ----------------
export const getSellerDashboard = () =>
  api.get("/v1/seller/dashboard").then((r) => r.data);

export const getSellerProducts = (params) =>
  api.get("/v1/seller/products", { params }).then((r) => r.data);

export const createSellerProduct = (data) =>
  api.post("/v1/seller/products", data).then((r) => r.data);

export const getSellerProduct = (id) =>
  api.get(`/v1/seller/products/${id}`).then((r) => r.data);

export const updateSellerProduct = (id, data) =>
  api.patch(`/v1/seller/products/${id}`, data).then((r) => r.data);

export const createSellerVariant = (productId, data) =>
  api.post(`/v1/seller/products/${productId}/variants`, data).then((r) => r.data);

export const updateSellerVariant = (id, data) =>
  api.patch(`/v1/seller/variants/${id}`, data).then((r) => r.data);

export const updateSellerInventory = (id, stockQuantity) =>
  api
    .patch(`/v1/seller/variants/${id}/inventory`, { stock_quantity: stockQuantity })
    .then((r) => r.data);

export const getSellerOrders = (params) =>
  api.get("/v1/seller/orders", { params }).then((r) => r.data);

export const getSellerOrder = (orderNumber) =>
  api.get(`/v1/seller/orders/${orderNumber}`).then((r) => r.data);

export const updateSellerFulfillment = (orderNumber, data) =>
  api.patch(`/v1/seller/orders/${orderNumber}/fulfillment`, data).then((r) => r.data);

export const getSellerProfile = () =>
  api.get("/v1/seller/profile").then((r) => r.data);

export const updateSellerProfile = (data) =>
  api.patch("/v1/seller/profile", data).then((r) => r.data);

export const getCatalogCategories = () =>
  api.get("/v1/catalog/categories").then((r) => r.data);

// ---------------- Admin ----------------
export const getAdminDashboard = () =>
  api.get("/v1/admin/dashboard").then((r) => r.data);
export const getAdminProducts = (params) =>
  api.get("/v1/admin/products", { params }).then((r) => r.data);
export const createAdminProduct = (data) =>
  api.post("/v1/admin/products", data).then((r) => r.data);
export const getAdminProduct = (id) =>
  api.get(`/v1/admin/products/${id}`).then((r) => r.data);
export const updateAdminProduct = (id, data) =>
  api.patch(`/v1/admin/products/${id}`, data).then((r) => r.data);
export const createAdminVariant = (productId, data) =>
  api.post(`/v1/admin/products/${productId}/variants`, data).then((r) => r.data);
export const updateAdminVariant = (id, data) =>
  api.patch(`/v1/admin/variants/${id}`, data).then((r) => r.data);
export const updateAdminInventory = (id, stockQuantity) =>
  api.patch(`/v1/admin/variants/${id}/inventory`, { stock_quantity: stockQuantity }).then((r) => r.data);
export const getAdminCategories = () =>
  api.get("/v1/admin/categories").then((r) => r.data);
export const createAdminCategory = (data) =>
  api.post("/v1/admin/categories", data).then((r) => r.data);
export const updateAdminCategory = (id, data) =>
  api.patch(`/v1/admin/categories/${id}`, data).then((r) => r.data);
export const deleteAdminCategory = (id) =>
  api.delete(`/v1/admin/categories/${id}`).then((r) => r.data);
export const getAdminOrders = (params) =>
  api.get("/v1/admin/orders", { params }).then((r) => r.data);
export const getAdminOrder = (orderNumber) =>
  api.get(`/v1/admin/orders/${orderNumber}`).then((r) => r.data);
export const updateAdminOrderStatus = (orderNumber, status) =>
  api.patch(`/v1/admin/orders/${orderNumber}/status`, { status }).then((r) => r.data);
export const getAdminCustomers = (params) =>
  api.get("/v1/admin/customers", { params }).then((r) => r.data);
export const getAdminCustomer = (id) =>
  api.get(`/v1/admin/customers/${id}`).then((r) => r.data);
export const getAdminPaymentsReview = () =>
  api.get("/v1/admin/payments/review").then((r) => r.data);
export const addAdminReviewNote = (paymentId, note) =>
  api.post(`/v1/admin/payments/${paymentId}/review-note`, { note }).then((r) => r.data);
export const adminMockRefund = (paymentId) =>
  api.post(`/v1/admin/payments/${paymentId}/mock-refund`).then((r) => r.data);
export const getAdminAudit = (params) =>
  api.get("/v1/admin/audit", { params }).then((r) => r.data);
export const getAdminSettings = () =>
  api.get("/v1/admin/settings").then((r) => r.data);

// ---------------- CMS admin ----------------
export const getCmsContent = (params) =>
  api.get("/v1/admin/cms/content", { params }).then((r) => r.data);
export const createCmsContent = (data) =>
  api.post("/v1/admin/cms/content", data).then((r) => r.data);
export const getCmsContentEntry = (id) =>
  api.get(`/v1/admin/cms/content/${id}`).then((r) => r.data);
export const updateCmsContent = (id, data) =>
  api.patch(`/v1/admin/cms/content/${id}`, data).then((r) => r.data);
export const setCmsContentStatus = (id, action) =>
  api.post(`/v1/admin/cms/content/${id}/status`, { action }).then((r) => r.data);
export const getCmsPreviewToken = (id) =>
  api.post(`/v1/admin/cms/content/${id}/preview-token`).then((r) => r.data);
export const getCmsRevisions = (id) =>
  api.get(`/v1/admin/cms/content/${id}/revisions`).then((r) => r.data);
export const restoreCmsRevision = (id, revisionId) =>
  api.post(`/v1/admin/cms/content/${id}/restore/${revisionId}`).then((r) => r.data);
export const getCmsMedia = (params) =>
  api.get("/v1/admin/cms/media", { params }).then((r) => r.data);
export const uploadCmsMedia = (file) => {
  const fd = new FormData();
  fd.append("file", file);
  return api
    .post("/v1/admin/cms/media", fd, { headers: { "Content-Type": undefined } })
    .then((r) => r.data);
};
export const updateCmsMedia = (id, data) =>
  api.patch(`/v1/admin/cms/media/${id}`, data).then((r) => r.data);
export const deleteCmsMedia = (id) =>
  api.delete(`/v1/admin/cms/media/${id}`).then((r) => r.data);

// ---------------- CMS public ----------------
export const getCmsBundle = () =>
  api.get("/v1/cms/public/bundle").then((r) => r.data);
export const getCmsFooter = () =>
  api.get("/v1/cms/public/footer").then((r) => r.data);
export const getCmsNavigation = () =>
  api.get("/v1/cms/public/navigation").then((r) => r.data);
export const getCmsPage = (slug) =>
  api.get(`/v1/cms/public/pages/${slug}`).then((r) => r.data);
export const getCmsFaq = () =>
  api.get("/v1/cms/public/faq").then((r) => r.data);

export const authErrorKey = (error) => {
  const detail = error?.response?.data?.detail;
  const code = typeof detail === "string" ? detail : Array.isArray(detail) ? "validation" : "";
  const map = {
    invalid_credentials: "auth.invalidCredentials",
    email_exists: "auth.emailExists",
    too_many_attempts: "auth.tooMany",
    too_many_requests: "auth.tooMany",
    invalid_or_expired_token: "auth.invalidReset",
    csrf_failed: "auth.genericError",
    not_authenticated: "auth.loginRequired",
  };
  return map[code] || "auth.genericError";
};

export default api;
