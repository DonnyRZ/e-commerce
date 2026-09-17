import { useQuery } from "@tanstack/react-query";
import { useI18n } from "@/i18n";
import { getCmsBundle } from "@/lib/api";
import { pickCmsLocalized } from "@/lib/localize";

export default function AnnouncementBar() {
  const { locale, t } = useI18n();
  const { data: bundle, isLoading, isError } = useQuery({
    queryKey: ["cms", "bundle"],
    queryFn: getCmsBundle,
    staleTime: 60_000,
  });
  if (isLoading) return null;
  const configured = bundle?.sections?.some((section) => section.key === "promo_bar");
  const text = isError
    ? t("announcement.text")
    : configured
      ? pickCmsLocalized(bundle?.announcement?.translations, locale)
      : "";
  if (!text) return null;
  return (
    <div
      data-testid="announcement-bar"
      className="bg-neutral-950 px-4 py-2 text-center text-xs tracking-wide text-white sm:text-[13px]"
    >
      {text}
    </div>
  );
}
