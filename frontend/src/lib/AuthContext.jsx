import { createContext, useContext, useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { authLogin, authLogout, authMe, authRegister } from "./api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const queryClient = useQueryClient();
  const { setLocale } = useI18n();
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

  const value = {
    user,
    checking: isLoading,
    async login(email, password) {
      const u = await authLogin(email, password);
      queryClient.setQueryData(["auth", "me"], u);
      return u;
    },
    async register(data) {
      const u = await authRegister(data);
      queryClient.setQueryData(["auth", "me"], u);
      return u;
    },
    async logout() {
      try {
        await authLogout();
      } finally {
        queryClient.setQueryData(["auth", "me"], null);
      }
    },
    setUser: (u) => queryClient.setQueryData(["auth", "me"], u),
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  return useContext(AuthContext);
}
