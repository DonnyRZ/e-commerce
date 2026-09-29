import { act } from "react";
import { createRoot } from "react-dom/client";
import Header from "./Header";

jest.mock("@tanstack/react-query", () => ({ useQuery: () => ({ data: [] }) }));
jest.mock("@/i18n", () => ({ useI18n: () => ({ locale: "id", t: (key) => key }) }));
jest.mock("@/lib/api", () => ({ getCatalogTree: jest.fn() }));
jest.mock("@/lib/ShopContext", () => ({ useShop: () => ({ cartCount: 0, wishlistCount: 0 }) }));
jest.mock("@/lib/AuthContext", () => ({ useAuth: () => ({ user: null }) }));
jest.mock("@/components/layout/LanguageSelector", () => () => null);
jest.mock("@/components/layout/MobileNavigation", () => () => null);
jest.mock("@/components/layout/SearchOverlay", () => () => null);
jest.mock("@/components/brand/BrandLogo", () => ({ testId }) => <span data-testid={testId}>Brand</span>);
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  Object.defineProperty(window, "scrollY", { configurable: true, writable: true, value: 0 });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("hides while scrolling down and returns when the customer scrolls up", async () => {
  await act(async () => root.render(<Header />));
  const header = container.querySelector('[data-testid="site-header"]');
  const scrollTo = (y) => act(() => {
    window.scrollY = y;
    window.dispatchEvent(new Event("scroll"));
  });

  expect(header.className).toContain("translate-y-0");
  scrollTo(40);
  expect(header.className).toContain("-translate-y-full");
  scrollTo(30);
  expect(header.className).toContain("-translate-y-full");
  scrollTo(15);
  expect(header.className).toContain("translate-y-0");
  scrollTo(0);
  expect(header.className).toContain("translate-y-0");
});
