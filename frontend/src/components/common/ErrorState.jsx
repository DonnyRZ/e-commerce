import { AlertCircle } from "lucide-react";
import { useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";

export default function ErrorState({ message, onRetry }) {
  const { t } = useI18n();
  return (
    <div
      data-testid="error-state"
      role="alert"
      className="flex flex-col items-center justify-center py-16 text-center"
    >
      <AlertCircle className="h-10 w-10 text-destructive" aria-hidden="true" />
      <h2 className="mt-4 text-base font-semibold md:text-lg">{t("common.error")}</h2>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        {message || t("errors.generic")}
      </p>
      {onRetry ? (
        <Button
          variant="outline"
          className="mt-6"
          data-testid="error-retry-button"
          onClick={onRetry}
        >
          {t("common.retry")}
        </Button>
      ) : null}
    </div>
  );
}
