import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { authErrorKey } from "@/lib/api";
import { completeCustomerAuth } from "@/lib/customerAuthFlow";
import BrandLogo from "@/components/brand/BrandLogo";

export default function LoginPage() {
  const { t } = useI18n();
  const { login, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const authenticatedUser = await login(email, password);
      if (authenticatedUser.role !== "customer") {
        await logout();
        setError(t("auth.customerOnly"));
        return;
      }
      await completeCustomerAuth({
        state: location.state,
        user: authenticatedUser,
        queryClient,
        navigate,
        t,
      });
    } catch (err) {
      setError(t(authErrorKey(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="login-page" className="mx-auto max-w-md py-12 lg:py-20">
      <div className="mb-10 flex justify-center">
        <BrandLogo size="lg" to="/" testId="login-brand-logo" priority />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("auth.login")}
      </h1>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <div>
          <label htmlFor="login-email" className="mb-1 block text-sm font-medium">
            {t("auth.email")}
          </label>
          <input
            id="login-email"
            data-testid="login-email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
          />
        </div>
        <div>
          <label htmlFor="login-password" className="mb-1 block text-sm font-medium">
            {t("auth.password")}
          </label>
          <input
            id="login-password"
            data-testid="login-password"
            type="password"
            required
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
          />
        </div>
        {error ? (
          <p data-testid="login-error" role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          data-testid="login-submit"
          disabled={busy}
          className="h-12 w-full bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:opacity-50"
        >
          {busy ? t("common.loading") : t("auth.login")}
        </button>
      </form>
      <div className="mt-5 flex items-center justify-between text-sm">
        <Link
          to="/forgot-password"
          data-testid="login-forgot-link"
          className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
        >
          {t("auth.forgot")}
        </Link>
        <Link
          to="/register"
          state={location.state}
          data-testid="login-register-link"
          className="font-medium underline-offset-4 hover:underline"
        >
          {t("auth.register")}
        </Link>
      </div>
    </div>
  );
}
