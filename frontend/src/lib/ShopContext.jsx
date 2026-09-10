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
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const cartKey = ["cart", user?.id || "guest"];
  const wishlistKey = ["wishlist", user?.id || "guest"];

  const cartQuery = useQuery({ queryKey: cartKey, queryFn: getCart });
  const wishlistQuery = useQuery({
    queryKey: wishlistKey,
    queryFn: getWishlist,
    enabled: Boolean(user),
    retry: false,
  });

  const cart = cartQuery.data || null;
  const wishlistIds = useMemo(
    () => new Set((wishlistQuery.data?.items || []).map((i) => i.product_id)),
    [wishlistQuery.data]
  );

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["cart"] });
    if (user) queryClient.invalidateQueries({ queryKey: ["wishlist"] });
  };

  const value = {
    cart,
    cartLoading: cartQuery.isLoading,
    cartError: cartQuery.isError,
    refetchCart: cartQuery.refetch,
    cartCount: cart?.item_count ?? 0,
    wishlistCount: user ? wishlistIds.size : 0,
    wishlistIds,
    wishlist: wishlistQuery.data || null,
    async addToCart(payload) {
      const data = await addCartItem(payload);
      queryClient.setQueryData(cartKey, data);
      return data;
    },
    async updateItem(itemId, quantity) {
      const data = await updateCartItem(itemId, quantity);
      queryClient.setQueryData(cartKey, data);
      return data;
    },
    async removeItem(itemId) {
      await removeCartItem(itemId);
      refresh();
    },
    async toggleWishlist(productId) {
      if (!user) return "auth_required";
      if (wishlistIds.has(productId)) {
        await removeWishlistItem(productId);
      } else {
        await addWishlistItem(productId);
      }
      queryClient.invalidateQueries({ queryKey: ["wishlist"] });
      return wishlistIds.has(productId) ? "removed" : "added";
    },
  };

  return <ShopContext.Provider value={value}>{children}</ShopContext.Provider>;
}

export function useShop() {
  return useContext(ShopContext);
}
