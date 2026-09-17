import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { getCmsPage } from "@/lib/api";
import { useI18n } from "@/i18n";
import { mediaUrl, pickLocalized } from "@/lib/localize";
import ErrorState from "@/components/common/ErrorState";
import EmptyState from "@/components/common/EmptyState";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";

export default function CmsPublicPage() {
  const { slug } = useParams();
  const { locale, t } = useI18n();
  const query = useQuery({
    queryKey: ["cms", "page", slug],
    queryFn: () => getCmsPage(slug),
    enabled: Boolean(slug),
    staleTime: 60_000,
  });

  if (query.isLoading) {
    return (
      <section className="py-10 sm:py-16" data-testid="cms-page-loading">
        <Skeleton className="h-9 w-2/3 max-w-xl" />
        <Skeleton className="mt-5 h-64 w-full" />
      </section>
    );
  }

  if (query.isError) {
    if (query.error?.response?.status === 404) {
      return <EmptyState title={t("errors.notFound")} description={t("common.comingSoon")} />;
    }
    return <ErrorState onRetry={() => query.refetch()} />;
  }

  const entry = query.data;
  const title = pickLocalized(entry?.translations, locale) || entry?.slug || t("errors.notFound");
  const subtitle = pickLocalized(entry?.translations, locale, "subtitle");
  const body = pickLocalized(entry?.translations, locale, "body") ||
    pickLocalized(entry?.translations, locale, "description");
  const image = mediaUrl(entry?.image_url);

  if (!entry) return <EmptyState title={t("errors.notFound")} />;

  return (
    <article data-testid={`cms-page-${slug}`} className="mx-auto max-w-3xl py-10 sm:py-16">
      {image ? (
        <ImageWithFallback
          src={image}
          alt={pickLocalized(entry?.translations, locale, "alt_text") || title}
          className="mb-8 max-h-[28rem] w-full object-cover"
        />
      ) : null}
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">
        {entry.content_type === "page" ? t("brand.name") : entry.content_type}
      </p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{title}</h1>
      {subtitle ? <p className="mt-3 text-base text-muted-foreground">{subtitle}</p> : null}
      {body ? (
        <div className="mt-8 whitespace-pre-wrap text-sm leading-7 text-foreground">{body}</div>
      ) : (
        <EmptyState title={t("common.empty")} description={t("common.comingSoon")} />
      )}
    </article>
  );
}
