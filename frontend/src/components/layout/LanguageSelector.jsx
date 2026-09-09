import { Globe } from "lucide-react";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export default function LanguageSelector() {
  const { locale, setLocale, t } = useI18n();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          data-testid="language-selector"
          aria-label={t("header.language")}
          className="gap-1.5 px-2"
        >
          <Globe className="h-4 w-4" aria-hidden="true" />
          <span className="text-xs font-medium uppercase">{locale}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" data-testid="language-menu">
        {SUPPORTED_LOCALES.map((code) => (
          <DropdownMenuItem
            key={code}
            data-testid={`language-option-${code}`}
            onClick={() => setLocale(code)}
            className={code === locale ? "font-semibold text-primary" : ""}
          >
            {LOCALE_LABELS[code]}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
