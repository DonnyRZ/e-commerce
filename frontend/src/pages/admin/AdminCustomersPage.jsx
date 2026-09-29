import { Fragment, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { getAdminCustomer, getAdminCustomers } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney, inputClass } from "./adminUtils";

function CustomerDetail({ id }) {
  const { data, isLoading } = useQuery({
    queryKey: ["admin-customer", id],
    queryFn: () => getAdminCustomer(id),
  });
  if (isLoading) return <div className="px-5 py-4"><Skeleton className="h-16 w-full" /></div>;
  if (!data) return null;
  return (
    <div className="bg-neutral-50 px-5 py-4" data-testid={`customer-detail-${id}`}>
      <p className="text-xs uppercase tracking-widest text-neutral-400">
        {data.preferred_locale} · joined {fmtDate(data.created_at)}
      </p>
      {data.orders?.length ? (
        <Fragment>
        <table className="mt-3 hidden w-full text-sm sm:table">
          <tbody>
            {data.orders.map((o) => (
              <tr key={o.order_number} className="border-b border-neutral-100" data-testid={`customer-order-${o.order_number}`}>
                <td className="py-2 font-medium">{o.order_number}</td>
                <td className="py-2 text-neutral-500">{fmtDate(o.created_at)}</td>
                <td className="py-2"><StatusPill value={o.status} /></td>
                <td className="py-2 text-right font-medium">{fmtMoney(o.grand_total, o.currency)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="mt-3 space-y-2 sm:hidden" data-testid={`customer-orders-mobile-${id}`}>
          {data.orders.map((o) => (
            <div key={o.order_number} className="rounded border border-neutral-200 bg-white p-3 text-xs" data-testid={`customer-order-mobile-${o.order_number}`}>
              <div className="flex flex-wrap items-center justify-between gap-2"><span className="font-semibold text-[#145A46]">{o.order_number}</span><StatusPill value={o.status} /></div>
              <div className="mt-2 flex items-center justify-between gap-2 text-neutral-500"><span>{fmtDate(o.created_at)}</span><span className="font-semibold text-neutral-800">{fmtMoney(o.grand_total, o.currency)}</span></div>
            </div>
          ))}
        </div>
        </Fragment>
      ) : (
        <p className="mt-3 text-sm text-neutral-400">No orders yet.</p>
      )}
    </div>
  );
}

export default function AdminCustomersPage() {
  const [q, setQ] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [page, setPage] = useState(1);
  const [openId, setOpenId] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["admin-customers", { submitted, page }],
    queryFn: () => getAdminCustomers({ q: submitted || undefined, page }),
  });

  const items = data?.items || [];
  const total = data?.total || 0;
  const pageSize = data?.page_size || 20;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div data-testid="admin-customers-page">
      <h1 className="text-xl font-semibold tracking-tight">Customers</h1>

      <form
        className="relative mt-5"
        onSubmit={(e) => {
          e.preventDefault();
          setPage(1);
          setSubmitted(q.trim());
        }}
      >
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" aria-hidden="true" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search by email or name…" data-testid="customers-search" className={`${inputClass} w-full max-w-md pl-9`} />
      </form>

      <div className="mt-5 space-y-3 md:hidden" data-testid="customers-mobile-list">
        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-28 w-full rounded-lg" />)
          : items.map((c) => (
              <article key={c.id} className="rounded-lg border border-neutral-200 bg-white p-4" data-testid={`customer-mobile-card-${c.id}`}>
                <button type="button" aria-expanded={openId === c.id} onClick={() => setOpenId(openId === c.id ? null : c.id)} className="block min-h-11 w-full text-left">
                  <span className="flex items-start justify-between gap-3"><span className="min-w-0"><span className="block break-words font-semibold">{c.first_name} {c.last_name}</span><span className="mt-1 block break-all text-xs text-neutral-500">{c.email}</span></span><span className="shrink-0 text-xs font-medium text-[#145A46]">{openId === c.id ? "Tutup" : "Detail"}</span></span>
                </button>
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-neutral-100 pt-3 text-xs">
                  <StatusPill value={c.is_active ? "active" : "inactive"} />
                  <span className="uppercase text-neutral-500">{c.preferred_locale}</span>
                  <span className="text-neutral-500">{c.order_count} order</span>
                  <span className="ml-auto text-neutral-500">{fmtDate(c.created_at)}</span>
                </div>
                {openId === c.id ? <CustomerDetail id={c.id} /> : null}
              </article>
            ))}
        {!isLoading && !items.length ? <div className="rounded-lg border border-neutral-200 bg-white px-4 py-10 text-center text-sm text-neutral-400" data-testid="customers-mobile-empty">No customers found.</div> : null}
      </div>

      <div className="mt-5 hidden overflow-x-auto border border-neutral-200 bg-white md:block">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-3 font-medium">Customer</th>
              <th className="px-5 py-3 font-medium">Locale</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Orders</th>
              <th className="px-5 py-3 font-medium">Joined</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={5} className="px-5 py-3"><Skeleton className="h-5 w-full" /></td></tr>
                ))
              : items.map((c) => (
                  <Fragment key={c.id}>
                    <tr
                      onClick={() => setOpenId(openId === c.id ? null : c.id)}
                      className="cursor-pointer border-b border-neutral-50 hover:bg-neutral-50"
                      data-testid={`customer-row-${c.id}`}
                    >
                      <td className="px-5 py-3">
                        <p className="font-medium">{c.first_name} {c.last_name}</p>
                        <p className="text-xs text-neutral-400">{c.email}</p>
                      </td>
                      <td className="px-5 py-3 uppercase text-neutral-500">{c.preferred_locale}</td>
                      <td className="px-5 py-3"><StatusPill value={c.is_active ? "active" : "inactive"} /></td>
                      <td className="px-5 py-3">{c.order_count}</td>
                      <td className="px-5 py-3 text-neutral-500">{fmtDate(c.created_at)}</td>
                    </tr>
                    {openId === c.id ? (
                      <tr><td colSpan={5} className="p-0"><CustomerDetail id={c.id} /></td></tr>
                    ) : null}
                  </Fragment>
                ))}
            {!isLoading && !items.length ? (
              <tr><td colSpan={5} className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="customers-empty">No customers found.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm">
        <span className="text-neutral-500" data-testid="customers-total">{total} customers</span>
        <div className="flex gap-2">
          <button disabled={page <= 1} onClick={() => setPage(page - 1)} data-testid="customers-prev" className="min-h-11 whitespace-nowrap border border-neutral-300 px-3 text-[11px] font-medium disabled:opacity-40 sm:px-4 sm:text-xs">Previous</button>
          <span className="flex min-h-11 items-center px-1 text-xs text-neutral-500 sm:px-2" data-testid="customers-page-indicator">Page {page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(page + 1)} data-testid="customers-next" className="min-h-11 whitespace-nowrap border border-neutral-300 px-3 text-[11px] font-medium disabled:opacity-40 sm:px-4 sm:text-xs">Next</button>
        </div>
      </div>
    </div>
  );
}
