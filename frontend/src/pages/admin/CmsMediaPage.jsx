import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ImagePlus, Search, Trash2, X } from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { deleteCmsMedia, getCmsMedia, updateCmsMedia, uploadCmsMedia } from "@/lib/api";
import { mediaUrl } from "@/lib/localize";
import ImageWithFallback from "@/components/common/ImageWithFallback";
import { Skeleton } from "@/components/ui/skeleton";
import { inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];
const fmtSize = (bytes) => (bytes > 1024 * 1024 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`);
const cmsPath = (href) => {
  if (!href) return "/";
  const normalized = href.startsWith("/admin/") ? href.slice("/admin".length) : href;
  return normalized.startsWith("/") ? normalized : `/${normalized}`;
};

function MediaEditor({ asset, onClose }) {
  const queryClient = useQueryClient();
  const [tr, setTr] = useState(() =>
    Object.fromEntries(
      LOCALES.map((l) => [l, {
        alt_text: asset.translations?.[l]?.alt_text || "",
        caption: asset.translations?.[l]?.caption || "",
      }])
    )
  );
  const [busy, setBusy] = useState(false);

  const save = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await updateCmsMedia(asset.id, { translations: tr });
      toast.success("Detail media berhasil disimpan.");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
      onClose();
    } catch {
      toast.error("Detail media gagal disimpan.");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy || asset.usage_count > 0 || !window.confirm(`Hapus permanen “${asset.original_filename}”?`)) return;
    setBusy(true);
    try {
      const result = await deleteCmsMedia(asset.id);
      if (result?.storage_cleanup_pending) toast.warning("Media dihapus dari CMS, tetapi pembersihan file perlu diulang.");
      else toast.success("Media berhasil dihapus.");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
      onClose();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || "Media gagal dihapus karena masih digunakan.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5 rounded-xl border border-[#DCD4C5] bg-[#FDFBF6] p-5 shadow-sm" data-testid="media-editor">
      <div className="flex items-center justify-between">
        <div><h2 className="text-sm font-semibold text-[#17392C]">{asset.original_filename}</h2><p className="mt-0.5 text-[11px] text-stone-500">{asset.mime_type} · {fmtSize(asset.file_size)} · digunakan {asset.usage_count}×</p></div>
        <button type="button" onClick={onClose} aria-label="Tutup detail media" data-testid="media-editor-close">
          <X className="h-4 w-4 text-neutral-400 hover:text-neutral-900" />
        </button>
      </div>
      <div className="mt-4 flex flex-wrap gap-5">
        <ImageWithFallback src={mediaUrl(asset.url)} alt="" className="h-32 w-32 border border-neutral-200 object-cover" />
        <div className="min-w-64 flex-1 space-y-3">
          {LOCALES.map((loc) => (
            <div key={loc} className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[11px] font-medium text-neutral-600">Teks alternatif · {({ en: "English", id: "Indonesia", uz: "O'zbek", ru: "Русский" })[loc]}</label>
                <input
                  value={tr[loc].alt_text}
                  onChange={(e) => setTr({ ...tr, [loc]: { ...tr[loc], alt_text: e.target.value } })}
                  className={inputClass}
                  data-testid={`media-alt-${loc}`}
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-neutral-600">Keterangan · {({ en: "English", id: "Indonesia", uz: "O'zbek", ru: "Русский" })[loc]}</label>
                <input
                  value={tr[loc].caption}
                  onChange={(e) => setTr({ ...tr, [loc]: { ...tr[loc], caption: e.target.value } })}
                  className={inputClass}
                  data-testid={`media-caption-${loc}`}
                />
              </div>
            </div>
          ))}
          <div className="flex items-center gap-3 pt-1">
            <button onClick={save} disabled={busy} data-testid="media-save" className="h-10 rounded-lg bg-[#02422C] px-6 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
              Simpan detail
            </button>
            <button onClick={remove} disabled={busy || asset.usage_count > 0} title={asset.usage_count > 0 ? "Lepaskan media dari semua konten sebelum menghapus." : "Hapus permanen"} data-testid="media-delete" className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-red-200 px-4 text-sm font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Hapus media
            </button>
          </div>
          {asset.usage_count > 0 ? <p className="text-xs text-amber-800">Media ini masih digunakan. Lepaskan dari {asset.usage_count} konten terlebih dahulu.</p> : null}
        </div>
      </div>
    </div>
  );
}

export default function CmsMediaPage() {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const pageSize = 24;

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ["cms-media", search, page],
    queryFn: () => getCmsMedia({ q: search.trim() || undefined, page, page_size: pageSize }),
    placeholderData: (previous) => previous,
  });

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await uploadCmsMedia(file);
      toast.success("Gambar berhasil diunggah.");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "object" ? d?.error : d;
      toast.error(code === "file_too_large" || err?.response?.status === 413 ? "Ukuran gambar maksimal 25 MB." : code === "unsupported_media_type" ? "Gunakan gambar JPEG, PNG, atau WebP." : "Gambar gagal diunggah.");
    } finally {
      setUploading(false);
    }
  };

  const items = data?.items || [];

  return (
    <div data-testid="cms-media-page" className="mx-auto max-w-7xl space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-[#8A6420]">Aset visual toko</p>
          <h1 className="mt-1 font-brand text-3xl font-semibold tracking-tight text-[#17392C]">Pustaka media</h1>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-stone-500">Kelola gambar yang dapat digunakan ulang. Media yang sedang dipakai tidak dapat dihapus agar halaman toko tetap utuh.</p>
        </div>
        <label
          className={`inline-flex h-11 cursor-pointer items-center gap-2 rounded-lg bg-[#02422C] px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-[#063723] ${uploading ? "opacity-50" : ""}`}
          data-testid="media-upload-button"
        >
          <ImagePlus className="h-4 w-4" aria-hidden="true" />
          {uploading ? "Mengunggah…" : "Unggah gambar"}
          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={upload} disabled={uploading} data-testid="media-upload-input" />
        </label>
      </div>

      {selected ? <MediaEditor asset={selected} onClose={() => setSelected(null)} /> : null}

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[#E9E3D7] bg-white p-3 shadow-sm">
        <label className="flex min-w-60 flex-1 items-center gap-2 text-sm text-neutral-500">
          <Search className="h-4 w-4" aria-hidden="true" />
          <span className="sr-only">Cari media</span>
          <input value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} className={`${inputClass} border-0 p-0 shadow-none focus:ring-0`} placeholder="Cari nama file…" data-testid="media-search" />
        </label>
        <span className="text-xs text-stone-500">{data?.total || 0} media</span>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" data-testid="media-grid">
        {isError ? <div className="col-span-full rounded-xl border border-red-200 bg-white px-5 py-12 text-center" data-testid="media-error"><p className="font-semibold text-red-900">Pustaka media gagal dimuat.</p><button type="button" onClick={() => refetch()} className="mt-3 rounded-lg bg-[#02422C] px-4 py-2 text-xs font-semibold text-white">Coba lagi</button></div> : isLoading
          ? Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)
          : items.map((m) => (
              <div
                key={m.id}
                className="group rounded-xl border border-[#E9E3D7] bg-white p-2.5 shadow-sm transition hover:-translate-y-0.5 hover:border-[#02422C]/50 hover:shadow-md"
                data-testid={`media-item-${m.id}`}
              >
                <button type="button" onClick={() => setSelected(m)} className="block w-full text-left" aria-label={`Edit ${m.original_filename}`}>
                  <ImageWithFallback src={mediaUrl(m.url)} alt={m.translations?.en?.alt_text || m.original_filename} loading="lazy" className="aspect-square w-full rounded-lg bg-stone-100 object-cover" />
                  <p className="mt-2 truncate text-xs font-semibold text-[#17392C]">{m.original_filename}</p>
                </button>
                <p className="text-[10px] text-neutral-400">
                  {fmtSize(m.file_size)}{m.width ? ` · ${m.width}×${m.height}` : ""} · dipakai {m.usage_count}×
                </p>
                {m.usage?.length ? <div className="mt-1 flex flex-wrap gap-1">{m.usage.slice(0, 3).map((u) => <Link key={`${u.type}-${u.id}`} to={cmsPath(u.href)} className="rounded bg-[#F4F1E9] px-1.5 py-0.5 text-[9px] text-stone-600 hover:text-[#02422C]">{u.type === "cms-draft" ? "draft CMS" : u.type === "cms" ? "CMS" : u.type}</Link>)}{m.usage.length > 3 ? <span className="px-1 text-[9px] text-stone-400">+{m.usage.length - 3}</span> : null}</div> : <span className="mt-1 block text-[9px] font-medium text-amber-700">Belum digunakan</span>}
              </div>
            ))}
      </div>
      {!isLoading && !isError && !items.length ? (
        <div className="rounded-xl border border-[#E9E3D7] bg-white px-5 py-12 text-center text-sm text-stone-500" data-testid="media-empty">
          <p>Belum ada gambar yang cocok.</p>
          <p className="mt-1 text-xs">Unggah gambar untuk mulai mengelola media CMS.</p>
        </div>
      ) : null}
      {data?.total > pageSize ? (
        <div className="flex items-center justify-between text-sm">
          <button type="button" onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page <= 1} className="inline-flex h-9 items-center gap-1 rounded-lg border border-[#DDD6C8] bg-white px-3 disabled:opacity-40" data-testid="media-page-prev"><ChevronLeft className="h-4 w-4" aria-hidden="true" />Sebelumnya</button>
          <span className="text-xs text-stone-500">Halaman {page} dari {Math.ceil(data.total / pageSize)}</span>
          <button type="button" onClick={() => setPage((p) => Math.min(Math.ceil(data.total / pageSize), p + 1))} disabled={page >= Math.ceil(data.total / pageSize)} className="inline-flex h-9 items-center gap-1 rounded-lg border border-[#DDD6C8] bg-white px-3 disabled:opacity-40" data-testid="media-page-next">Berikutnya<ChevronRight className="h-4 w-4" aria-hidden="true" /></button>
        </div>
      ) : null}
    </div>
  );
}
