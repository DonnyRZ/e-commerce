import { Link, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { getCmsContent } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusPill, fmtDate, inputClass } from "./adminUtils";

const CONTENT_TYPES = [
  "hero", "announcement", "banner", "story", "page", "faq_item",
  "nav_item", "footer_group", "footer_item", "footer_text",
  "homepage_section", "department_visual",
];

export default function CmsContentPage() {
  const [params, setParams] = useSearchParams();
  const type = params.get("type") || "";
  const status = params.get("status") || "";
  const q = params.get("q") || "";

  const { data, isLoading } = useQuery({
    queryKey: ["cms-content", { type, status, q }],
    queryFn: () => getCmsContent({ type: type || undefined, status: status || undefined, q: q || undefined }),
  });

  const setFilter = (key, value) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    setParams(next);
  };

  const items = data?.items || [];

  return (
    <div data-testid="cms-content-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold tracking-tight">CMS Content</h1>
        <Link
          to="/cms/new"
          data-testid="cms-new-button"
          className="inline-flex h-10 items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          New Content
        </Link>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <select value={type} onChange={(e) => setFilter("type", e.target.value)} className={`${inputClass} w-52`} data-testid="cms-type-filter">
          <option value="">All types</option>
          {CONTENT_TYPES.map((ct) => (
            <option key={ct} value={ct}>{ct.replaceAll("_", " ")}</option>
          ))}
        </select>
        <select value={status} onChange={(e) => setFilter("status", e.target.value)} className={`${inputClass} w-44`} data-testid="cms-status-filter">
          <option value="">All statuses</option>
          <option value="draft">Draft</option>
          <option value="published">Published</option>
          <option value="archived">Archived</option>
        </select>
        <input
          value={q}
          onChange={(e) => setFilter("q", e.target.value)}
          placeholder="Search name or slug…"
          className={`${inputClass} w-56`}
          data-testid="cms-search"
        />
      </div>

      <div className="mt-5 overflow-x-auto border border-neutral-200 bg-white">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wider text-neutral-400">
              <th className="px-5 py-3 font-medium">Name</th>
              <th className="px-5 py-3 font-medium">Type</th>
              <th className="px-5 py-3 font-medium">Status</th>
              <th className="px-5 py-3 font-medium">Locales</th>
              <th className="px-5 py-3 font-medium">Updated</th>
            </tr>
          </thead>
          <tbody>
            {isLoading
              ? Array.from({ length: 5 }).map((_, i) => (
                  <tr key={i}><td colSpan={5} className="px-5 py-3"><Skeleton className="h-5 w-full" /></td></tr>
                ))
              : items.map((e) => (
                  <tr key={e.id} className="border-b border-neutral-50 hover:bg-neutral-50" data-testid={`cms-row-${e.slug || e.id}`}>
                    <td className="px-5 py-3">
                      <Link to={`/cms/${e.id}`} className="font-medium text-[#145A46] hover:underline" data-testid={`cms-edit-${e.slug || e.id}`}>
                        {e.internal_name}
                      </Link>
                      <p className="text-xs text-neutral-400">{e.slug || "—"}</p>
                    </td>
                    <td className="px-5 py-3 text-neutral-600">{e.content_type.replaceAll("_", " ")}</td>
                    <td className="px-5 py-3">
                      <StatusPill value={e.status} />
                      {!e.is_visible ? <span className="ml-1 text-[10px] uppercase tracking-wide text-neutral-400">hidden</span> : null}
                    </td>
                    <td className="px-5 py-3">
                      <span className="flex gap-1" data-testid={`cms-locales-${e.id}`}>
                        {["id", "en", "uz", "ru"].map((l) => (
                          <span
                            key={l}
                            className={`inline-flex h-5 w-7 items-center justify-center text-[10px] font-semibold uppercase ${
                              e.completeness?.includes(l) ? "bg-[#145A46]/10 text-[#145A46]" : "bg-neutral-100 text-neutral-300"
                            }`}
                          >
                            {l}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="px-5 py-3 text-neutral-500">{fmtDate(e.updated_at)}</td>
                  </tr>
                ))}
            {!isLoading && !items.length ? (
              <tr><td colSpan={5} className="px-5 py-10 text-center text-sm text-neutral-400" data-testid="cms-empty">No content found.</td></tr>
            ) : null}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-neutral-400" data-testid="cms-total">{data?.total ?? 0} entries · Drafts are never visible on the storefront.</p>
    </div>
  );
}
