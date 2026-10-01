import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { getLocalePreference, useI18n } from "@/i18n";
import { authLogin, authLogout, authMe, authRefresh, authRegister, mergeCart } from "./api";
import { translations } from "@/i18n/translations";
import { toast } from "sonner";

const AuthContext = createContext(null);
const AUTH_EXPIRED_EVENT = "shanicantik:auth-expired";
const PRIVATE_QUERY_ROOTS = new Set([
  "addresses",
  "cart",
  "my-order",
  "my-orders",
  "wishlist",
]);

async function loadCurrentUser() {
  try {
    return await authMe();
  } catch (error) {
    if (error?.response?.status !== 401) throw error;
    const accessSessionWasPresent =
      error?.response?.data?.detail !== "not_authenticated";
    try {
      await authRefresh();
      return await authMe();
    } catch (refreshError) {
      const detail = refreshError?.response?.data?.detail;
      if (
        (accessSessionWasPresent || detail !== "not_authenticated") &&
        typeof window !== "undefined"
      ) {
        window.dispatchEvent(
          new CustomEvent(AUTH_EXPIRED_EVENT, { detail: { notify: true } })
        );
      }
      return null;
    }
  }
}

function removePrivateQueries(queryClient, userId) {
  if (userId) {
    queryClient.removeQueries({ queryKey: ["cart", userId] });
    queryClient.removeQueries({ queryKey: ["wishlist", userId] });
    queryClient.removeQueries({ queryKey: ["addresses", userId] });
    queryClient.removeQueries({ queryKey: ["my-orders", userId] });
    queryClient.removeQueries({ queryKey: ["my-order", userId] });
    return;
  }
  queryClient.removeQueries({
    predicate: (query) =>
      PRIVATE_QUERY_ROOTS.has(query.queryKey[0]) &&
      !(["cart", "wishlist"].includes(query.queryKey[0]) &&
        query.queryKey[1] === "guest"),
  });
}

function removeAllPrivateQueries(queryClient) {
  queryClient.removeQueries({
    predicate: (query) =>
      PRIVATE_QUERY_ROOTS.has(query.queryKey[0]) &&
      !(["cart", "wishlist"].includes(query.queryKey[0]) &&
        query.queryKey[1] === "guest"),
  });
}

export function AuthProvider({ children, mergeCustomerCartOnRestore = true }) {
  const queryClient = useQueryClient();
  const { setLocale, locale } = useI18n();
  const previousUserId = useRef(undefined);
  const mergeJobs = useRef(new Map());
  const localeRef = useRef(locale);
  const [cartMergeError, setCartMergeError] = useState(false);
  const [cartMergePending, setCartMergePending] = useState(false);
  const [cartMergeReadyUserId, setCartMergeReadyUserId] = useState(null);
  const { data: user = null, isLoading } = useQuery({
    queryKey: ["auth", "me"],
    queryFn: async () => {
      const restoredUser = await loadCurrentUser();
      if (!restoredUser) removePrivateQueries(queryClient, null);
      return restoredUser;
    },
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    localeRef.current = locale;
  }, [locale]);

  const mergeCustomerCart = useCallback((customerId) => {
    const existingJob = mergeJobs.current.get(customerId);
    if (existingJob) return existingJob;

    const job = (async () => {
      setCartMergePending(true);
      setCartMergeError(false);
      try {
        const result = await mergeCart();
        const { adjustments = [], ...cart } = result;
        const stillCurrent =
          queryClient.getQueryData(["auth", "me"])?.id === customerId;
        if (stillCurrent) {
          queryClient.setQueryData(["cart", customerId], cart);
          setCartMergeError(false);
        }
        if (stillCurrent) {
          queryClient.removeQueries({ queryKey: ["cart", "guest"] });
        }
        if (adjustments.length && stillCurrent) {
          const loc = localeRef.current || "en";
          toast.info(
            translations[loc]?.["cart.mergeAdjusted"] ??
              translations.en["cart.mergeAdjusted"]
          );
        }
        return true;
      } catch {
        const stillCurrent =
          queryClient.getQueryData(["auth", "me"])?.id === customerId;
        if (stillCurrent) {
          setCartMergeError(true);
          const loc = localeRef.current || "en";
          toast.error(
            translations[loc]?.["cart.mergeFailed"] ??
              translations.en["cart.mergeFailed"]
          );
        }
        return false;
      } finally {
        if (queryClient.getQueryData(["auth", "me"])?.id === customerId) {
          setCartMergeReadyUserId(customerId);
        }
        mergeJobs.current.delete(customerId);
        setCartMergePending(mergeJobs.current.size > 0);
      }
    })();

    mergeJobs.current.set(customerId, job);
    return job;
  }, [queryClient]);

  useEffect(() => {
    const preferredLocale = getLocalePreference(user?.preferred_locale);
    if (preferredLocale) setLocale(preferredLocale);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  useEffect(() => {
    const currentUserId = user?.id || null;
    const previousId = previousUserId.current;
    if (previousId !== undefined && previousId !== currentUserId) {
      removePrivateQueries(queryClient, previousId);
      setCartMergeError(false);
      setCartMergeReadyUserId(null);
    }
    previousUserId.current = currentUserId;
  }, [queryClient, user?.id]);

  const restoredCustomerId = user?.role === "customer" ? user.id : null;
  useEffect(() => {
    if (mergeCustomerCartOnRestore && restoredCustomerId) {
      void mergeCustomerCart(restoredCustomerId);
    } else if (!restoredCustomerId) {
      setCartMergeError(false);
      setCartMergeReadyUserId(null);
    }
  }, [mergeCustomerCart, mergeCustomerCartOnRestore, restoredCustomerId]);

  useEffect(() => {
    const handleSessionExpired = (event) => {
      void queryClient.cancelQueries({ queryKey: ["auth", "me"] });
      queryClient.setQueryData(["auth", "me"], null);
      removeAllPrivateQueries(queryClient);
      setCartMergeError(false);
      setCartMergePending(false);
      setCartMergeReadyUserId(null);
      if (event.detail?.notify) {
        const loc = localeRef.current || "en";
        toast.error(
          translations[loc]?.["auth.sessionExpired"] ??
            translations.en["auth.sessionExpired"]
        );
      }
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, handleSessionExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handleSessionExpired);
  }, [queryClient]);

  const value = {
    user,
    checking: isLoading,
    cartMergeError,
    cartMergePending,
    cartMergeReady: user?.role !== "customer" || cartMergeReadyUserId === user?.id,
    cartMutationsBlocked:
      user?.role === "customer" &&
      (cartMergeReadyUserId !== user.id || cartMergePending),
    retryCartMerge: () => (user?.role === "customer" ? mergeCustomerCart(user.id) : false),
    async login(email, password) {
      await queryClient.cancelQueries({ queryKey: ["auth", "me"] });
      await queryClient.cancelQueries({
        predicate: (query) => PRIVATE_QUERY_ROOTS.has(query.queryKey[0]),
      });
      const authenticatedUser = await authLogin(email, password);
      queryClient.setQueryData(["auth", "me"], authenticatedUser);
      if (mergeCustomerCartOnRestore && authenticatedUser.role === "customer") {
        await mergeCustomerCart(authenticatedUser.id);
      }
      return authenticatedUser;
    },
    async register(data) {
      await queryClient.cancelQueries({ queryKey: ["auth", "me"] });
      await queryClient.cancelQueries({
        predicate: (query) => PRIVATE_QUERY_ROOTS.has(query.queryKey[0]),
      });
      const authenticatedUser = await authRegister(data);
      queryClient.setQueryData(["auth", "me"], authenticatedUser);
      if (mergeCustomerCartOnRestore && authenticatedUser.role === "customer") {
        await mergeCustomerCart(authenticatedUser.id);
      }
      return authenticatedUser;
    },
    async logout() {
      await queryClient.cancelQueries({ queryKey: ["auth", "me"] });
      await queryClient.cancelQueries({
        predicate: (query) => PRIVATE_QUERY_ROOTS.has(query.queryKey[0]),
      });
      try {
        try {
          await authLogout();
        } catch (error) {
          // A stale CSRF cookie can survive an older frontend release. Refresh
          // rotates the CSRF cookie, then logout can clear the auth cookies.
          if (
            error?.response?.status === 403 &&
            error?.response?.data?.detail === "csrf_failed"
          ) {
            await authRefresh();
            await authLogout();
          } else {
            throw error;
          }
        }
      } finally {
        queryClient.setQueryData(["auth", "me"], null);
        removeAllPrivateQueries(queryClient);
        setCartMergeError(false);
        setCartMergePending(false);
        setCartMergeReadyUserId(null);
      }
    },
    setUser: (authenticatedUser) =>
      queryClient.setQueryData(["auth", "me"], authenticatedUser),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
