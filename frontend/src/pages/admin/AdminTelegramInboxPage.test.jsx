import { act } from "react";
import { createRoot } from "react-dom/client";
import AdminTelegramInboxPage from "./AdminTelegramInboxPage";

let inboxQueryOptions;
let mockSelectedId;
const mockQueryClient = { invalidateQueries: jest.fn() };
const mockInboxResponse = {
  items: [
    {
      id: "conversation-1",
      chat_id: 123,
      customer_name: "Customer One",
      customer_username: "customerone",
      locale: "id",
      status: "needs_admin",
      last_message_at: "2026-09-29T10:30:00Z",
      last_message: { type: "text", text: "Saya mencari produk" },
      workflow_stage: "received_by_admin",
      order_count: 2,
      latest_order: { order_number: "MC-LATEST-1", status: "paid", stage: "supplier_shipping" },
    },
  ],
  counts: {
    inquiry: 2,
    payment: 1,
    supplier_shipping: 3,
    received_by_admin: 4,
    customer_shipping: 5,
    delivered: 6,
    archived: 7,
  },
  total: 21,
  next_cursor: null,
};
const mockConversation = {
  ...mockInboxResponse.items[0],
  can_send: false,
  orders: [
    { order_number: "MC-LATEST-1", status: "paid", stage: "supplier_shipping", archived_at: null },
    { order_number: "MC-OLDER-1", status: "supplier_shipping", stage: "received_by_admin", archived_at: null },
  ],
  messages: [],
  candidates: [],
};

jest.mock("@tanstack/react-query", () => ({
  useQuery: (options) => {
    if (options.queryKey[0] === "admin-telegram-inbox" && options.queryKey[4] === "cursor") {
      return { data: null, isFetching: false, isError: false };
    }
    if (options.queryKey[0] === "admin-telegram-inbox") {
      inboxQueryOptions = options;
      return { data: mockInboxResponse, isLoading: false };
    }
    if (options.queryKey[0] === "admin-telegram-product-search") {
      return { data: { items: [] }, isFetching: false };
    }
    if (options.queryKey[0] === "admin-telegram-conversation") {
      mockSelectedId = options.queryKey[1];
      return { data: mockSelectedId ? mockConversation : undefined, isLoading: false };
    }
    throw new Error(`Unexpected query: ${options.queryKey[0]}`);
  },
  useQueryClient: () => mockQueryClient,
}));
jest.mock("react-router-dom", () => ({
  Link: ({ children, to }) => <a href={to}>{children}</a>,
}), { virtual: true });
jest.mock("@/lib/api", () => ({
  createAdminTelegramOrder: jest.fn(),
  getAdminTelegramConversation: jest.fn(),
  getAdminTelegramInbox: jest.fn(),
  reviewAdminTelegramCandidate: jest.fn(),
  searchAdminTelegramProducts: jest.fn(),
  sendAdminTelegramCandidate: jest.fn(),
  sendAdminTelegramPhoto: jest.fn(),
  sendAdminTelegramText: jest.fn(),
  updateAdminTelegramConversation: jest.fn(),
}));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

let root;
let container;

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  inboxQueryOptions = null;
  mockSelectedId = null;
  mockQueryClient.invalidateQueries.mockReset();
  Element.prototype.scrollIntoView = jest.fn();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
});

test("uses the Orders workflow stages as primary Inbox filters and keeps chat status secondary", async () => {
  await act(async () => root.render(<AdminTelegramInboxPage />));

  const stageButtons = [...container.querySelectorAll('[aria-label="Filter tahap order"] button')];
  expect(stageButtons.map((button) => button.textContent)).toEqual([
    "Pending Order2",
    "Pembayaran1",
    "Supplier mengirim3",
    "Diterima admin4",
    "Dikirim ke customer5",
    "Selesai6",
    "Diarsipkan7",
  ]);
  expect(container.querySelector('[aria-label="Filter status chat"]')).not.toBeNull();
  expect([...container.querySelector('[aria-label="Filter status chat"]').options].map((option) => option.value)).toEqual([
    "all",
    "needs_admin",
    "waiting_customer",
    "ready_for_order",
  ]);
  expect(inboxQueryOptions.queryKey.slice(0, 4)).toEqual(["admin-telegram-inbox", "all", "all", ""]);

  await act(async () => stageButtons[3].dispatchEvent(new MouseEvent("click", { bubbles: true })));
  expect(inboxQueryOptions.queryKey[1]).toBe("received_by_admin");

  const chatStatus = container.querySelector('[aria-label="Filter status chat"]');
  await act(async () => {
    chatStatus.value = "waiting_customer";
    chatStatus.dispatchEvent(new Event("change", { bubbles: true }));
  });
  expect(inboxQueryOptions.queryKey[2]).toBe("waiting_customer");
});

test("shows a conversation once with related orders linked from the selected thread", async () => {
  await act(async () => root.render(<AdminTelegramInboxPage />));

  expect(container.querySelectorAll('[data-testid="telegram-conversation-conversation-1"]')).toHaveLength(1);
  expect(container.querySelector('[data-testid="telegram-conversation-conversation-1"]').textContent).toContain("2 order");
  await act(async () => container.querySelector('[data-testid="telegram-conversation-conversation-1"]').click());

  const relatedOrders = container.querySelector('[data-testid="telegram-conversation-orders"]');
  expect(relatedOrders.textContent).toContain("Order terkait · 2");
  expect([...relatedOrders.querySelectorAll("a")].map((link) => link.getAttribute("href"))).toEqual([
    "/admin/orders/MC-LATEST-1",
    "/admin/orders/MC-OLDER-1",
  ]);
});
