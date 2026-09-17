import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { authErrorKey } from "@/lib/api";
import BrandLogo from "@/components/brand/BrandLogo";

export default function AdminLoginPage() {
  const { t } = useI18n();
  const { login, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const authenticatedUser = await login(email, password);
      if (authenticatedUser.role !== "admin") {
        await logout();
        setError(t("auth.adminOnly"));
        return;
      }
      navigate(location.state?.from || "/", { replace: true });
    } catch (err) {
      setError(t(authErrorKey(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main
      className="flex min-h-screen items-center justify-center bg-neutral-50 px-4 py-12 text-neutral-900"
      data-testid="admin-login-page"
    >
      <section className="w-full max-w-md border border-neutral-200 bg-white p-6 shadow-sm sm:p-8">
        <div className="mb-10 flex justify-center">
          <BrandLogo size="lg" to="/" testId="admin-login-brand-logo" priority />
        </div>
        <p className="text-center text-xs font-semibold uppercase tracking-[0.2em] text-[#CD9B3A]">
          Admin Console
        </p>
        <h1 className="mt-3 text-center text-2xl font-semibold tracking-tight lg:text-3xl">
          {t("auth.login")}
        </h1>
        <p className="mt-3 text-center text-sm text-neutral-500">
          Sign in to manage the MUSLIMAH CANTIK store.
        </p>
        <form onSubmit={submit} className="mt-8 space-y-4">
          <div>
            <label htmlFor="admin-login-email" className="mb-1 block text-sm font-medium">
              {t("auth.email")}
            </label>
            <input
              id="admin-login-email"
              data-testid="admin-login-email"
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
            />
          </div>
          <div>
            <label htmlFor="admin-login-password" className="mb-1 block text-sm font-medium">
              {t("auth.password")}
            </label>
            <input
              id="admin-login-password"
              data-testid="admin-login-password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
            />
          </div>
          {error ? (
            <p data-testid="admin-login-error" role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            data-testid="admin-login-submit"
            disabled={busy}
            className="h-12 w-full bg-[#02422C] text-sm font-semibold text-white transition-colors hover:bg-[#145A46] disabled:opacity-50"
          >
            {busy ? t("common.loading") : t("auth.login")}
          </button>
        </form>
        <div className="mt-5 flex items-center justify-between text-sm">
          <Link
            to="/forgot-password"
            data-testid="admin-login-forgot-link"
            className="text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            {t("auth.forgot")}
          </Link>
          <a href="/" data-testid="admin-login-store-link" className="font-medium underline-offset-4 hover:underline">
            View Store
          </a>
        </div>
      </section>
    </main>
  );
}
