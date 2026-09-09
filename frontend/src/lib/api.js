import axios from "axios";

const api = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  withCredentials: true,
  headers: { "Content-Type": "application/json" },
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

export default api;
