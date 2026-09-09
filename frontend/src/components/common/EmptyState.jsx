import { Inbox } from "lucide-react";
import { useI18n } from "@/i18n";

export default function EmptyState({ title, description, action }) {
  const { t } = useI18n();
  return (
    <div
      data-testid="empty-state"
      className="flex flex-col items-center justify-center py-16 text-center"
    >
      <Inbox className="h-10 w-10 text-muted-foreground" aria-hidden="true" />
      <h2 className="mt-4 text-base font-semibold md:text-lg">
        {title || t("common.empty")}
      </h2>
      {description ? (
        <p className="mt-2 max-w-sm text-sm text-muted-foreground">{description}</p>
      ) : null}
      {action ? <div className="mt-6">{action}</div> : null}
    </div>
  );
}
