import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { authErrorKey } from "@/lib/api";
import { completeCustomerAuth } from "@/lib/customerAuthFlow";
import BrandLogo from "@/components/brand/BrandLogo";

export default function RegisterPage() {
  const { t, locale } = useI18n();
  const { register } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    password: "",
    preferred_locale: locale,
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const authenticatedUser = await register(form);
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

  const fieldClass =
    "h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground";

  return (
    <div data-testid="register-page" className="mx-auto max-w-md py-12 lg:py-20">
      <div className="mb-10 flex justify-center">
        <BrandLogo size="lg" to="/" testId="register-brand-logo" priority />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("auth.register")}
      </h1>
      <form onSubmit={submit} className="mt-8 space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label htmlFor="reg-first" className="mb-1 block text-sm font-medium">
              {t("auth.firstName")}
            </label>
            <input id="reg-first" data-testid="register-first-name" required value={form.first_name} onChange={set("first_name")} className={fieldClass} />
          </div>
          <div>
            <label htmlFor="reg-last" className="mb-1 block text-sm font-medium">
              {t("auth.lastName")}
            </label>
            <input id="reg-last" data-testid="register-last-name" value={form.last_name} onChange={set("last_name")} className={fieldClass} />
          </div>
        </div>
        <div>
          <label htmlFor="reg-email" className="mb-1 block text-sm font-medium">
            {t("auth.email")}
          </label>
          <input id="reg-email" data-testid="register-email" type="email" required autoComplete="email" value={form.email} onChange={set("email")} className={fieldClass} />
        </div>
        <div>
          <label htmlFor="reg-password" className="mb-1 block text-sm font-medium">
            {t("auth.password")}
          </label>
          <input id="reg-password" data-testid="register-password" type="password" required minLength={8} autoComplete="new-password" value={form.password} onChange={set("password")} className={fieldClass} />
        </div>
        <div>
          <label htmlFor="reg-locale" className="mb-1 block text-sm font-medium">
            {t("auth.localeLabel")}
          </label>
          <select id="reg-locale" data-testid="register-locale" value={form.preferred_locale} onChange={set("preferred_locale")} className={fieldClass}>
            {SUPPORTED_LOCALES.map((code) => (
              <option key={code} value={code}>
                {LOCALE_LABELS[code]}
              </option>
            ))}
          </select>
        </div>
        {error ? (
          <p data-testid="register-error" role="alert" className="text-sm text-destructive">
            {error}
          </p>
        ) : null}
        <button
          type="submit"
          data-testid="register-submit"
          disabled={busy}
          className="h-12 w-full bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:opacity-50"
        >
          {busy ? t("common.loading") : t("auth.register")}
        </button>
      </form>
      <p className="mt-5 text-sm text-muted-foreground">
        {t("auth.haveAccount")}{" "}
        <Link to="/login" state={location.state} data-testid="register-login-link" className="font-medium text-foreground underline-offset-4 hover:underline">
          {t("auth.login")}
        </Link>
      </p>
    </div>
  );
}
