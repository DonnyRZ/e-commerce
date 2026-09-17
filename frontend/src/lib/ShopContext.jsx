import { createContext, useContext, useMemo } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useAuth } from "./AuthContext";
import {
  addCartItem,
  addWishlistItem,
  getCart,
  getWishlist,
  removeCartItem,
  removeWishlistItem,
  updateCartItem,
} from "./api";

const ShopContext = createContext(null);

export function ShopProvider({ children }) {
  const {
    user,
    cartMergeError,
    cartMergePending,
    cartMergeReady,
    cartMutationsBlocked,
  } = useAuth();
  const queryClient = useQueryClient();
  const isCustomer = user?.role === "customer";
  const guestCartMode =
    !isCustomer || cartMergeError || (cartMergePending && cartMergeReady);
  const cartKey = ["cart", guestCartMode ? "guest" : user.id];
  const wishlistKey = ["wishlist", isCustomer ? user.id : "guest"];

  const cartQuery = useQuery({
    queryKey: cartKey,
    // The storefront can be opened from the admin console via “View Store”.
    // In that case an admin session must use the browser's guest/demo cart
    // explicitly instead of sending the admin cookie to the customer cart
    // endpoint (which correctly rejects non-customer users).
    queryFn: () => getCart({ guest: guestCartMode }),
    enabled: !isCustomer || cartMergeReady,
  });
  const wishlistQuery = useQuery({
    queryKey: wishlistKey,
    queryFn: getWishlist,
    enabled: isCustomer,
    retry: false,
  });

  const cart = cartQuery.data || null;
  const wishlistIds = useMemo(
    () => new Set((wishlistQuery.data?.items || []).map((i) => i.product_id)),
    [wishlistQuery.data]
  );

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: cartKey });
  };

  const cacheCartForCurrentUser = (data) => {
    const currentUserId = queryClient.getQueryData(["auth", "me"])?.id;
    if (!isCustomer || guestCartMode || currentUserId === user.id) {
      queryClient.setQueryData(cartKey, data);
    }
  };

  const value = {
    cart,
    cartLoading: cartQuery.isLoading || (isCustomer && !cartMergeReady),
    cartError: cartQuery.isError,
    refetchCart: cartQuery.refetch,
    cartCount: cart?.item_count ?? 0,
    wishlistCount: isCustomer ? wishlistIds.size : 0,
    wishlistIds,
    wishlist: wishlistQuery.data || null,
    cartMergePending,
    cartMutationsBlocked,
    guestCartMode,
    async addToCart(payload) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      const data = await addCartItem(payload, { guest: guestCartMode });
      cacheCartForCurrentUser(data);
      return data;
    },
    async updateItem(itemId, quantity) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      const data = await updateCartItem(itemId, quantity, { guest: guestCartMode });
      cacheCartForCurrentUser(data);
      return data;
    },
    async removeItem(itemId) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      await removeCartItem(itemId, { guest: guestCartMode });
      refresh();
    },
    async toggleWishlist(productId) {
      if (!isCustomer) return "auth_required";
      if (wishlistIds.has(productId)) {
        await removeWishlistItem(productId);
      } else {
        await addWishlistItem(productId);
      }
      queryClient.invalidateQueries({ queryKey: wishlistKey });
      return wishlistIds.has(productId) ? "removed" : "added";
    },
  };

  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>;
}

export function useShop() {
  return useContext(ShopContext);
}
