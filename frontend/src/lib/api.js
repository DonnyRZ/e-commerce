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
