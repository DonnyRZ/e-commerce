import { useI18n } from "@/i18n";

export default function AnnouncementBar() {
  const { t } = useI18n();
  return (
    <div
      data-testid="announcement-bar"
      className="bg-neutral-950 px-4 py-2 text-center text-xs tracking-wide text-white sm:text-[13px]"
    >
      {t("announcement.text")}
    </div>
  );
}
