import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useI18n } from "@/i18n";
import { authErrorKey, resetPassword } from "@/lib/api";
import BrandLogo from "@/components/brand/BrandLogo";

export default function ResetPasswordPage({ backTo = "/login", brandTo = "/" }) {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (err) {
      setError(t(authErrorKey(err)));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="reset-password-page" className="mx-auto max-w-md py-12 lg:py-20">
      <div className="mb-10 flex justify-center">
        <BrandLogo size="lg" to={brandTo} testId="reset-brand-logo" priority />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("auth.resetTitle")}
      </h1>
      {done ? (
        <p data-testid="reset-done" className="mt-6 text-sm text-muted-foreground">
          {t("auth.resetDone")}
        </p>
      ) : (
        <form onSubmit={submit} className="mt-6 space-y-4">
          <div>
            <label htmlFor="reset-password" className="mb-1 block text-sm font-medium">
              {t("auth.newPassword")}
            </label>
            <input
              id="reset-password"
              data-testid="reset-password-input"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
            />
          </div>
          {error ? (
            <p data-testid="reset-error" role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <button
            type="submit"
            data-testid="reset-submit"
            disabled={busy || !token}
            className="h-12 w-full bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:opacity-50"
          >
            {busy ? t("common.loading") : t("auth.resetCta")}
          </button>
        </form>
      )}
      <p className="mt-5 text-sm">
        <Link to={backTo} data-testid="reset-back-login" className="font-medium underline-offset-4 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </p>
    </div>
  );
}
