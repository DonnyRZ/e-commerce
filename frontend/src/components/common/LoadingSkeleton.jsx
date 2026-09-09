import { useI18n } from "@/i18n";
import { Skeleton } from "@/components/ui/skeleton";

export default function LoadingSkeleton({ rows = 3 }) {
  const { t } = useI18n();
  return (
    <div
      data-testid="loading-skeleton"
      aria-label={t("common.loading")}
      className="space-y-3 py-8"
    >
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-5 w-full" />
      ))}
    </div>
  );
}
