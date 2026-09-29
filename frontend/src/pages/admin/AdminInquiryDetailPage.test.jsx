import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminInquiryDetailPage from "./AdminInquiryDetailPage";

const mockNavigate = jest.fn();
const mockInquiry = {
  reference: "SC-INQUIRY-1",
  status: "sent",
  created_at: "2026-09-28T10:00:00Z",
  item_count: 1,
  subtotal: 100000,
  currency: "UZS",
  snapshot: { items: [{ sku: "SKU-1", name: "Produk test", quantity: 1, unit_price: 100000, line_total: 100000 }] },
};

jest.mock("@tanstack/react-query", () => ({
  useQuery: () => ({ data: mockInquiry, isLoading: false }),
  useMutation: () => ({ mutate: jest.fn(), isPending: false }),
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to }) => <a href={to}>{children}</a>,
  useNavigate: () => mockNavigate,
  useParams: () => ({ reference: "SC-INQUIRY-1" }),
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  createAdminOrderFromInquiry: jest.fn(),
  getAdminTelegramInquiry: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  mockNavigate.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("inquiry uses the shared six-stage progress and shows the live payment summary", async () => {
  await act(async () => root.render(<AdminInquiryDetailPage />));

  const progress = container.querySelector('[aria-label="Tahapan order"]');
  expect(progress.querySelectorAll("li")).toHaveLength(6);
  expect(progress.querySelector('li[aria-current="step"]').textContent).toContain("Inquiry");
  expect(progress.textContent).toContain("Supplier mengirim");
  expect(progress.textContent).toContain("Diterima admin");
  expect(progress.textContent).toContain("Dikirim ke customer");
  expect(container.querySelectorAll('[data-testid="inquiry-order-form"] input[required]')).toHaveLength(4);
  expect(container.querySelector('[data-testid="inquiry-order-summary"]').textContent).toContain("100,000");
  expect(container.querySelector('[data-testid="create-order-from-inquiry"]').textContent).toContain("Buat order & kirim pilihan bank");
});
