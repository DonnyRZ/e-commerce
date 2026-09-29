import { act } from "react";
import { createRoot } from "react-dom/client";
import HomePage from "./HomePage";

jest.mock("@tanstack/react-query", () => ({
  useQuery: ({ queryKey }) => {
    if (queryKey[0] === "catalog-tree") {
      return {
        data: [{
          id: "dept-batik",
          slug: "batik",
          kind: "department",
          is_active: true,
          product_count: 0,
          children: [],
          image_url: null,
          translations: { id: { title: "Batik" } },
        }],
        isSuccess: true,
        isLoading: false,
        isError: false,
      };
    }
    if (queryKey[0] === "cms") {
      return {
        data: {
          sections: [],
          department_visuals: [{
            slug: "batik",
            image_url: "/api/v1/cms/media/file/asset-123",
          }],
        },
        isSuccess: true,
        isLoading: false,
        isError: false,
      };
    }
    return { data: { items: [] }, isSuccess: true, isLoading: false, isError: false };
  },
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
}), { virtual: true });
jest.mock("@/i18n", () => ({ useI18n: () => ({ locale: "id", t: () => "Belanja" }) }));
jest.mock("@/lib/api", () => ({ getCatalogTree: jest.fn(), getCmsBundle: jest.fn(), getProducts: jest.fn() }));
jest.mock("@/components/common/CmsBannerStrip", () => () => null);
jest.mock("@/components/common/ProductRail", () => () => null);
jest.mock("@/components/common/ErrorState", () => () => null);

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("shows the uploaded department image with its coming-soon badge when no products exist", async () => {
  await act(async () => root.render(<HomePage />));

  const image = container.querySelector('[data-testid="department-card-batik"] img');
  expect(image).not.toBeNull();
  expect(image.getAttribute("src")).toContain("/api/v1/cms/media/file/asset-123");
  expect(container.querySelector('[data-testid="department-card-batik"]').textContent).toContain("Segera hadir");
});
