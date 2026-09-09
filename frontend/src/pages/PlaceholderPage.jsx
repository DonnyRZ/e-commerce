import EmptyState from "@/components/common/EmptyState";
import { useI18n } from "@/i18n";

export default function PlaceholderPage({ titleKey }) {
  const { t } = useI18n();
  return (
    <section
      data-testid={`page-${titleKey.split(".").pop()}`}
      className="py-16 sm:py-24"
    >
      <EmptyState title={t(titleKey)} description={t("common.comingSoon")} />
    </section>
  );
}
