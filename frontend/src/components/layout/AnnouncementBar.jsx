import { useI18n } from "@/i18n";

export default function AnnouncementBar() {
  const { t } = useI18n();
  return (
    <div
      data-testid="announcement-bar"
      className="bg-primary text-primary-foreground text-center text-xs sm:text-sm py-2 px-4"
    >
      {t("announcement.text")}
    </div>
  );
}
