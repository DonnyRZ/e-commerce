import { createContext, useContext, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { authLogin, authLogout, authMe, authRegister, mergeCart } from "./api";
import { translations } from "@/i18n/translations";
import { toast } from "sonner";

const AuthContext = createContext(null);

async function mergeGuestCart(queryClient) {
  try {
    const result = await mergeCart();
    queryClient.invalidateQueries({ queryKey: ["cart"] });
    queryClient.invalidateQueries({ queryKey: ["wishlist"] });
    if (result.adjustments?.length) {
      const loc = window.localStorage.getItem("mc_locale") || "en";
      toast.info(
        translations[loc]?.["cart.mergeAdjusted"] ??
          translations.en["cart.mergeAdjusted"]
      );
    }
  } catch {
    /* guest-cart merge is best-effort */
  }
}

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const { setLocale } = useI18n();
  const previousUserId = useRef(undefined);
  const { data: user = null, isLoading } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: authMe,
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (user?.preferred_locale) setLocale(user.preferred_locale);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    if (
      previousUserId.current !== undefined &&
      previousUserId.current !== (user?.id || null)
    ) {
      // Cart and wishlist are principal-scoped. Never let React Query reuse
      // the previous account's data after login, logout, or account switch.
      queryClient.removeQueries({ queryKey: ["cart"] });
      queryClient.removeQueries({ queryKey: ["wishlist"] });
    }
    previousUserId.current = user?.id || null;
  }, [queryClient, user?.id]);

  const value = {
    user,
    checking: isLoading,
    async login(email, password) {
      const u = await authLogin(email, password);
      queryClient.setQueryData(["auth", "me"], u);
      // Admin sessions are for operations only and must never inherit a
      // shopper's guest cart or wishlist state.
      if (u.role !== "admin") await mergeGuestCart(queryClient);
      return u;
    },
    async register(data) {
      const u = await authRegister(data);
      queryClient.setQueryData(["auth", "me"], u);
      await mergeGuestCart(queryClient);
      return u;
    },
    async logout() {
      try {
        await authLogout();
      } finally {
        queryClient.setQueryData(["auth", "me"], null);
        queryClient.removeQueries({ queryKey: ["cart"] });
        queryClient.removeQueries({ queryKey: ["wishlist"] });
      }
    },
    setUser: (u) => queryClient.setQueryData(["auth", "me"], u),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
