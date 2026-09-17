import { useQuery } from "@tanstack/react-query";
import { getCmsFaq } from "@/lib/api";
import { useI18n } from "@/i18n";
import { pickLocalized } from "@/lib/localize";
import ErrorState from "@/components/common/ErrorState";
import EmptyState from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";

export default function FaqPage() {
  const { locale, t } = useI18n();
  const query = useQuery({
    queryKey: ["cms", "faq"],
    queryFn: getCmsFaq,
    staleTime: 60_000,
  });

  if (query.isLoading) {
    return (
      <section className="py-10 sm:py-16" data-testid="faq-loading">
        <Skeleton className="h-9 w-56" />
        <div className="mt-8 space-y-3">
          {Array.from({ length: 4 }).map((_, index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
      </section>
    );
  }

  if (query.isError) return <ErrorState onRetry={() => query.refetch()} />;

  const items = query.data?.items || [];
  return (
    <section data-testid="faq-page" className="mx-auto max-w-3xl py-10 sm:py-16">
      <p className="text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">{t("brand.name")}</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-tight sm:text-4xl">{t("footer.link.faq")}</h1>
      {items.length ? (
        <div className="mt-8 divide-y divide-border border-y border-border">
          {items.map((item) => {
            const question = pickLocalized(item.translations, locale) || item.slug;
            const answer = pickLocalized(item.translations, locale, "body") ||
              pickLocalized(item.translations, locale, "description");
            const questionId = `faq-question-${item.slug}`;
            const answerId = `faq-answer-${item.slug}`;
            return (
              <details key={item.id || item.slug} className="group py-5">
                <summary
                  id={questionId}
                  role="button"
                  aria-controls={answerId}
                  className="cursor-pointer list-none pr-8 text-base font-semibold marker:hidden"
                >
                  {question}
                </summary>
                {answer ? <p id={answerId} className="mt-3 whitespace-pre-wrap text-sm leading-6 text-muted-foreground">{answer}</p> : null}
              </details>
            );
          })}
        </div>
      ) : (
        <EmptyState title={t("common.empty")} description={t("common.comingSoon")} />
      )}
    </section>
  );
}
