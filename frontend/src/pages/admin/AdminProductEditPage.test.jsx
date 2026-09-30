import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminProductEditPage from "./AdminProductEditPage";
import { saveAdminProductEditor } from "@/lib/api";

let mockProduct;
const mockQueryClient = {
  invalidateQueries: jest.fn(),
  setQueryData: jest.fn(),
};
const mockNavigate = jest.fn();

jest.mock("@tanstack/react-query", () => ({
  useQuery: (options) => options.queryKey[0] === "admin-categories"
    ? { data: [{
        id: "category-12345678",
        kind: "category",
        slug: "tops",
        department: "women-muslimah",
        is_leaf: true,
        is_active: true,
        translations: { en: { name: "Tops" } },
      }], isLoading: false }
    : { data: mockProduct, isLoading: false },
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useNavigate: () => mockNavigate,
  useParams: () => ({ productId: "product-12345678" }),
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  createAdminProduct: jest.fn(),
  deleteAdminProduct: jest.fn(),
  deleteAdminVariant: jest.fn(),
  getAdminCategories: jest.fn(),
  getAdminProduct: jest.fn(),
  saveAdminProductEditor: jest.fn(),
  uploadCmsMedia: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: {
  error: jest.fn(),
  success: jest.fn(),
  warning: jest.fn(),
} }));

const product = (overrides = {}) => ({
  id: "product-12345678",
  revision: 1,
  category_id: "category-12345678",
  product_type: "apparel",
  brand: "Original",
  base_price: 100000,
  compare_at_price: null,
  status: "draft",
  attributes: {},
  tags: [],
  media: [],
  translations: { en: { name: "Product name", short_description: "", description: "" } },
  variants: [{
    id: "variant-12345678",
    sku: "TEST-S",
    option_values: { size: "S" },
    stock_quantity: 3,
    price_override: null,
    sale_price_override: null,
    media_id: null,
    image_url: "",
    is_active: true,
  }],
  ...overrides,
});

let root;
let container;

const change = async (selector, value) => {
  const input = container.querySelector(selector);
  await act(async () => {
    const setter = Object.getOwnPropertyDescriptor(input.constructor.prototype, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
};

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockProduct = product();
  mockNavigate.mockReset();
  mockQueryClient.invalidateQueries.mockReset();
  mockQueryClient.setQueryData.mockReset();
  saveAdminProductEditor.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("a background refetch warns but never replaces unsaved editor fields", async () => {
  await act(async () => root.render(<AdminProductEditPage />));
  await change('[data-testid="editor-brand"]', "My unsaved draft");

  mockProduct = product({ revision: 2, brand: "Saved by another admin" });
  await act(async () => root.render(<AdminProductEditPage />));

  expect(container.querySelector('[data-testid="editor-brand"]').value).toBe("My unsaved draft");
  expect(container.querySelector('[data-testid="product-remote-update-warning"]').textContent)
    .toContain("Your unsaved draft is still here");
});

test("stale saves show a comparison and overwrite only after an explicit choice", async () => {
  await act(async () => root.render(<AdminProductEditPage />));
  await change('[data-testid="editor-brand"]', "My deliberate draft");

  const latest = product({ revision: 2, brand: "Boss's saved version" });
  const saved = product({ revision: 3, brand: "My deliberate draft" });
  saveAdminProductEditor
    .mockRejectedValueOnce({ response: { status: 409, data: { detail: { error: "product_changed", current: latest } } } })
    .mockResolvedValueOnce(saved);

  await act(async () => {
    container.querySelector('[data-testid="editor-save"]').click();
    await Promise.resolve();
  });

  expect(container.querySelector('[data-testid="product-conflict-dialog"]')).not.toBeNull();
  expect(container.textContent).toContain("Boss's saved version");
  expect(container.querySelector('[data-testid="editor-brand"]').value).toBe("My deliberate draft");
  expect(saveAdminProductEditor.mock.calls[0][1]).toMatchObject({
    brand: "My deliberate draft",
    expected_revision: 1,
    overwrite_confirmed: false,
  });

  await act(async () => {
    container.querySelector('[data-testid="product-conflict-overwrite"]').click();
    await Promise.resolve();
  });

  expect(saveAdminProductEditor).toHaveBeenCalledTimes(2);
  expect(saveAdminProductEditor.mock.calls[1][1]).toMatchObject({
    brand: "My deliberate draft",
    expected_revision: 2,
    overwrite_confirmed: true,
    overwrote_revision: 1,
  });
  expect(container.querySelector('[data-testid="product-conflict-dialog"]')).toBeNull();
  expect(container.querySelector('[data-testid="editor-brand"]').value).toBe("My deliberate draft");
});
