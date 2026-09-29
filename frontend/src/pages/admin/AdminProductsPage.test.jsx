import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminProductsPage from "./AdminProductsPage";
import {
  applyAdminProductSizePresets,
  getAdminProductSizePresets,
  previewAdminProductSizePresets,
  saveAdminProductSizePresets,
} from "@/lib/api";

const mockPresetData = {
  clothing_sizes: ["M", "L", "XL", "XXL"],
  footwear_sizes: ["36", "37", "38", "39", "40"],
  applied_clothing_sizes: null,
  applied_footwear_sizes: null,
};
const mockQueryClient = {
  invalidateQueries: jest.fn(),
  setQueryData: jest.fn(),
};
let mockSearchParams = new URLSearchParams();
const mockSetSearchParams = jest.fn();

jest.mock("@tanstack/react-query", () => ({
  useQuery: (options) => options.queryKey[0] === "admin-product-size-presets"
    ? { data: mockPresetData, isLoading: false, isError: false }
    : { data: { items: [], total: 0, page_size: 20 }, isLoading: false },
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  applyAdminProductSizePresets: jest.fn(),
  deleteAdminProduct: jest.fn(),
  getAdminProductSizePresets: jest.fn(),
  getAdminProducts: jest.fn(),
  previewAdminProductSizePresets: jest.fn(),
  saveAdminProductSizePresets: jest.fn(),
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
  mockQueryClient.setQueryData.mockReset();
  getAdminProductSizePresets.mockReset();
  previewAdminProductSizePresets.mockReset();
  saveAdminProductSizePresets.mockReset();
  applyAdminProductSizePresets.mockReset();
  previewAdminProductSizePresets.mockResolvedValue({
    preview_digest: "a".repeat(64),
    product_count: 3,
    products_changed: 2,
    variants_to_add: 7,
    products: [
      {
        id: "product-1",
        name: "Batik Gamis",
        variants_to_add: 4,
        variant_options: [{ color: "Emerald", size: "M" }],
        more_variants: 3,
      },
    ],
  });
  applyAdminProductSizePresets.mockResolvedValue({
    ...mockPresetData,
    applied_clothing_sizes: ["M", "L", "XL", "XXL"],
    applied_footwear_sizes: ["36", "37", "38", "39", "40"],
    products_changed: 2,
    variants_added: 7,
  });
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

test("previews all affected products before applying CMS size presets", async () => {
  await act(async () => root.render(<AdminProductsPage />));
  expect(container.querySelector('[data-testid="size-preset-clothing"]').value).toBe("M, L, XL, XXL");
  expect(container.querySelector('[data-testid="size-preset-footwear"]').value).toBe("36, 37, 38, 39, 40");

  await act(async () => container.querySelector('[data-testid="size-presets-preview"]').click());
  expect(previewAdminProductSizePresets).toHaveBeenCalledTimes(1);
  expect(container.querySelector('[data-testid="size-presets-preview-result"]').textContent).toContain("7 varian baru");
  expect(container.textContent).toContain("Batik Gamis");
  expect(container.textContent).toContain("+4 varian");

  await act(async () => container.querySelector('[data-testid="size-presets-apply"]').click());
  expect(confirmSpy).toHaveBeenCalledTimes(1);
  expect(applyAdminProductSizePresets).toHaveBeenCalledWith("a".repeat(64));
  expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["products"] });
  expect(container.querySelector('[data-testid="size-presets-preview-result"]')).toBeNull();
});
