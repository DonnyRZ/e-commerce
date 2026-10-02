const OPTION_LABELS = {
  size: "Ukuran",
  ukuran: "Ukuran",
  color: "Warna",
  colour: "Warna",
  warna: "Warna",
  material: "Bahan",
  bahan: "Bahan",
  volume: "Volume",
  capacity: "Kapasitas",
  kapasitas: "Kapasitas",
  format: "Tipe",
  type: "Tipe",
  tipe: "Tipe",
  style: "Model",
  model: "Model",
  variant: "Varian",
  varian: "Varian",
};

function optionLabel(key) {
  const normalized = String(key || "").trim().toLocaleLowerCase();
  return OPTION_LABELS[normalized] || String(key || "").trim();
}

export function formatOrderItemOptions(item) {
  const values = item?.option_values;
  const entries = values && typeof values === "object" && !Array.isArray(values)
    ? Object.entries(values).filter(([, value]) => value !== null && value !== undefined && String(value).trim())
    : [];

  if (entries.length) {
    if (entries.length === 1 && ["variant", "varian"].includes(String(entries[0][0]).trim().toLocaleLowerCase())) {
      return `${optionLabel(entries[0][0])}: ${entries[0][1]}`;
    }
    return entries.map(([key, value]) => `${optionLabel(key) || "Opsi"}: ${value}`).join(" · ");
  }

  const legacyVariant = typeof item?.variant === "string" ? item.variant.trim() : "";
  return legacyVariant;
}

export function countOrderItemUnits(items = []) {
  return items.reduce((total, item) => total + Math.max(0, Number(item?.quantity) || 0), 0);
}
