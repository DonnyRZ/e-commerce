import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminOrdersPage from "./AdminOrdersPage";

const mockSearchParams = new URLSearchParams("?stage=payment_review");
const mockSetSearchParams = jest.fn();
const mockWorkflowResponse = {
  items: [
    {
      kind: "order",
      order_number: "MC-WAITING-1",
      stage: "pending_payment",
      status: "pending_payment",
      created_at: "2026-09-27T10:00:00Z",
      customer: { name: "Customer A", city: "Tashkent" },
      item_count: 1,
      grand_total: 100000,
      currency: "UZS",
      next_action: "wait_payment",
    },
    {
      kind: "order",
      order_number: "MC-REVIEW-1",
      stage: "payment_review",
      status: "payment_review",
      created_at: "2026-09-27T11:00:00Z",
      customer: { name: "Customer B", city: "Tashkent" },
      item_count: 2,
      grand_total: 200000,
      currency: "UZS",
      next_action: "verify_payment",
    },
  ],
  counts: { payment: 2 },
  total: 2,
  page: 1,
  page_size: 20,
};
let mockQueryOptions;

jest.mock("@tanstack/react-query", () => ({
  useQuery: (options) => {
    mockQueryOptions = options;
    return { data: mockWorkflowResponse, isLoading: false };
  },
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to }) => <a href={to}>{children}</a>,
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}), { virtual: true });
jest.mock("@/lib/api", () => ({ getAdminOrderWorkflow: jest.fn() }));

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockQueryOptions = null;
  mockSetSearchParams.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("groups payment stages into one filter and shows each order's current payment task", async () => {
  await act(async () => root.render(<AdminOrdersPage />));

  const filterButtons = [...container.querySelectorAll('[role="tablist"] button')];
  expect(filterButtons.map((button) => button.textContent)).toContain("Pembayaran2");
  expect(filterButtons.find((button) => button.textContent.startsWith("Pembayaran")).getAttribute("aria-selected")).toBe("true");
  expect(filterButtons.some((button) => button.textContent.includes("Menunggu pembayaran"))).toBe(false);
  expect(filterButtons.some((button) => button.textContent.includes("Pembayaran diverifikasi"))).toBe(false);
  expect(mockQueryOptions.queryKey[1].stage).toBe("payment");

  expect(container.textContent).toContain("Menunggu transfer");
  expect(container.textContent).toContain("Bukti perlu diperiksa");
  expect(container.querySelectorAll('[aria-label="Order progress"]')).toHaveLength(2);
  expect(container.textContent).toContain("Satu transfer per order");
});
