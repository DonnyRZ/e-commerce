jest.mock("./api", () => ({ addWishlistItem: jest.fn() }));
jest.mock("sonner", () => ({ toast: { success: jest.fn(), error: jest.fn() } }));

import { toast } from "sonner";
import { addWishlistItem } from "./api";
import { completeCustomerAuth, getCustomerReturnTo } from "./customerAuthFlow";

describe("customer login continuation", () => {
  beforeEach(() => jest.clearAllMocks());

  test("restores only internal return paths", () => {
    expect(getCustomerReturnTo({ returnTo: "/product/hijab?color=black" })).toBe(
      "/product/hijab?color=black"
    );
    expect(getCustomerReturnTo({ returnTo: "//evil.example" })).toBe("/account");
    expect(getCustomerReturnTo({ returnTo: "/\\evil.example" })).toBe("/account");
  });

  test("completes a pending wishlist action and returns to its origin", async () => {
    addWishlistItem.mockResolvedValue({});
    const queryClient = { invalidateQueries: jest.fn().mockResolvedValue() };
    const navigate = jest.fn();
    const state = {
      returnTo: "/product/hijab",
      intent: { type: "wishlist_add", productId: "product-123" },
    };

    await completeCustomerAuth({
      state,
      user: { id: "customer-1" },
      queryClient,
      navigate,
      t: (key) => key,
    });

    expect(addWishlistItem).toHaveBeenCalledWith("product-123");
    expect(queryClient.invalidateQueries).toHaveBeenCalledWith({
      queryKey: ["wishlist", "customer-1"],
    });
    expect(toast.success).toHaveBeenCalledWith("wishlist.added");
    expect(navigate).toHaveBeenCalledWith("/product/hijab", { replace: true });
  });

  test("still returns to the origin and reports a failed wishlist save", async () => {
    addWishlistItem.mockRejectedValue(new Error("offline"));
    const navigate = jest.fn();

    await completeCustomerAuth({
      state: {
        returnTo: "/shop?category=scarves",
        intent: { type: "wishlist_add", productId: "product-123" },
      },
      user: { id: "customer-1" },
      queryClient: { invalidateQueries: jest.fn() },
      navigate,
      t: (key) => key,
    });

    expect(toast.error).toHaveBeenCalledWith("wishlist.saveAfterLoginFailed");
    expect(navigate).toHaveBeenCalledWith("/shop?category=scarves", { replace: true });
  });
});
