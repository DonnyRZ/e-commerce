import { act } from "react";
import { createRoot } from "react-dom/client";
import ProductPage from "./ProductPage";

const mockAddToCart = jest.fn();
const mockProduct = {
  id: "product123456",
  slug: "sample-shirt",
  product_type: "apparel",
  size_selection_required: true,
  brand: "Example",
  base_price: 100000,
  compare_at_price: null,
  media: [],
  attributes: {},
  translations: { en: { title: "Sample Shirt" } },
  category: { department: "women-muslimah", ancestors: [] },
  variants: [
    { id: "variant-size-m", sku: "SHIRT-M", option_values: { size: "M" }, is_active: true },
    { id: "variant-size-l", sku: "SHIRT-L", option_values: { size: "L" }, is_active: true },
  ],
};

jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: mockProduct, isLoading: false, isError: false }),
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children }) => <a href="/">{children}</a>,
  useLocation: () => ({ pathname: "/product/sample-shirt", state: null }),
  useNavigate: () => jest.fn(),
  useParams: () => ({ slug: "sample-shirt" }),
}), { virtual: true });
jest.mock("@/i18n", () => ({ useI18n: () => ({ locale: "en", t: (key) => key }) }));
jest.mock("@/lib/api", () => ({ getProduct: jest.fn() }));
jest.mock("@/lib/ShopContext", () => ({ useShop: () => ({
  addToCart: mockAddToCart,
  cartMutationsBlocked: false,
  toggleWishlist: jest.fn(),
  wishlistIds: new Set(),
}) }));
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("@/components/common/EmptyState", () => () => <div />);
jest.mock("@/components/common/ErrorState", () => () => <div />);
jest.mock("@/components/common/ImageWithFallback", () => () => <div />);
jest.mock("@/components/common/PriceDisplay", () => () => <div />);
jest.mock("@/components/pdp/SizeGuide", () => () => <div />);
jest.mock("@/components/ui/skeleton", () => ({ Skeleton: () => <div /> }));
jest.mock("@/components/ui/accordion", () => ({
  Accordion: ({ children }) => <div>{children}</div>,
  AccordionContent: ({ children }) => <div>{children}</div>,
  AccordionItem: ({ children }) => <div>{children}</div>,
  AccordionTrigger: ({ children }) => <div>{children}</div>,
}));

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockProduct.product_type = "apparel";
  mockProduct.size_selection_required = true;
  mockProduct.category.department = "women-muslimah";
  mockProduct.variants = [
    { id: "variant-size-m", sku: "SHIRT-M", option_values: { size: "M" }, is_active: true },
    { id: "variant-size-l", sku: "SHIRT-L", option_values: { size: "L" }, is_active: true },
  ];
  mockAddToCart.mockReset().mockResolvedValue({});
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("customer must explicitly choose a size before adding the product to cart", async () => {
  await act(async () => root.render(<ProductPage />));
  const addButton = container.querySelector('[data-testid="pdp-add-to-cart"]');
  expect(addButton.disabled).toBe(true);
  expect(mockAddToCart).not.toHaveBeenCalled();

  await act(async () => container.querySelector('[data-testid="pdp-option-size-m"]').click());
  expect(addButton.disabled).toBe(false);
  await act(async () => addButton.click());
  expect(mockAddToCart).toHaveBeenCalledWith({
    product_id: "product123456",
    variant_id: "variant-size-m",
    quantity: 1,
  });
});

test("changing another option never silently selects a size", async () => {
  mockProduct.variants = [
    { id: "black-m", sku: "SHIRT-BLACK-M", option_values: { color: "Black", size: "M" }, is_active: true },
    { id: "black-l", sku: "SHIRT-BLACK-L", option_values: { color: "Black", size: "L" }, is_active: true },
    { id: "red-m", sku: "SHIRT-RED-M", option_values: { color: "Red", size: "M" }, is_active: true },
    { id: "red-l", sku: "SHIRT-RED-L", option_values: { color: "Red", size: "L" }, is_active: true },
  ];
  await act(async () => root.render(<ProductPage />));
  const addButton = container.querySelector('[data-testid="pdp-add-to-cart"]');
  expect(addButton.disabled).toBe(true);
  await act(async () => container.querySelector('[data-testid="pdp-color-red"]').click());
  expect(addButton.disabled).toBe(true);
  await act(async () => container.querySelector('[data-testid="pdp-option-size-l"]').click());
  expect(addButton.disabled).toBe(false);
  await act(async () => addButton.click());
  expect(mockAddToCart).toHaveBeenCalledWith({
    product_id: "product123456",
    variant_id: "red-l",
    quantity: 1,
  });
});

test("products outside apparel and footwear keep automatic variant selection", async () => {
  mockProduct.product_type = "parfum";
  mockProduct.size_selection_required = false;
  mockProduct.category.department = "parfum";
  mockProduct.variants = [
    { id: "perfume-50", sku: "PERFUME-50", option_values: { volume: "50ml" }, is_active: true },
    { id: "perfume-100", sku: "PERFUME-100", option_values: { volume: "100ml" }, is_active: true },
  ];
  await act(async () => root.render(<ProductPage />));
  const addButton = container.querySelector('[data-testid="pdp-add-to-cart"]');
  expect(addButton.disabled).toBe(false);
  await act(async () => addButton.click());
  expect(mockAddToCart).toHaveBeenCalledWith({
    product_id: "product123456",
    variant_id: "perfume-50",
    quantity: 1,
  });
});

test("scoped clothing products without size variants cannot be ordered without a size", async () => {
  mockProduct.size_selection_required = true;
  mockProduct.category.department = "women-muslimah";
  mockProduct.variants = [
    { id: "shirt-black", sku: "SHIRT-BLACK", option_values: { color: "Black" }, is_active: true },
  ];
  await act(async () => root.render(<ProductPage />));
  expect(container.querySelector('[data-testid="pdp-add-to-cart"]').disabled).toBe(true);
  expect(mockAddToCart).not.toHaveBeenCalled();
});
