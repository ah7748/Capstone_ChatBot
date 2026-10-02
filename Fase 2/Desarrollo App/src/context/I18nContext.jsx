import { createContext, useContext, useEffect, useState } from 'react'
import dictionary from '../i18n/dictionary'

// Clave = texto en español. Valor = ['inglés', 'portugués'] o { en, pt }.
const LOCALES = { es: 'es-CL', en: 'en-GB', pt: 'pt-BR' }
const SUPPORTED = ['es', 'en', 'pt']

const stored = localStorage.getItem('lang')
// Idioma actual accesible fuera de componentes (errText, constantes, etc.)
let currentLang = SUPPORTED.includes(stored) ? stored : 'es'

function lookup(key) {
  const entry = dictionary[key]
  if (entry == null) return undefined
  if (Array.isArray(entry)) return entry[currentLang === 'en' ? 0 : 1]
  return entry[currentLang]
}

export const getLang = () => currentLang
export const hasKey = (key) => key in dictionary

/** Traduce `key` (español) al idioma actual. Admite variables: tr('Hola {name}', { name }) */
export function tr(key, vars) {
  let s = key
  if (currentLang !== 'es') {
    const found = lookup(key)
    if (found === undefined) {
      if (import.meta.env.DEV) console.warn(`[i18n] falta traducción (${currentLang}): "${key}"`)
    } else {
      s = found
    }
  }
  return vars ? s.replace(/\{(\w+)\}/g, (_, k) => (vars[k] ?? `{${k}}`)) : s
}

/** Fecha/hora en el idioma elegido (no en el del navegador). */
export const fmtDate = (d, opts) => new Date(d).toLocaleString(LOCALES[currentLang], opts)

export const PERIOD_OPTIONS = [
  ['7d', 'Últimos 7 días'], ['today', 'Hoy'], ['prev_month', 'Mes anterior'],
  ['30d', 'Últimos 30 días'], ['3m', 'Últimos 3 meses'], ['year', 'Año'],
]

const I18nCtx = createContext(null)

export function I18nProvider({ children }) {
  const [lang, setLangState] = useState(currentLang)

  useEffect(() => { document.documentElement.lang = lang }, [lang])

  const setLang = (l) => {
    if (!SUPPORTED.includes(l)) return
    currentLang = l                       // antes del re-render, para que tr() ya use el nuevo idioma
    localStorage.setItem('lang', l)
    setLangState(l)
  }

  return (
    <I18nCtx.Provider value={{ lang, setLang, t: tr, fmtDate }}>
      {children}
    </I18nCtx.Provider>
  )
}

export const useI18n = () => useContext(I18nCtx)
