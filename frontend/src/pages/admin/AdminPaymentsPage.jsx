import { useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { addAdminReviewNote, adminRefund, getAdminPaymentsReview } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, fmtMoney } from "./adminUtils";

function ReviewCard({ item, onSaved }) {
  const [note, setNote] = useState(item.review_note || "");
  const [busy, setBusy] = useState(false);

  const saveNote = async () => {
    if (!note.trim() || busy) return;
    setBusy(true);
    try {
      await addAdminReviewNote(item.payment_id, note.trim());
      toast.success("Review note saved");
      onSaved();
    } catch {
      toast.error("Could not save note");
    } finally {
      setBusy(false);
    }
  };

  const refund = async () => {
    if (busy || !window.confirm(`Refund ${fmtMoney(item.amount, item.currency)} for order ${item.order_number}?`)) return;
    setBusy(true);
    try {
      await adminRefund(item.payment_id);
      toast.success("Payment refund requested");
      onSaved();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || "Refund failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="border border-neutral-200 bg-white p-5" data-testid={`review-card-${item.payment_id}`}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <Link to={`/orders/${item.order_number}`} className="font-semibold text-[#145A46] hover:underline" data-testid={`review-order-${item.order_number}`}>
            {item.order_number}
          </Link>
          <p className="mt-0.5 text-xs text-neutral-400">{fmtDate(item.created_at)} · txn {item.merchant_trans_id.slice(0, 12)}…</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusPill value={item.payment_status} />
          <StatusPill value={item.order_status} />
          <span className="text-base font-semibold">{fmtMoney(item.amount, item.currency)}</span>
        </div>
      </div>

      {item.failure_code || item.failure_note ? (
        <p className="mt-3 border-l-2 border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700" data-testid="review-failure">
          {item.failure_code} {item.failure_note}
        </p>
      ) : null}

      {item.events?.length ? (
        <ul className="mt-3 space-y-1 text-xs text-neutral-500" data-testid="review-events">
          {item.events.map((e, i) => (
            <li key={i}>
              <span className="font-medium text-neutral-700">{e.event_type}</span> → {e.result}
              {e.provider_error_code ? ` (${e.provider_error_code})` : ""} · {fmtDate(e.created_at)}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="mt-4 flex flex-wrap items-end gap-3">
        <div className="min-w-64 flex-1">
          <label className="mb-1 block text-xs font-medium text-neutral-500">Review note</label>
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={2}
            maxLength={1000}
            data-testid={`review-note-${item.payment_id}`}
            className="w-full border border-neutral-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#145A46]"
            placeholder="Resolution notes after checking the CLICK dashboard…"
          />
        </div>
        <button
          onClick={saveNote}
          disabled={busy || !note.trim()}
          data-testid={`review-save-${item.payment_id}`}
          className="h-10 bg-[#145A46] px-5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
        >
          Save note
        </button>
        {item.payment_status === "paid" ? (
          <button
            onClick={refund}
            disabled={busy}
            data-testid={`review-refund-${item.payment_id}`}
            className="h-10 border border-red-300 px-5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
          >
            Refund payment
          </button>
        ) : null}
      </div>
    </article>
  );
}

export default function AdminPaymentsPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["admin-payments-review"],
    queryFn: getAdminPaymentsReview,
  });
  const onSaved = () => {
    queryClient.invalidateQueries({ queryKey: ["admin-payments-review"] });
    queryClient.invalidateQueries({ queryKey: ["admin-dashboard"] });
  };

  const items = data?.items || [];

  return (
    <div data-testid="admin-payments-page">
      <h1 className="text-xl font-semibold tracking-tight">Payment Review Queue</h1>
      <p className="mt-1 text-sm text-neutral-500">
        Payments flagged for reconciliation. Verify against the CLICK dashboard, then record a review note.
      </p>
      <div className="mt-5 space-y-4">
        {isLoading
          ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-40 w-full" />)
          : items.map((item) => <ReviewCard key={item.payment_id} item={item} onSaved={onSaved} />)}
        {!isLoading && !items.length ? (
          <div className="border border-neutral-200 bg-white px-5 py-12 text-center text-sm text-neutral-400" data-testid="review-empty">
            Queue is empty — no payments need review.
          </div>
        ) : null}
      </div>
    </div>
  );
}
