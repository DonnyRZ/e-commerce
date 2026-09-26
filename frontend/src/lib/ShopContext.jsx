import { createContext, useContext, useMemo, useRef, useState } from "react";
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
  const queue = useRef(Promise.resolve());
  const [mutationCount, setMutationCount] = useState(0);
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
    refetchOnWindowFocus: true,
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
    return queryClient.invalidateQueries({ queryKey: cartKey });
  };

  const mutateCart = (operation) => {
    setMutationCount((count) => count + 1);
    const result = queue.current.then(async () => {
      await queryClient.cancelQueries({ queryKey: cartKey });
      return operation();
    });
    queue.current = result.catch(() => {});
    return result.finally(() => setMutationCount((count) => count - 1));
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
    cartMutationsBlocked: cartMutationsBlocked || mutationCount > 0,
    guestCartMode,
    async addToCart(payload) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      return mutateCart(async () => {
        const data = await addCartItem(payload, { guest: guestCartMode });
        cacheCartForCurrentUser(data);
        return data;
      });
    },
    async updateItem(itemId, quantity) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      return mutateCart(async () => {
        const data = await updateCartItem(itemId, quantity, { guest: guestCartMode });
        cacheCartForCurrentUser(data);
        return data;
      });
    },
    async removeItem(itemId) {
      if (cartMutationsBlocked) {
        throw new Error("cart_merge_pending");
      }
      return mutateCart(async () => {
        await removeCartItem(itemId, { guest: guestCartMode });
        await refresh();
      });
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
