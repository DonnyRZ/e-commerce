import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCmsBundle } from "@/lib/api";
import { pickLocalized } from "@/lib/localize";

export default function AnnouncementBar() {
  const { locale, t } = useI18n();
  const { data: bundle } = useQuery({
    queryKey: ["cms", "bundle"],
    queryFn: getCmsBundle,
    staleTime: 60_000,
  });
  const text =
    pickLocalized(bundle?.announcement?.translations, locale) || t("announcement.text");
  return (
    <div
      data-testid="announcement-bar"
      className="bg-neutral-950 px-4 py-2 text-center text-xs tracking-wide text-white sm:text-[13px]"
    >
      {text}
    </div>
  );
}
