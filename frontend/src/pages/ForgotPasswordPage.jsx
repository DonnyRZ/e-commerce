import { useState } from "react";
import { Link } from "react-router-dom";
import { useI18n } from "@/i18n";
import { forgotPassword } from "@/lib/api";
import BrandLogo from "@/components/brand/BrandLogo";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await forgotPassword(email);
    } catch {
      /* response is intentionally generic */
    }
    setSent(true);
    setBusy(false);
  };

  return (
    <div data-testid="forgot-password-page" className="mx-auto max-w-md py-12 lg:py-20">
      <div className="mb-10 flex justify-center">
        <BrandLogo size="lg" to="/" testId="forgot-brand-logo" priority />
      </div>
      <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
        {t("auth.forgotTitle")}
      </h1>
      {sent ? (
        <p data-testid="forgot-sent" className="mt-6 text-sm text-muted-foreground">
          {t("auth.forgotSent")}
        </p>
      ) : (
        <>
          <p className="mt-3 text-sm text-muted-foreground">{t("auth.forgotText")}</p>
          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label htmlFor="forgot-email" className="mb-1 block text-sm font-medium">
                {t("auth.email")}
              </label>
              <input
                id="forgot-email"
                data-testid="forgot-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="h-11 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground"
              />
            </div>
            <button
              type="submit"
              data-testid="forgot-submit"
              disabled={busy}
              className="h-12 w-full bg-foreground text-sm font-semibold text-background transition-colors hover:bg-primary disabled:opacity-50"
            >
              {busy ? t("common.loading") : t("auth.sendLink")}
            </button>
          </form>
        </>
      )}
      <p className="mt-5 text-sm">
        <Link to="/login" data-testid="forgot-back-login" className="font-medium underline-offset-4 hover:underline">
          {t("auth.backToLogin")}
        </Link>
      </p>
    </div>
  );
}
