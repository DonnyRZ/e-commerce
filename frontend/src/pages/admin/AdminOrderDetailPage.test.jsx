import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminOrderDetailPage from "./AdminOrderDetailPage";
import { confirmAdminPayment, uploadAdminPaymentEvidence } from "@/lib/api";

let mockOrder;
let mockQueryClient;
let resolveUpload;

jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: mockOrder, isLoading: false }),
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to }) => <a href={to}>{children}</a>,
  useParams: () => ({ orderNumber: "MC-UX-1" }),
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  confirmAdminPayment: jest.fn(),
  getAdminOrder: jest.fn(),
  retryAdminPaymentNotification: jest.fn(),
  updateAdminOrderStatus: jest.fn(),
  updateAdminFulfillment: jest.fn(),
  uploadAdminPaymentEvidence: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

const pendingOrder = () => ({
  order_number: "MC-UX-1",
  order_source: "telegram_manual",
  status: "pending_payment",
  payment_state: "unpaid",
  created_at: "2026-09-28T10:00:00Z",
  grand_total: 580000,
  subtotal: 500000,
  shipping_amount: 80000,
  currency: "UZS",
  email: "customer@example.com",
  shipping_address: { recipient_name: "Customer", city: "Tashkent", country_code: "UZ" },
  items: [{ sku: "SKU-1", product_name: "Produk test", quantity: 1, unit_price: 500000, line_total: 500000 }],
  payment: {
    id: "payment-1",
    status: "pending",
    amount: 580000,
    merchant_trans_id: "MANUAL-TEST",
    telegram_notification: { status: "sent", message_id: 41 },
    destination: null,
    evidence: [],
  },
  fulfillment: [],
  activity: [],
});

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockOrder = pendingOrder();
  mockQueryClient = {
    invalidateQueries: jest.fn(),
    setQueryData: jest.fn((_key, updater) => {
      mockOrder = typeof updater === "function" ? updater(mockOrder) : updater;
    }),
  };
  uploadAdminPaymentEvidence.mockReset();
  confirmAdminPayment.mockReset();
  resolveUpload = null;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("keeps six-stage payment view in place while evidence is stored for audit", async () => {
  await act(async () => root.render(<AdminOrderDetailPage />));

  expect(container.querySelectorAll('[data-testid="order-progress"] li')).toHaveLength(6);
  expect(container.querySelector('[data-testid="order-progress"] li[aria-current="step"]').textContent).toContain("Pembayaran");
  expect(container.querySelector('[data-testid="active-payment-stage"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="active-payment-review"]')).toBeNull();
  expect(container.querySelector('[data-testid="confirm-payment-and-continue"]').disabled).toBe(true);

  const evidence = {
    id: "evidence-1",
    original_filename: "transfer.pdf",
    mime_type: "application/pdf",
    file_size: 128,
    download_url: "/evidence/1",
    created_at: "2026-09-28T10:05:00Z",
  };
  uploadAdminPaymentEvidence.mockImplementation((_orderNumber, _file, onProgress) => {
    onProgress(72);
    return new Promise((resolve) => { resolveUpload = resolve; });
  });

  const input = container.querySelector('[data-testid="payment-evidence-input"]');
  const file = new File(["%PDF-test"], "transfer.pdf", { type: "application/pdf" });
  Object.defineProperty(input, "files", { configurable: true, value: [file] });
  await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
  expect(container.querySelector('[data-testid="selected-payment-evidence"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="save-payment-evidence"]')).not.toBeNull();

  await act(async () => {
    container.querySelector('[data-testid="save-payment-evidence"]').click();
    await Promise.resolve();
  });
  expect(container.querySelector('[aria-label="Progres upload bukti transfer"]').value).toBe(72);

  await act(async () => {
    resolveUpload(evidence);
    await Promise.resolve();
  });

  expect(uploadAdminPaymentEvidence).toHaveBeenCalledTimes(1);
  expect(container.querySelector('[data-testid="active-payment-stage"]')).not.toBeNull();
  expect(container.querySelector('[data-testid="active-payment-review"]')).toBeNull();
  expect(container.querySelector('[data-testid="order-progress"] li[aria-current="step"]').textContent).toContain("Pembayaran");
  expect(container.querySelector('[data-testid="confirm-payment-and-continue"]').disabled).toBe(false);
  expect(container.textContent).toContain("Upload ini tidak mengonfirmasi pembayaran");
});

test("confirmed payment advances the shared progress to supplier shipping", async () => {
  mockOrder.status = "paid";
  mockOrder.payment.status = "paid";
  mockOrder.payment_state = "paid";
  await act(async () => root.render(<AdminOrderDetailPage />));

  expect(container.querySelector('[data-testid="order-progress"] li[aria-current="step"]').textContent).toContain("Supplier mengirim");
  expect(container.querySelector('[data-testid="active-fulfillment"]')).not.toBeNull();
});
