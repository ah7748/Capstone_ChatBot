import { createContext, useContext, useState } from 'react'
import en from '../i18n/en'
import pt from '../i18n/pt'

const DICTS = {en, pt}
const LOCALES = {es: 'es-CL', en: 'en-GB', pt: 'pt-BR'}
// Diccionario de interfaz (ES base → EN, PT), heredado del wireframe v5.
let currentLang = localStorage.getItem('lang') || 'es'

export function tr(key, vars) {
  let s = key
  if (currentLang !== 'es'){
    s = DICTS[currentLang]?.[key]
    if (s === undefined){
      if (import.meta.env.DEV) console.warn(`[i18n] falta traduccion (${currentLang}): "${key}"`)
    }
  }
  return varsa ? s.replace(/\{(\w+)\}/g, (_, k) => vars[k] ?? `{${k}`) : s
}

export const fmtDate = (d, opts) =>
  new Date(d).toLocaleString(LOCALES[currentLang], opts)

export const PERIOD_OPTIONS = [
  ['7d', 'Últimos 7 días'], ['today', 'Hoy'], ['prev_month', 'Mes anterior'],
  ['30d', 'Últimos 30 días'], ['3m', 'Últimos 3 meses'], ['year', 'Año'],
]

const I18nCtx = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(currentLang)
  const setLang = (l) => {
    currentLang = l
    localStorage.setItem('lang', l)
    document.documentElement.lang = l
    setLangState(l)
  }
  return <I18nCtx.Provider value={{ lang, setLang, t: tr, fmtDate }}>{children}</I18nCtx.Provider>
}

export const useI18n = () => useContext(I18nCtx)
