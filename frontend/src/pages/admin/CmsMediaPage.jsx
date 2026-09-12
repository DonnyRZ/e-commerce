import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import { deleteCmsMedia, getCmsMedia, updateCmsMedia, uploadCmsMedia } from "@/lib/api";
import { mediaUrl } from "@/lib/localize";
import { Skeleton } from "@/components/ui/skeleton";
import { inputClass } from "./adminUtils";

const LOCALES = ["en", "id", "uz", "ru"];
const fmtSize = (bytes) => (bytes > 1024 * 1024 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`);

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
      toast.success("Media details saved");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
      onClose();
    } catch {
      toast.error("Save failed");
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy || !window.confirm(`Delete "${asset.original_filename}"?`)) return;
    setBusy(true);
    try {
      await deleteCmsMedia(asset.id);
      toast.success("Media deleted");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
      onClose();
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "object" && d?.error) || "Delete failed (media may be in use)");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-5 border border-[#145A46]/30 bg-white p-5" data-testid="media-editor">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold">{asset.original_filename}</h2>
        <button onClick={onClose} aria-label="close" data-testid="media-editor-close">
          <X className="h-4 w-4 text-neutral-400 hover:text-neutral-900" />
        </button>
      </div>
      <div className="mt-4 flex flex-wrap gap-5">
        <img src={mediaUrl(asset.url)} alt="" className="h-32 w-32 border border-neutral-200 object-cover" />
        <div className="min-w-64 flex-1 space-y-3">
          {LOCALES.map((loc) => (
            <div key={loc} className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[11px] font-medium text-neutral-500">Alt text ({loc})</label>
                <input
                  value={tr[loc].alt_text}
                  onChange={(e) => setTr({ ...tr, [loc]: { ...tr[loc], alt_text: e.target.value } })}
                  className={inputClass}
                  data-testid={`media-alt-${loc}`}
                />
              </div>
              <div>
                <label className="mb-1 block text-[11px] font-medium text-neutral-500">Caption ({loc})</label>
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
            <button onClick={save} disabled={busy} data-testid="media-save" className="h-10 bg-[#145A46] px-6 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
              Save
            </button>
            <button onClick={remove} disabled={busy} data-testid="media-delete" className="inline-flex h-10 items-center gap-1.5 border border-red-300 px-4 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-50">
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Delete
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function CmsMediaPage() {
  const queryClient = useQueryClient();
  const [uploading, setUploading] = useState(false);
  const [selected, setSelected] = useState(null);

  const { data, isLoading } = useQuery({
    queryKey: ["cms-media"],
    queryFn: () => getCmsMedia({ page_size: 96 }),
  });

  const upload = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      await uploadCmsMedia(file);
      toast.success("Image uploaded");
      queryClient.invalidateQueries({ queryKey: ["cms-media"] });
    } catch (err) {
      const d = err?.response?.data?.detail;
      const code = typeof d === "object" ? d?.error : d;
      toast.error(code === "file_too_large" ? "File too large (max 5 MB)." : code === "unsupported_media_type" ? "Only JPEG, PNG or WebP images." : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const items = data?.items || [];

  return (
    <div data-testid="cms-media-page">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Media Library</h1>
          <p className="mt-1 text-sm text-neutral-500">JPEG, PNG or WebP up to 5 MB. Used by CMS content and product images.</p>
        </div>
        <label
          className={`inline-flex h-10 cursor-pointer items-center gap-1.5 bg-[#145A46] px-4 text-sm font-semibold text-white hover:opacity-90 ${uploading ? "opacity-50" : ""}`}
          data-testid="media-upload-button"
        >
          <ImagePlus className="h-4 w-4" aria-hidden="true" />
          {uploading ? "Uploading…" : "Upload image"}
          <input type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={upload} disabled={uploading} data-testid="media-upload-input" />
        </label>
      </div>

      {selected ? <MediaEditor asset={selected} onClose={() => setSelected(null)} /> : null}

      <div className="mt-5 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5" data-testid="media-grid">
        {isLoading
          ? Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="aspect-square" />)
          : items.map((m) => (
              <button
                key={m.id}
                onClick={() => setSelected(m)}
                className="group border border-neutral-200 bg-white p-2 text-left transition-colors hover:border-[#145A46]"
                data-testid={`media-item-${m.id}`}
              >
                <img src={mediaUrl(m.url)} alt={m.translations?.en?.alt_text || m.original_filename} loading="lazy" className="aspect-square w-full object-cover" />
                <p className="mt-2 truncate text-xs font-medium">{m.original_filename}</p>
                <p className="text-[10px] text-neutral-400">
                  {fmtSize(m.file_size)}{m.width ? ` · ${m.width}×${m.height}` : ""} · used {m.usage_count}×
                </p>
              </button>
            ))}
      </div>
      {!isLoading && !items.length ? (
        <div className="mt-5 border border-neutral-200 bg-white px-5 py-12 text-center text-sm text-neutral-400" data-testid="media-empty">
          No media yet — upload your first image.
        </div>
      ) : null}
    </div>
  );
}
