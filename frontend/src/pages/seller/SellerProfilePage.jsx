import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useI18n } from "@/i18n";
import { getSellerProfile, updateSellerProfile } from "@/lib/api";
import PriceDisplay, { LOCALE_TAGS } from "@/components/common/PriceDisplay";
import { Skeleton } from "@/components/ui/skeleton";

const inputClass =
  "h-10 w-full border border-neutral-300 bg-white px-3 text-sm outline-none focus:border-[#145A46]";

export default function SellerProfilePage() {
  const { t, locale } = useI18n();
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ store_name: "", contact_phone: "", description: "" });
  const [saving, setSaving] = useState(false);

  const profileQuery = useQuery({ queryKey: ["seller-profile"], queryFn: getSellerProfile });

  useEffect(() => {
    const p = profileQuery.data;
    if (p) {
      setForm({
        store_name: p.store_name || "",
        contact_phone: p.contact_phone || "",
        description: p.description || "",
      });
    }
  }, [profileQuery.data]);

  const save = async (e) => {
    e.preventDefault();
    if (saving) return;
    setSaving(true);
    try {
      await updateSellerProfile(form);
      toast.success(t("seller.profile.saved"));
      queryClient.invalidateQueries({ queryKey: ["seller-profile"] });
    } catch {
      toast.error(t("seller.editor.failed"));
    } finally {
      setSaving(false);
    }
  };

  if (profileQuery.isLoading) {
    return <div data-testid="profile-loading"><Skeleton className="h-8 w-48" /><Skeleton className="mt-6 h-64 w-full max-w-xl" /></div>;
  }
  const p = profileQuery.data;
  const tag = LOCALE_TAGS[locale] || "en-US";

  return (
    <div data-testid="seller-profile-page">
      <h1 className="text-xl font-semibold tracking-tight">{t("seller.profile.title")}</h1>
      <div className="mt-6 grid max-w-3xl gap-5 lg:grid-cols-[1fr_240px]">
        <form onSubmit={save} className="border border-neutral-200 bg-white p-5">
          <div className="space-y-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.profile.storeName")}</label>
              <input value={form.store_name} onChange={(e) => setForm({ ...form, store_name: e.target.value })} required className={inputClass} data-testid="profile-store-name" maxLength={255} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.profile.phone")}</label>
              <input value={form.contact_phone} onChange={(e) => setForm({ ...form, contact_phone: e.target.value })} className={inputClass} data-testid="profile-phone" maxLength={40} />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-neutral-500">{t("seller.profile.description")}</label>
              <textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} rows={5} className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]" data-testid="profile-description" maxLength={2000} />
            </div>
            <button type="submit" disabled={saving} data-testid="profile-save" className="h-11 bg-[#145A46] px-8 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
              {saving ? t("seller.editor.saving") : t("seller.profile.save")}
            </button>
          </div>
        </form>
        <aside className="h-fit border border-neutral-200 bg-white p-5 text-xs text-neutral-500" data-testid="profile-meta">
          <dl className="space-y-3">
            <div>
              <dt className="font-medium text-neutral-400">{t("seller.profile.email")}</dt>
              <dd className="mt-0.5 text-sm text-neutral-800" data-testid="profile-email">{p.email}</dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-400">{t("seller.profile.slug")}</dt>
              <dd className="mt-0.5 text-sm text-neutral-800" data-testid="profile-slug">{p.slug}</dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-400">{t("seller.profile.memberSince")}</dt>
              <dd className="mt-0.5 text-sm text-neutral-800" data-testid="profile-created">
                {new Intl.DateTimeFormat(tag, { dateStyle: "medium" }).format(new Date(p.created_at))}
              </dd>
            </div>
            <div>
              <dt className="font-medium text-neutral-400">{t("seller.products.status")}</dt>
              <dd className="mt-0.5" data-testid="profile-status">
                <span className={`inline-block px-2 py-0.5 text-[11px] font-semibold uppercase ${p.is_active ? "bg-[#145A46] text-white" : "bg-neutral-300 text-neutral-700"}`}>
                  {p.is_active ? t("seller.status.active") : t("seller.status.inactive")}
                </span>
              </dd>
            </div>
          </dl>
        </aside>
      </div>
    </div>
  );
}
