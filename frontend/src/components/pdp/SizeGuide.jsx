import { useI18n } from "@/i18n";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

const ROWS = [
  { size: "XS", chest: 84, length: 64 },
  { size: "S", chest: 88, length: 66 },
  { size: "M", chest: 92, length: 68 },
  { size: "L", chest: 96, length: 70 },
  { size: "XL", chest: 100, length: 72 },
  { size: "XXL", chest: 104, length: 74 },
];

export default function SizeGuide() {
  const { t } = useI18n();
  return (
    <Dialog>
      <DialogTrigger asChild>
        <button
          type="button"
          data-testid="size-guide-button"
          className="text-xs font-medium text-foreground underline underline-offset-4 hover:text-primary"
        >
          {t("pdp.sizeGuide")}
        </button>
      </DialogTrigger>
      <DialogContent className="max-w-sm" data-testid="size-guide-dialog">
        <DialogHeader>
          <DialogTitle>{t("pdp.sizeGuide")}</DialogTitle>
        </DialogHeader>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs uppercase text-muted-foreground">
              <th className="py-2">{t("options.size")}</th>
              <th className="py-2">{t("pdp.chest")}</th>
              <th className="py-2">{t("pdp.length")}</th>
            </tr>
          </thead>
          <tbody>
            {ROWS.map((r) => (
              <tr key={r.size} className="border-b border-border last:border-0">
                <td className="py-2 font-medium">{r.size}</td>
                <td className="py-2">{r.chest}</td>
                <td className="py-2">{r.length}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-xs text-muted-foreground">{t("pdp.sizeGuideNote")}</p>
      </DialogContent>
    </Dialog>
  );
}
