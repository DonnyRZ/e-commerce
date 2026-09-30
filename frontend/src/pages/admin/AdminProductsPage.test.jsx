import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminProductsPage from "./AdminProductsPage";

const mockQueryClient = { invalidateQueries: jest.fn() };
let mockSearchParams = new URLSearchParams();
const mockSetSearchParams = jest.fn();

jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: { items: [], total: 0, page_size: 20 }, isLoading: false }),
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  deleteAdminProduct: jest.fn(),
  getAdminProducts: jest.fn(),
  updateAdminProduct: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));

let root;
let container;
let confirmSpy;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockSearchParams = new URLSearchParams();
  mockSetSearchParams.mockReset();
  mockQueryClient.invalidateQueries.mockReset();
  confirmSpy = jest.spyOn(window, "confirm").mockReturnValue(true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  confirmSpy.mockRestore();
});

test("product management no longer shows a global size preset panel", async () => {
  await act(async () => root.render(<AdminProductsPage />));

  expect(container.querySelector('[data-testid="product-size-presets"]')).toBeNull();
  expect(container.querySelector('[data-testid="products-new-button"]')?.textContent).toContain("New Product");
});
