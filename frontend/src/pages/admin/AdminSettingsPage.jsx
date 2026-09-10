import { useQuery } from "@tanstack/react-query";
import { getAdminAudit, getAdminSettings } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { fmtDate, fmtMoney } from "./adminUtils";

function Row({ label, value, testId }) {
  return (
    <div className="flex justify-between gap-4 border-b border-neutral-50 py-2.5 text-sm" data-testid={testId}>
      <dt className="text-neutral-500">{label}</dt>
      <dd className="text-right font-medium">{value}</dd>
    </div>
  );
}

export default function AdminSettingsPage() {
  const settingsQuery = useQuery({ queryKey: ["admin-settings"], queryFn: getAdminSettings });
  const auditQuery = useQuery({
    queryKey: ["admin-audit"],
    queryFn: () => getAdminAudit({ page_size: 50 }),
  });

  const s = settingsQuery.data;

  return (
    <div data-testid="admin-settings-page">
      <h1 className="text-xl font-semibold tracking-tight">Settings</h1>

      <section className="mt-6 border border-neutral-200 bg-white p-5" data-testid="settings-store">
        <h2 className="text-sm font-semibold">Store configuration</h2>
        {settingsQuery.isLoading ? (
          <Skeleton className="mt-4 h-48 w-full" />
        ) : (
          <dl className="mt-3">
            <Row label="Store" value={s?.store} testId="setting-store" />
            <Row label="Business model" value={s?.business_model === "single_vendor" ? "Single vendor (this store operates everything)" : s?.business_model} testId="setting-model" />
            <Row label="Base currency" value={s?.currency} testId="setting-currency" />
            <Row label="Payment provider" value={`CLICK (${s?.click_mode} mode)`} testId="setting-payments" />
            <Row label="Shipping provider" value={s?.shipping_provider} testId="setting-shipping" />
            <Row
              label="Shipping methods"
              value={(s?.shipping_methods || []).map((m) => `${m.label} ${fmtMoney(m.amount, s?.currency)} (${m.eta} days)`).join(" · ")}
              testId="setting-shipping-methods"
            />
            <Row label="Free standard shipping over" value={fmtMoney(s?.free_standard_threshold, s?.currency)} testId="setting-free-shipping" />
            <Row label="Inventory reservation TTL" value={`${s?.inventory_reservation_ttl_minutes} min`} testId="setting-reservation-ttl" />
            <Row label="Media storage" value={s?.media_storage} testId="setting-media-storage" />
            <Row label="Locales" value={(s?.locales || []).join(", ")} testId="setting-locales" />
          </dl>
        )}
      </section>

      <section className="mt-6 border border-neutral-200 bg-white" data-testid="settings-audit">
        <h2 className="border-b border-neutral-200 px-5 py-3 text-sm font-semibold">Audit log</h2>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-neutral-100 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-2 font-medium">When</th>
              <th className="px-5 py-2 font-medium">Actor</th>
              <th className="px-5 py-2 font-medium">Action</th>
              <th className="px-5 py-2 font-medium">Target</th>
            </tr>
          </thead>
          <tbody>
            {auditQuery.isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={4} className="px-5 py-2.5"><Skeleton className="h-4 w-full" /></td></tr>
                ))
              : (auditQuery.data?.items || []).map((a) => (
                  <tr key={a.id} className="border-b border-neutral-50" data-testid={`audit-row-${a.id}`}>
                    <td className="whitespace-nowrap px-5 py-2.5 text-neutral-500">{fmtDate(a.created_at)}</td>
                    <td className="px-5 py-2.5 text-neutral-600">{a.actor || "system"}</td>
                    <td className="px-5 py-2.5 font-mono text-xs">{a.action}</td>
                    <td className="px-5 py-2.5 text-xs text-neutral-500">{a.target_type}</td>
                  </tr>
                ))}
            {!auditQuery.isLoading && !(auditQuery.data?.items || []).length ? (
              <tr><td colSpan={4} className="px-5 py-8 text-center text-sm text-neutral-400" data-testid="audit-empty">No audit events yet.</td></tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </div>
  );
}
