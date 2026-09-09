import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { LOCALE_LABELS, SUPPORTED_LOCALES, useI18n } from "@/i18n";
import { useAuth } from "@/lib/AuthContext";
import { translations } from "@/i18n/translations";
import {
  authErrorKey,
  createAddress,
  deleteAddress,
  getAddresses,
  updateAddress,
  updateProfile,
} from "@/lib/api";
import EmptyState from "@/components/common/EmptyState";
import { Skeleton } from "@/components/ui/skeleton";

const EMPTY_ADDRESS = {
  label: "",
  recipient_name: "",
  phone: "",
  address_line_1: "",
  address_line_2: "",
  city: "",
  state_province: "",
  postal_code: "",
  country_code: "ID",
  is_default: false,
};

const fieldClass =
  "h-10 w-full border border-border bg-background px-3 text-sm outline-none focus:border-foreground";

function AddressForm({ initial, onSubmit, onCancel, busy, testPrefix }) {
  const { t } = useI18n();
  const [form, setForm] = useState(initial);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const fields = [
    ["label", t("auth.label")],
    ["recipient_name", t("auth.recipient")],
    ["phone", t("auth.phone")],
    ["address_line_1", t("auth.addressLine1")],
    ["address_line_2", t("auth.addressLine2")],
    ["city", t("auth.city")],
    ["state_province", t("auth.province")],
    ["postal_code", t("auth.postalCode")],
    ["country_code", t("auth.country")],
  ];
  return (
    <form
      data-testid={testPrefix}
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ ...form, label: form.label || "Home" });
      }}
      className="mt-4 grid grid-cols-1 gap-3 border border-border p-4 sm:grid-cols-2"
    >
      {fields.map(([key, label]) => (
        <div key={key} className={key.startsWith("address_line") ? "sm:col-span-2" : ""}>
          <label className="mb-1 block text-xs font-medium text-muted-foreground">
            {label}
          </label>
          <input
            data-testid={`${testPrefix}-${key.replace(/_/g, "-")}`}
            value={form[key] || ""}
            onChange={set(key)}
            required={!["label", "address_line_2"].includes(key)}
            className={fieldClass}
          />
        </div>
      ))}
      <label className="flex items-center gap-2 text-sm sm:col-span-2">
        <input
          type="checkbox"
          data-testid={`${testPrefix}-is-default`}
          checked={form.is_default}
          onChange={(e) => setForm((f) => ({ ...f, is_default: e.target.checked }))}
          className="h-4 w-4 accent-primary"
        />
        {t("auth.setDefault")}
      </label>
      <div className="flex gap-2 sm:col-span-2">
        <button
          type="submit"
          data-testid={`${testPrefix}-save`}
          disabled={busy}
          className="h-10 bg-foreground px-6 text-sm font-semibold text-background hover:bg-primary disabled:opacity-50"
        >
          {t("common.save")}
        </button>
        <button
          type="button"
          data-testid={`${testPrefix}-cancel`}
          onClick={onCancel}
          className="h-10 border border-border px-6 text-sm font-medium hover:border-foreground"
        >
          {t("common.cancel")}
        </button>
      </div>
    </form>
  );
}

export default function AccountPage() {
  const { t, locale, setLocale } = useI18n();
  const { user, checking, logout, setUser } = useAuth();
  const queryClient = useQueryClient();
  const [profile, setProfile] = useState(null);
  const [showAddressForm, setShowAddressForm] = useState(false);
  const [editingAddress, setEditingAddress] = useState(null);

  useEffect(() => {
    if (user && !profile) {
      setProfile({
        first_name: user.first_name || "",
        last_name: user.last_name || "",
        preferred_locale: user.preferred_locale || locale,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.id]);

  const addressesQuery = useQuery({
    queryKey: ["addresses"],
    queryFn: getAddresses,
    enabled: Boolean(user),
  });

  const profileMutation = useMutation({
    mutationFn: updateProfile,
    onSuccess: (u) => {
      setUser(u);
      setLocale(u.preferred_locale);
      const msg =
        translations[u.preferred_locale]?.["auth.profileSaved"] ??
        translations.en["auth.profileSaved"];
      toast.success(msg);
    },
    onError: (e) => toast.error(t(authErrorKey(e))),
  });

  const addressSave = useMutation({
    mutationFn: (data) =>
      editingAddress ? updateAddress(editingAddress.id, data) : createAddress(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["addresses"] });
      setShowAddressForm(false);
      setEditingAddress(null);
      toast.success(t("auth.addressSaved"));
    },
    onError: (e) => toast.error(t(authErrorKey(e))),
  });

  const addressDelete = useMutation({
    mutationFn: deleteAddress,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["addresses"] });
      toast.success(t("auth.addressDeleted"));
    },
  });

  if (checking) {
    return (
      <div className="py-12" data-testid="account-loading">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="mt-6 h-40 w-full max-w-2xl" />
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;

  const addresses = addressesQuery.data || [];

  return (
    <div data-testid="account-page" className="py-8 lg:py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight lg:text-3xl">
            {t("auth.account")}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">{user.email}</p>
        </div>
        <button
          type="button"
          data-testid="account-logout"
          onClick={logout}
          className="border border-border px-5 py-2 text-sm font-medium transition-colors hover:border-foreground"
        >
          {t("auth.logout")}
        </button>
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-2">
        <section data-testid="account-profile" className="border border-border p-5">
          <h2 className="text-sm font-semibold uppercase tracking-wide">
            {t("auth.profile")}
          </h2>
          {profile ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                profileMutation.mutate(profile);
              }}
              className="mt-4 space-y-3"
            >
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t("auth.firstName")}
                  </label>
                  <input
                    data-testid="profile-first-name"
                    value={profile.first_name}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, first_name: e.target.value }))
                    }
                    className={fieldClass}
                  />
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">
                    {t("auth.lastName")}
                  </label>
                  <input
                    data-testid="profile-last-name"
                    value={profile.last_name}
                    onChange={(e) =>
                      setProfile((p) => ({ ...p, last_name: e.target.value }))
                    }
                    className={fieldClass}
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  {t("auth.localeLabel")}
                </label>
                <select
                  data-testid="profile-locale"
                  value={profile.preferred_locale}
                  onChange={(e) =>
                    setProfile((p) => ({ ...p, preferred_locale: e.target.value }))
                  }
                  className={fieldClass}
                >
                  {SUPPORTED_LOCALES.map((code) => (
                    <option key={code} value={code}>
                      {LOCALE_LABELS[code]}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                data-testid="profile-save"
                disabled={profileMutation.isPending}
                className="h-10 bg-foreground px-6 text-sm font-semibold text-background hover:bg-primary disabled:opacity-50"
              >
                {t("common.save")}
              </button>
            </form>
          ) : null}
        </section>

        <section data-testid="account-addresses" className="border border-border p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide">
              {t("auth.addresses")}
            </h2>
            {!showAddressForm && !editingAddress ? (
              <button
                type="button"
                data-testid="address-add"
                onClick={() => setShowAddressForm(true)}
                className="text-sm font-medium underline-offset-4 hover:underline"
              >
                {t("auth.addAddress")}
              </button>
            ) : null}
          </div>
          {addresses.length === 0 && !showAddressForm ? (
            <p data-testid="addresses-empty" className="mt-4 text-sm text-muted-foreground">
              {t("auth.noAddresses")}
            </p>
          ) : (
            <ul className="mt-4 space-y-3">
              {addresses.map((a) => (
                <li
                  key={a.id}
                  data-testid={`address-item-${a.id}`}
                  className="border border-border p-3 text-sm"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium">
                      {a.label}
                      {a.is_default ? (
                        <span
                          data-testid={`address-default-${a.id}`}
                          className="ml-2 bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground"
                        >
                          {t("auth.defaultBadge")}
                        </span>
                      ) : null}
                    </span>
                    <div className="flex gap-3 text-xs">
                      <button
                        type="button"
                        data-testid={`address-edit-${a.id}`}
                        onClick={() => {
                          setEditingAddress(a);
                          setShowAddressForm(false);
                        }}
                        className="underline-offset-4 hover:underline"
                      >
                        {t("common.edit")}
                      </button>
                      <button
                        type="button"
                        data-testid={`address-delete-${a.id}`}
                        onClick={() => addressDelete.mutate(a.id)}
                        className="text-destructive underline-offset-4 hover:underline"
                      >
                        {t("common.delete")}
                      </button>
                    </div>
                  </div>
                  <p className="mt-1 text-muted-foreground">
                    {a.recipient_name} · {a.phone}
                  </p>
                  <p className="text-muted-foreground">
                    {a.address_line_1}
                    {a.address_line_2 ? `, ${a.address_line_2}` : ""}, {a.city},{" "}
                    {a.state_province} {a.postal_code}, {a.country_code}
                  </p>
                </li>
              ))}
            </ul>
          )}
          {showAddressForm ? (
            <AddressForm
              testPrefix="address-form-new"
              initial={EMPTY_ADDRESS}
              busy={addressSave.isPending}
              onSubmit={(data) => addressSave.mutate(data)}
              onCancel={() => setShowAddressForm(false)}
            />
          ) : null}
          {editingAddress ? (
            <AddressForm
              testPrefix="address-form-edit"
              initial={editingAddress}
              busy={addressSave.isPending}
              onSubmit={(data) => addressSave.mutate(data)}
              onCancel={() => setEditingAddress(null)}
            />
          ) : null}
        </section>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Link
          to="/wishlist"
          data-testid="account-wishlist-link"
          className="border border-border p-5 text-sm font-medium transition-colors hover:border-foreground"
        >
          {t("header.wishlist")} →
        </Link>
        <Link
          to="/orders"
          data-testid="account-orders-link"
          className="border border-border p-5 text-sm font-medium transition-colors hover:border-foreground"
        >
          {t("footer.link.orders")} →
        </Link>
      </div>
    </div>
  );
}

export { EmptyState as _AccountEmptyState };
