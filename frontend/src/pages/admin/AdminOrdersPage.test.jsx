import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminOrdersPage from "./AdminOrdersPage";
import { archiveAdminOrder, permanentlyDeleteAdminOrder, permanentlyDeleteAdminTelegramInquiry, restoreAdminOrder } from "@/lib/api";

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
      evidence_count: 1,
      next_action: "confirm_payment",
    },
  ],
  counts: { payment: 2 },
  total: 2,
  page: 1,
  page_size: 20,
};
let mockQueryOptions;
let mockIsPlaceholderData = false;
const mockQueryClient = { invalidateQueries: jest.fn(), removeQueries: jest.fn() };

jest.mock("@tanstack/react-query", () => ({
  useQuery: (options) => {
    mockQueryOptions = options;
    return { data: mockWorkflowResponse, isLoading: false, isFetching: false, isPlaceholderData: mockIsPlaceholderData };
  },
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to, state }) => <a href={to} data-return-to={state?.returnTo} data-workflow-filter={state?.workflowFilter}>{children}</a>,
  useSearchParams: () => [mockSearchParams, mockSetSearchParams],
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  archiveAdminOrder: jest.fn(),
  getAdminOrderWorkflow: jest.fn(),
  permanentlyDeleteAdminOrder: jest.fn(),
  permanentlyDeleteAdminTelegramInquiry: jest.fn(),
  restoreAdminOrder: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  [...mockSearchParams.keys()].forEach((key) => mockSearchParams.delete(key));
  mockSearchParams.set("stage", "payment_review");
  mockWorkflowResponse.items = [
    {
      kind: "order",
      order_number: "MC-WAITING-1",
      stage: "payment",
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
      stage: "payment",
      status: "payment_review",
      created_at: "2026-09-27T11:00:00Z",
      customer: { name: "Customer B", city: "Tashkent" },
      item_count: 2,
      grand_total: 200000,
      currency: "UZS",
      evidence_count: 1,
      next_action: "confirm_payment",
    },
  ];
  mockWorkflowResponse.counts = { payment: 2 };
  mockWorkflowResponse.total = 2;
  mockQueryOptions = null;
  mockIsPlaceholderData = false;
  mockSetSearchParams.mockReset();
  mockQueryClient.invalidateQueries.mockReset();
  mockQueryClient.removeQueries.mockReset();
  archiveAdminOrder.mockReset();
  restoreAdminOrder.mockReset();
  permanentlyDeleteAdminOrder.mockReset();
  permanentlyDeleteAdminTelegramInquiry.mockReset();
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

  const filterButtons = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')];
  expect(filterButtons.map((button) => button.textContent)).toContain("Pembayaran2");
  expect(filterButtons.find((button) => button.textContent.startsWith("Pembayaran")).getAttribute("aria-pressed")).toBe("true");
  expect(filterButtons.some((button) => button.textContent.includes("Semua"))).toBe(false);
  expect(filterButtons.some((button) => button.textContent.includes("Perlu tindakan"))).toBe(false);
  expect(filterButtons.some((button) => button.textContent.includes("Menunggu pembayaran"))).toBe(false);
  expect(filterButtons.some((button) => button.textContent.includes("Pembayaran diverifikasi"))).toBe(false);
  expect(mockQueryOptions.queryKey[1].stage).toBe("payment");
  expect(mockQueryOptions.staleTime).toBe(15000);
  expect(mockQueryOptions.placeholderData(mockWorkflowResponse)).toBe(mockWorkflowResponse);
  expect(mockQueryOptions.refetchOnMount).toBeUndefined();

  const overview = container.querySelector('[data-testid="workflow-overview"]');
  expect(overview.querySelectorAll("li")).toHaveLength(6);
  expect([...overview.querySelectorAll("li")].map((step) => step.textContent.trim())).toEqual([
    "1Inquiry",
    "2Pembayaran",
    "3Supplier mengirim",
    "4Diterima admin",
    "5Dikirim ke customer",
    "6Selesai",
  ]);
  expect(container.textContent).toContain("Menunggu transfer");
  expect(container.textContent).toContain("Bukti tersimpan · siap dikonfirmasi");
  expect(container.querySelectorAll('[aria-label="Order progress"]')).toHaveLength(2);
  expect(container.textContent).toContain("Satu transfer per order");
  const firstOrderCard = container.querySelector('[data-testid="workflow-card-MC-WAITING-1"]');
  const archiveButton = firstOrderCard.querySelector('[data-testid="archive-order-MC-WAITING-1"]');
  const deleteButton = firstOrderCard.querySelector('[data-testid="delete-order-MC-WAITING-1"]');
  const primaryAction = firstOrderCard.querySelector("a");
  expect(archiveButton.compareDocumentPosition(primaryAction) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(deleteButton.compareDocumentPosition(primaryAction) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("shows the delivered count and completed orders in the Selesai filter", async () => {
  mockSearchParams.set("stage", "delivered");
  mockWorkflowResponse.items = [{
    kind: "order",
    order_number: "MC-DONE-1",
    stage: "delivered",
    status: "delivered",
    created_at: "2026-09-27T12:00:00Z",
    customer: { name: "Customer Selesai", city: "Tashkent" },
    item_count: 1,
    grand_total: 639200,
    currency: "UZS",
    next_action: "view_order",
  }];
  mockWorkflowResponse.counts = { delivered: 1 };
  mockWorkflowResponse.total = 1;
  await act(async () => root.render(<AdminOrdersPage />));

  const completedFilter = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')]
    .find((button) => button.textContent.startsWith("Selesai"));
  expect(completedFilter.textContent).toBe("Selesai1");
  expect(completedFilter.getAttribute("aria-pressed")).toBe("true");
  expect(container.querySelector('[data-testid="workflow-card-MC-DONE-1"]')).not.toBeNull();
});

test("keeps filter controls stable and prevents stale cards from being used during a filter transition", async () => {
  mockSearchParams.set("stage", "supplier_shipping");
  mockIsPlaceholderData = true;
  await act(async () => root.render(<AdminOrdersPage />));

  const results = container.querySelector('[data-testid="workflow-results"]');
  const overlay = container.querySelector('[data-testid="workflow-loading-overlay"]');
  const paymentFilter = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')]
    .find((button) => button.textContent.startsWith("Pembayaran"));
  expect(results.getAttribute("aria-busy")).toBe("true");
  expect(overlay.textContent).toContain("Memuat tahap Supplier mengirim");
  expect(results.querySelector(".pointer-events-none")).not.toBeNull();
  expect(paymentFilter.querySelector("span").className).toContain("w-8");
  expect(paymentFilter.textContent).toBe("Pembayaran2");
});

test("archives directly from the order card beside its primary action", async () => {
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  archiveAdminOrder.mockResolvedValue({ archived: true });
  await act(async () => root.render(<AdminOrdersPage />));

  const card = container.querySelector('[data-testid="workflow-card-MC-WAITING-1"]');
  await act(async () => {
    card.querySelector('[data-testid="archive-order-MC-WAITING-1"]').click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(archiveAdminOrder).toHaveBeenCalledWith("MC-WAITING-1");
  expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["admin-order-workflow"] });
  confirm.mockRestore();
});

test("permanent deletion requires an exact order-number confirmation", async () => {
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  const prompt = jest.spyOn(window, "prompt").mockReturnValue("MC-WAITING-1");
  permanentlyDeleteAdminOrder.mockResolvedValue({ deleted: true });
  await act(async () => root.render(<AdminOrdersPage />));

  const deleteButton = container.querySelector('[data-testid="delete-order-MC-WAITING-1"]');
  await act(async () => {
    deleteButton.click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(prompt).toHaveBeenCalledWith(expect.stringContaining("MC-WAITING-1"));
  expect(permanentlyDeleteAdminOrder).toHaveBeenCalledWith("MC-WAITING-1");
  expect(mockQueryClient.removeQueries).toHaveBeenCalledWith({ queryKey: ["admin-order", "MC-WAITING-1"] });
  confirm.mockRestore();
  prompt.mockRestore();
});

test("inquiry cards offer permanent deletion only and explain Telegram messages remain", async () => {
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  const prompt = jest.spyOn(window, "prompt").mockReturnValue("SC-ABC123");
  permanentlyDeleteAdminTelegramInquiry.mockResolvedValue({ deleted: true });
  mockSearchParams.set("stage", "inquiry");
  mockWorkflowResponse.items = [{
    kind: "inquiry",
    reference: "SC-ABC123",
    stage: "inquiry",
    status: "sent",
    created_at: "2026-09-27T12:00:00Z",
    customer: { name: "Customer E" },
    item_count: 1,
    subtotal: 50000,
    currency: "UZS",
    next_action: "review_inquiry",
  }];
  mockWorkflowResponse.counts = { inquiry: 1 };
  mockWorkflowResponse.total = 1;
  await act(async () => root.render(<AdminOrdersPage />));

  const card = container.querySelector('[data-testid="workflow-card-SC-ABC123"]');
  expect(card.querySelector('[data-testid="archive-order-SC-ABC123"]')).toBeNull();
  expect(card.querySelector('[data-testid="delete-inquiry-SC-ABC123"]')).not.toBeNull();

  await act(async () => {
    card.querySelector('[data-testid="delete-inquiry-SC-ABC123"]').click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("pesan Telegram yang sudah terkirim tidak ikut terhapus"));
  expect(prompt).toHaveBeenCalledWith("Ketik referensi inquiry ini untuk melanjutkan: SC-ABC123");
  expect(permanentlyDeleteAdminTelegramInquiry).toHaveBeenCalledWith("SC-ABC123");
  expect(mockQueryClient.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["admin-order-workflow"] });
  confirm.mockRestore();
  prompt.mockRestore();
});

test("keeps paid legacy orders visible in the supplier stage and preserves the selected filter", async () => {
  mockSearchParams.set("stage", "paid");
  mockWorkflowResponse.items = [{
    kind: "order",
    order_number: "MC-PAID-1",
    stage: "supplier_shipping",
    status: "paid",
    created_at: "2026-09-27T12:00:00Z",
    customer: { name: "Customer C", city: "Tashkent" },
    item_count: 1,
    grand_total: 300000,
    currency: "UZS",
    next_action: "supplier_ship",
  }];
  mockWorkflowResponse.counts = { supplier_shipping: 1 };
  mockWorkflowResponse.total = 1;
  await act(async () => root.render(<AdminOrdersPage />));

  expect(mockQueryOptions.queryKey[1].stage).toBe("supplier_shipping");
  const supplierFilter = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')]
    .find((button) => button.textContent.startsWith("Supplier mengirim"));
  expect(supplierFilter.getAttribute("aria-pressed")).toBe("true");
  expect(container.querySelector('[data-testid="workflow-card-MC-PAID-1"]')).not.toBeNull();
  expect(container.textContent).toContain("Siap ke supplier");

  const detailLink = container.querySelector('[data-testid="workflow-card-MC-PAID-1"] a');
  expect(detailLink.getAttribute("data-return-to")).toBe("/orders?stage=paid");
  expect(detailLink.getAttribute("data-workflow-filter")).toBe("supplier_shipping");
});

test("repairs an out-of-range page after the selected stage loses an order", async () => {
  mockSearchParams.set("stage", "supplier_shipping");
  mockSearchParams.set("page", "8");
  mockWorkflowResponse.items = [];
  mockWorkflowResponse.counts = { supplier_shipping: 1 };
  mockWorkflowResponse.total = 1;
  await act(async () => root.render(<AdminOrdersPage />));

  expect(mockSetSearchParams).toHaveBeenCalledTimes(1);
  const [nextParams, options] = mockSetSearchParams.mock.calls[0];
  expect(nextParams.get("page")).toBe("1");
  expect(options).toEqual({ replace: true });
});

test("lists archived orders in their own filter without mixing them into active stages", async () => {
  mockSearchParams.set("stage", "archived");
  mockWorkflowResponse.items = [{
    kind: "order",
    order_number: "MC-ARCHIVED-1",
    stage: "supplier_shipping",
    status: "supplier_shipping",
    archived_at: "2026-09-29T10:00:00Z",
    created_at: "2026-09-27T12:00:00Z",
    customer: { name: "Customer D", city: "Tashkent" },
    item_count: 1,
    grand_total: 300000,
    currency: "UZS",
    next_action: "view_order",
  }];
  mockWorkflowResponse.counts = { archived: 1, supplier_shipping: 3 };
  mockWorkflowResponse.total = 1;
  await act(async () => root.render(<AdminOrdersPage />));

  expect(mockQueryOptions.queryKey[1].stage).toBe("archived");
  const filters = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')];
  const archivedFilter = filters.find((button) => button.textContent.startsWith("Diarsipkan"));
  expect(archivedFilter.getAttribute("aria-pressed")).toBe("true");
  expect(archivedFilter.textContent).toBe("Diarsipkan1");
  expect(container.querySelector('[data-testid="workflow-card-MC-ARCHIVED-1"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="workflow-card-MC-ARCHIVED-1"]').textContent).toContain("Diarsipkan");
  expect(container.querySelector('[data-testid="restore-order-MC-ARCHIVED-1"]')).not.toBeNull();

  restoreAdminOrder.mockResolvedValue({ archived: false });
  await act(async () => {
    container.querySelector('[data-testid="restore-order-MC-ARCHIVED-1"]').click();
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
  expect(restoreAdminOrder).toHaveBeenCalledWith("MC-ARCHIVED-1");
});
