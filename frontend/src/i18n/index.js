import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { translations } from "./translations";

export const SUPPORTED_LOCALES = ["id", "en", "uz", "ru"];
export const DEFAULT_LOCALE = "en";
export const LOCALE_LABELS = {
  id: "Bahasa Indonesia",
  en: "English",
  uz: "O'zbek",
  ru: "Русский",
};
export const BASE_CURRENCY = "UZS";

const STORAGE_KEY = "mc_locale";

const I18nContext = createContext(null);

export function getLocalePreference(accountLocale) {
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (SUPPORTED_LOCALES.includes(saved)) return saved;
  } catch {
    // Fall back to the account preference when browser storage is unavailable.
  }
  return SUPPORTED_LOCALES.includes(accountLocale) ? accountLocale : null;
}

export function I18nProvider({ children }) {
  const [locale, setLocaleState] = useState(() => {
    return getLocalePreference() || DEFAULT_LOCALE;
  });

  const setLocale = (next) => {
    if (!SUPPORTED_LOCALES.includes(next)) return;
    setLocaleState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* storage unavailable */
    }
  };

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const value = useMemo(() => {
    const t = (key, params) => {
      let str =
        translations[locale]?.[key] ?? translations[DEFAULT_LOCALE][key] ?? key;
      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          str = str.replaceAll(`{${k}}`, String(v));
        });
      }
      return str;
    };
    return { locale, setLocale, t };
  }, [locale]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n must be used within I18nProvider");
  return ctx;
}
