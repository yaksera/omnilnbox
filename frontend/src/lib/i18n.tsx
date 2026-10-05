"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import NE from "@/locales/ne";

/**
 * App language (English / नेपाली).
 *
 *   const t = useT();
 *   t("Inbox")                       -> "इनबक्स" in Nepali, "Inbox" in English
 *   t("{n} unread", { n: 3 })        -> placeholders in {braces}
 *
 * English text is the key. A missing translation simply shows the English text, so nothing ever breaks.
 * Translations live in src/locales/ne/*.ts (one file per area of the app).
 */
export type Lang = "en" | "ne";
const STORAGE_KEY = "omni.lang";

type Ctx = { lang: Lang; setLang: (l: Lang) => void };
const LangContext = createContext<Ctx>({ lang: "en", setLang: () => undefined });

function fill(text: string, vars?: Record<string, string | number>) {
  return vars ? text.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : text;
}

export function translate(lang: Lang, text: string, vars?: Record<string, string | number>) {
  return fill(lang === "ne" ? NE[text] ?? text : text, vars);
}

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === "ne" || saved === "en") setLangState(saved);
    } catch { /* storage blocked */ }
  }, []);
  useEffect(() => { document.documentElement.lang = lang === "ne" ? "ne" : "en"; }, [lang]);
  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(STORAGE_KEY, l); } catch { /* storage blocked */ }
  }, []);
  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return <LangContext.Provider value={value}>{children}</LangContext.Provider>;
}

export function useLang() {
  return useContext(LangContext);
}

/** Translate function for the current language. */
export function useT() {
  const { lang } = useContext(LangContext);
  return useCallback((text: string, vars?: Record<string, string | number>) => translate(lang, text, vars), [lang]);
}
